import os
import unittest
from unittest import mock

from src import observability
from src.config import DEFAULT_MODEL_CONTEXT_WINDOW, get_model_context_window
from src.observability import (
    attach_model_step_metrics,
    build_model_step_metrics,
    classify_tool_result_hit,
    log_tool_data_hits,
)


class TestGetModelContextWindow(unittest.TestCase):
    def test_default_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_MODEL_CONTEXT_WINDOW", None)
            self.assertEqual(get_model_context_window(), DEFAULT_MODEL_CONTEXT_WINDOW)

    def test_valid_value(self):
        with mock.patch.dict(os.environ, {"AGENT_MODEL_CONTEXT_WINDOW": "200000"}):
            self.assertEqual(get_model_context_window(), 200000)

    def test_non_integer_falls_back_with_warning(self):
        with mock.patch.dict(os.environ, {"AGENT_MODEL_CONTEXT_WINDOW": "lots"}):
            with mock.patch("builtins.print") as printed:
                self.assertEqual(
                    get_model_context_window(), DEFAULT_MODEL_CONTEXT_WINDOW
                )
            printed.assert_called_once()

    def test_non_positive_falls_back_with_warning(self):
        with mock.patch.dict(os.environ, {"AGENT_MODEL_CONTEXT_WINDOW": "0"}):
            with mock.patch("builtins.print") as printed:
                self.assertEqual(
                    get_model_context_window(), DEFAULT_MODEL_CONTEXT_WINDOW
                )
            printed.assert_called_once()


class TestBuildModelStepMetrics(unittest.TestCase):
    def test_payload_keys_and_values(self):
        metrics = build_model_step_metrics(
            step_input_tokens=1000,
            step_output_tokens=200,
            cumulative_tokens_in=5000,
            cumulative_tokens_out=900,
            cumulative_cost_eur=0.0123,
            model_context_window=128000,
        )
        self.assertEqual(
            metrics,
            {
                "step_input_tokens": 1000,
                "step_output_tokens": 200,
                "cumulative_tokens_in": 5000,
                "cumulative_tokens_out": 900,
                "cumulative_cost_eur": 0.0123,
                "model_context_window": 128000,
                "context_window_pct": 0.78,
            },
        )

    def test_pct_uses_step_tokens_not_cumulative(self):
        # Trimmed-prompt semantics: utilization reflects this call's prompt
        # even when the cumulative ledger is far larger.
        metrics = build_model_step_metrics(
            step_input_tokens=64000,
            step_output_tokens=10,
            cumulative_tokens_in=1_000_000,
            cumulative_tokens_out=500_000,
            cumulative_cost_eur=1.0,
            model_context_window=128000,
        )
        self.assertEqual(metrics["context_window_pct"], 50.0)

    def test_pct_rounded_to_two_decimals(self):
        metrics = build_model_step_metrics(
            step_input_tokens=1,
            step_output_tokens=0,
            cumulative_tokens_in=1,
            cumulative_tokens_out=0,
            cumulative_cost_eur=0.0,
            model_context_window=3,
        )
        self.assertEqual(metrics["context_window_pct"], 33.33)

    def test_zero_window_yields_zero_pct(self):
        metrics = build_model_step_metrics(
            step_input_tokens=100,
            step_output_tokens=10,
            cumulative_tokens_in=100,
            cumulative_tokens_out=10,
            cumulative_cost_eur=0.0,
            model_context_window=0,
        )
        self.assertEqual(metrics["context_window_pct"], 0.0)

    def test_values_are_numeric_only(self):
        metrics = build_model_step_metrics(
            step_input_tokens=10,
            step_output_tokens=5,
            cumulative_tokens_in=10,
            cumulative_tokens_out=5,
            cumulative_cost_eur=0.001,
            model_context_window=128000,
        )
        for key, value in metrics.items():
            self.assertIsInstance(value, (int, float), key)


class TestAttachModelStepMetrics(unittest.TestCase):
    METRICS = {"step_input_tokens": 1, "context_window_pct": 0.0}

    def test_noop_when_langsmith_absent(self):
        with mock.patch.object(observability, "get_current_run_tree", None):
            self.assertIsNone(attach_model_step_metrics(self.METRICS))

    def test_noop_when_no_active_run(self):
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=None
        ):
            self.assertIsNone(attach_model_step_metrics(self.METRICS))

    def test_attaches_to_current_run_only(self):
        run = mock.Mock()
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(observability, "_get_feedback_client", return_value=None):
            attach_model_step_metrics(self.METRICS)
        run.add_metadata.assert_called_once_with(self.METRICS)
        run.patch.assert_called_once_with()

    def test_swallows_exceptions_with_warning(self):
        run = mock.Mock()
        run.add_metadata.side_effect = RuntimeError("boom")
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(
            observability, "_get_feedback_client"
        ) as get_client:
            with mock.patch("builtins.print") as printed:
                self.assertIsNone(attach_model_step_metrics(self.METRICS))
            printed.assert_called_once()
        run.patch.assert_not_called()
        # Feedback is skipped when metadata attachment fails.
        get_client.assert_not_called()


class TestStepMetricFeedback(unittest.TestCase):
    METRICS = {
        "step_input_tokens": 1000,
        "step_output_tokens": 200,
        "cumulative_tokens_in": 5000,
        "cumulative_tokens_out": 900,
        "cumulative_cost_eur": 0.0123,
        "model_context_window": 128000,
        "context_window_pct": 0.78,
    }

    def test_mirrors_chartable_keys_as_feedback(self):
        run = mock.Mock()
        client = mock.Mock()
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            attach_model_step_metrics(self.METRICS)

        logged = {
            call.kwargs["key"]: call.kwargs["score"]
            for call in client.create_feedback.call_args_list
        }
        self.assertEqual(
            logged,
            {
                "context_window_pct": 0.78,
                "cumulative_cost_eur": 0.0123,
                "step_input_tokens": 1000,
            },
        )
        for call in client.create_feedback.call_args_list:
            self.assertEqual(call.kwargs["run_id"], run.id)
            self.assertEqual(call.kwargs["trace_id"], run.trace_id)

    def test_feedback_failure_is_swallowed_per_key(self):
        run = mock.Mock()
        client = mock.Mock()
        client.create_feedback.side_effect = RuntimeError("boom")
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            with mock.patch("builtins.print") as printed:
                self.assertIsNone(attach_model_step_metrics(self.METRICS))
        # One warning per chartable key; metadata attachment is unaffected.
        self.assertEqual(printed.call_count, 3)
        run.add_metadata.assert_called_once_with(self.METRICS)

    def test_noop_without_client(self):
        run = mock.Mock()
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(observability, "Client", None), mock.patch.object(
            observability, "_feedback_client", None
        ):
            attach_model_step_metrics(self.METRICS)
        run.add_metadata.assert_called_once_with(self.METRICS)

    def test_client_creation_failure_cached_as_noop(self):
        failing_client_cls = mock.Mock(side_effect=RuntimeError("no api key"))
        with mock.patch.object(
            observability, "Client", failing_client_cls
        ), mock.patch.object(observability, "_feedback_client", None):
            with mock.patch("builtins.print") as printed:
                self.assertIsNone(observability._get_feedback_client())
                self.assertIsNone(observability._get_feedback_client())
            # Warned once, then cached the failure instead of retrying.
            printed.assert_called_once()
            failing_client_cls.assert_called_once()


class TestClassifyToolResultHit(unittest.TestCase):
    def test_data_rows_are_a_hit(self):
        self.assertEqual(classify_tool_result_hit("id | name\n1 | Alice"), 1.0)

    def test_table_list_is_a_hit(self):
        self.assertEqual(classify_tool_result_hit("customers, orders"), 1.0)

    def test_miss_markers(self):
        for content in (
            "No tables found.",
            "No user-facing tables found.",
            "Table 'foo' does not exist.",
            "No results found.",
            "Error: Only SELECT queries are allowed.",
            "Query error: no such column: foo",
            '{"rows": [], "rowCount": 0}',
            "",
            "   ",
        ):
            self.assertEqual(classify_tool_result_hit(content), 0.0, content)

    def test_list_content_blocks(self):
        self.assertEqual(classify_tool_result_hit(["row1", "row2"]), 1.0)
        self.assertEqual(classify_tool_result_hit([]), 0.0)


class _FakeToolMessage:
    def __init__(self, name, content):
        self.name = name
        self.content = content


class TestLogToolDataHits(unittest.TestCase):
    def test_logs_one_score_per_tool_message(self):
        run = mock.Mock()
        client = mock.Mock()
        messages = [
            _FakeToolMessage("query_database", "id | total\n1 | 9.99"),
            _FakeToolMessage("query_database", "No results found."),
        ]
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            log_tool_data_hits(messages)

        calls = client.create_feedback.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [(c.kwargs["key"], c.kwargs["score"], c.kwargs["comment"]) for c in calls],
            [
                ("data_hit", 1.0, "tool: query_database"),
                ("data_hit", 0.0, "tool: query_database"),
            ],
        )

    def test_noop_without_run_or_client(self):
        messages = [_FakeToolMessage("list_tables", "customers")]
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=None
        ):
            self.assertIsNone(log_tool_data_hits(messages))
        run = mock.Mock()
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(
            observability, "_get_feedback_client", return_value=None
        ):
            self.assertIsNone(log_tool_data_hits(messages))

    def test_feedback_failure_is_swallowed(self):
        run = mock.Mock()
        client = mock.Mock()
        client.create_feedback.side_effect = RuntimeError("boom")
        with mock.patch.object(
            observability, "get_current_run_tree", return_value=run
        ), mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            with mock.patch("builtins.print") as printed:
                log_tool_data_hits([_FakeToolMessage("list_tables", "customers")])
            printed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
