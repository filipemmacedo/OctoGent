from __future__ import annotations

import re
from datetime import date
from typing import Any, Sequence

from ga4_mcp_server.errors import GA4ValidationError

_ACCOUNT_RE = re.compile(r"^(?:accounts/)?([0-9]+)$")
_PROPERTY_RE = re.compile(r"^(?:properties/)?([0-9]+)$")
_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:]{0,127}$")
_RELATIVE_DATE_RE = re.compile(r"^[0-9]{1,4}daysAgo$")
_ALLOWED_MATCH_TYPES = {
    "EXACT",
    "BEGINS_WITH",
    "ENDS_WITH",
    "CONTAINS",
    "FULL_REGEXP",
    "PARTIAL_REGEXP",
}


def validate_account_resource(account: str | None) -> str | None:
    if account is None or not str(account).strip():
        return None
    match = _ACCOUNT_RE.match(str(account).strip())
    if not match:
        raise GA4ValidationError(
            "account must be a numeric account ID or resource name like accounts/123."
        )
    return f"accounts/{match.group(1)}"


def validate_property_id(
    property_id: str | int | None,
    default_property_id: str | None = None,
) -> str:
    candidate = str(property_id or default_property_id or "").strip()
    match = _PROPERTY_RE.match(candidate)
    if not match:
        raise GA4ValidationError(
            "property_id must be a numeric GA4 property ID or resource name like properties/123."
        )
    return match.group(1)


def validate_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = _validate_ga_date(start_date, "start_date")
    end = _validate_ga_date(end_date, "end_date")

    if _is_iso_date(start) and _is_iso_date(end):
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise GA4ValidationError("start_date must be on or before end_date.")

    return start, end


def validate_field_names(values: Sequence[str], field_type: str) -> list[str]:
    if not values:
        raise GA4ValidationError(f"{field_type} must contain at least one value.")

    validated: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not _FIELD_RE.match(value):
            raise GA4ValidationError(
                f"Invalid {field_type} value {value!r}. Use GA4 API field names only."
            )
        validated.append(value)
    return validated


def validate_filters(filters: Any | None) -> list[dict[str, Any]]:
    """Validate a small structured string-filter subset.

    Accepted shape:
      {"field_name": "country", "string_value": "Portugal", "match_type": "EXACT"}
    or a list of those objects. Multiple filters are combined with AND.
    """
    if filters is None:
        return []

    raw_filters = filters if isinstance(filters, list) else [filters]
    if not all(isinstance(item, dict) for item in raw_filters):
        raise GA4ValidationError("filters must be an object or list of objects.")

    validated: list[dict[str, Any]] = []
    for item in raw_filters:
        field_name = str(item.get("field_name", "")).strip()
        string_value = item.get("string_value")
        match_type = str(item.get("match_type", "EXACT")).strip().upper()
        case_sensitive = bool(item.get("case_sensitive", False))

        if not _FIELD_RE.match(field_name):
            raise GA4ValidationError("filters.field_name must be a valid GA4 field name.")
        if string_value is None or not str(string_value).strip():
            raise GA4ValidationError("filters.string_value must be a non-empty string.")
        if match_type not in _ALLOWED_MATCH_TYPES:
            raise GA4ValidationError(
                "filters.match_type must be one of "
                + ", ".join(sorted(_ALLOWED_MATCH_TYPES))
                + "."
            )

        validated.append(
            {
                "field_name": field_name,
                "string_value": str(string_value),
                "match_type": match_type,
                "case_sensitive": case_sensitive,
            }
        )

    return validated


def _validate_ga_date(value: str, name: str) -> str:
    text = str(value).strip()
    if text in {"today", "yesterday"} or _RELATIVE_DATE_RE.match(text):
        return text
    if _is_iso_date(text):
        return text
    raise GA4ValidationError(
        f"{name} must be YYYY-MM-DD, today, yesterday, or a value like 7daysAgo."
    )


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
