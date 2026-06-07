from __future__ import annotations

from typing import Any

from google.protobuf.json_format import MessageToDict

from ga4_mcp_server.auth import get_credentials
from ga4_mcp_server.config import GA4MCPConfig
from ga4_mcp_server.errors import GA4MCPError, safe_error_message
from ga4_mcp_server.validation import (
    validate_account_resource,
    validate_date_range,
    validate_field_names,
    validate_filters,
    validate_property_id,
)


def list_accounts(config: GA4MCPConfig | None = None) -> dict[str, Any]:
    config = config or GA4MCPConfig.from_env()
    try:
        from google.analytics import admin_v1beta

        client = admin_v1beta.AnalyticsAdminServiceClient(
            credentials=get_credentials(config)
        )
        request = admin_v1beta.ListAccountSummariesRequest(page_size=200)
        accounts = []
        for summary in client.list_account_summaries(request=request):
            accounts.append(
                {
                    "account": summary.account,
                    "display_name": summary.display_name,
                    "property_count": len(summary.property_summaries),
                }
            )
        return {
            "accounts": accounts,
            "message": "No GA accounts are available to this Google user."
            if not accounts
            else None,
        }
    except GA4MCPError:
        raise
    except Exception as exc:
        raise GA4MCPError(safe_error_message(exc)) from exc


def list_properties(
    account: str | None = None,
    config: GA4MCPConfig | None = None,
) -> dict[str, Any]:
    config = config or GA4MCPConfig.from_env()
    account_resource = validate_account_resource(account)
    try:
        from google.analytics import admin_v1beta

        client = admin_v1beta.AnalyticsAdminServiceClient(
            credentials=get_credentials(config)
        )
        request = admin_v1beta.ListAccountSummariesRequest(page_size=200)
        properties = []
        for summary in client.list_account_summaries(request=request):
            if account_resource and summary.account != account_resource:
                continue
            for prop in summary.property_summaries:
                properties.append(
                    {
                        "property_id": prop.property.removeprefix("properties/"),
                        "property": prop.property,
                        "display_name": prop.display_name,
                        "property_type": _enum_name(prop.property_type),
                        "parent": prop.parent,
                        "account": summary.account,
                        "account_display_name": summary.display_name,
                    }
                )
        return {
            "properties": properties,
            "message": "No GA4 properties are available for this Google user."
            if not properties
            else None,
        }
    except GA4MCPError:
        raise
    except Exception as exc:
        raise GA4MCPError(safe_error_message(exc)) from exc


def run_report(
    start_date: str,
    end_date: str,
    dimensions: list[str],
    metrics: list[str],
    property_id: str | int | None = None,
    filters: Any | None = None,
    config: GA4MCPConfig | None = None,
) -> dict[str, Any]:
    config = config or GA4MCPConfig.from_env()
    default_property_id = None if property_id else config.require_default_property_id()
    resolved_property_id = validate_property_id(property_id, default_property_id)
    start, end = validate_date_range(start_date, end_date)
    dimensions = validate_field_names(dimensions, "dimensions")
    metrics = validate_field_names(metrics, "metrics")
    validated_filters = validate_filters(filters)

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Filter,
            FilterExpression,
            FilterExpressionList,
            Metric,
            RunReportRequest,
        )

        request = RunReportRequest(
            property=f"properties/{resolved_property_id}",
            date_ranges=[DateRange(start_date=start, end_date=end)],
            dimensions=[Dimension(name=name) for name in dimensions],
            metrics=[Metric(name=name) for name in metrics],
            dimension_filter=_build_dimension_filter(
                validated_filters, Filter, FilterExpression, FilterExpressionList
            ),
            return_property_quota=True,
        )
        client = BetaAnalyticsDataClient(credentials=get_credentials(config))
        response = client.run_report(request)
        return _report_response_to_dict(resolved_property_id, response)
    except GA4MCPError:
        raise
    except Exception as exc:
        raise GA4MCPError(safe_error_message(exc)) from exc


def run_realtime_report(
    dimensions: list[str],
    metrics: list[str],
    property_id: str | int | None = None,
    config: GA4MCPConfig | None = None,
) -> dict[str, Any]:
    config = config or GA4MCPConfig.from_env()
    default_property_id = None if property_id else config.require_default_property_id()
    resolved_property_id = validate_property_id(property_id, default_property_id)
    dimensions = validate_field_names(dimensions, "dimensions")
    metrics = validate_field_names(metrics, "metrics")

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            Dimension,
            Metric,
            RunRealtimeReportRequest,
        )

        request = RunRealtimeReportRequest(
            property=f"properties/{resolved_property_id}",
            dimensions=[Dimension(name=name) for name in dimensions],
            metrics=[Metric(name=name) for name in metrics],
        )
        client = BetaAnalyticsDataClient(credentials=get_credentials(config))
        response = client.run_realtime_report(request)
        return _report_response_to_dict(resolved_property_id, response)
    except GA4MCPError:
        raise
    except Exception as exc:
        raise GA4MCPError(safe_error_message(exc)) from exc


def _build_dimension_filter(
    filters: list[dict[str, Any]],
    filter_type: Any,
    expression_type: Any,
    expression_list_type: Any,
) -> Any | None:
    expressions = []
    for item in filters:
        expressions.append(
            expression_type(
                filter=filter_type(
                    field_name=item["field_name"],
                    string_filter=filter_type.StringFilter(
                        match_type=getattr(
                            filter_type.StringFilter.MatchType, item["match_type"]
                        ),
                        value=item["string_value"],
                        case_sensitive=item["case_sensitive"],
                    ),
                )
            )
        )

    if not expressions:
        return None
    if len(expressions) == 1:
        return expressions[0]
    return expression_type(and_group=expression_list_type(expressions=expressions))


def _report_response_to_dict(property_id: str, response: Any) -> dict[str, Any]:
    dimension_headers = [header.name for header in response.dimension_headers]
    metric_headers = [header.name for header in response.metric_headers]
    rows = []
    for row in response.rows:
        rows.append(
            {
                "dimensions": {
                    name: value.value
                    for name, value in zip(dimension_headers, row.dimension_values)
                },
                "metrics": {
                    name: value.value
                    for name, value in zip(metric_headers, row.metric_values)
                },
            }
        )

    return {
        "property_id": property_id,
        "dimension_headers": dimension_headers,
        "metric_headers": metric_headers,
        "rows": rows,
        "row_count": response.row_count,
        "property_quota": _proto_to_dict(getattr(response, "property_quota", None)),
    }


def _proto_to_dict(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        proto = value._pb if hasattr(value, "_pb") else value
        return MessageToDict(proto, preserving_proto_field_name=True)
    except Exception:
        return {"value": str(value)}


def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value)
