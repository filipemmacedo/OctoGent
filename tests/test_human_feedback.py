import json
import unittest
from unittest import mock

from src import observability
from src.config import build_graph_config
from src.observability import (
    create_answer_example,
    delete_user_feedback,
    log_user_feedback,
    user_feedback_id,
)


class TestUserFeedbackId(unittest.TestCase):
    def test_stable_for_same_message(self):
        self.assertEqual(user_feedback_id("msg-1"), user_feedback_id("msg-1"))

    def test_distinct_for_different_messages(self):
        self.assertNotEqual(user_feedback_id("msg-1"), user_feedback_id("msg-2"))


class TestLogUserFeedback(unittest.TestCase):
    def test_noop_when_client_unavailable(self):
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=None
        ):
            self.assertFalse(
                log_user_feedback("run-1", 1.0, "great", "msg-1")
            )

    def test_creates_feedback_with_deterministic_id(self):
        client = mock.Mock()
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            self.assertTrue(log_user_feedback("run-1", 1.0, "great", "msg-1"))
        client.create_feedback.assert_called_once_with(
            run_id="run-1",
            trace_id="run-1",
            key="user_score",
            score=1.0,
            comment="great",
            feedback_id=user_feedback_id("msg-1"),
        )

    def test_falls_back_to_update_on_existing_feedback(self):
        client = mock.Mock()
        client.create_feedback.side_effect = RuntimeError("conflict")
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            self.assertTrue(log_user_feedback("run-1", 0.0, None, "msg-1"))
        client.create_feedback.assert_called_once_with(
            run_id="run-1",
            trace_id="run-1",
            key="user_score",
            score=0.0,
            comment=None,
            feedback_id=user_feedback_id("msg-1"),
        )
        client.update_feedback.assert_called_once_with(
            user_feedback_id("msg-1"),
            score=0.0,
            comment=None,
        )

    def test_updates_dataset_example_metadata_when_example_id_present(self):
        client = mock.Mock()
        client.read_example.return_value.metadata = {
            "app": "langgraph-governed-agent",
            "interface": "chainlit",
            "thread_id": "thread-1",
        }
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            self.assertTrue(
                log_user_feedback(
                    "run-1",
                    1.0,
                    "great",
                    "msg-1",
                    example_id="example-1",
                )
            )
        client.update_example.assert_called_once_with(
            example_id="example-1",
            metadata={
                "app": "langgraph-governed-agent",
                "interface": "chainlit",
                "thread_id": "thread-1",
                "user_score": 1.0,
                "user_feedback": "great",
                "message_id": "msg-1",
                "source_run_id": "run-1",
            },
        )

    def test_never_raises_when_create_and_update_fail(self):
        client = mock.Mock()
        client.create_feedback.side_effect = RuntimeError("down")
        client.update_feedback.side_effect = RuntimeError("down")
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            with mock.patch("builtins.print") as printed:
                self.assertFalse(log_user_feedback("run-1", 1.0, "", "msg-1"))
            printed.assert_called_once()


class TestCreateAnswerExample(unittest.TestCase):
    def test_noop_when_dataset_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(observability, "_get_feedback_client") as get_client:
                self.assertIsNone(
                    create_answer_example("hi", "hello", "thread-1", "msg-1", "run-1")
                )
        get_client.assert_not_called()

    def test_uses_configured_dataset_name_and_returns_example_id(self):
        client = mock.Mock()
        client.create_example.return_value.id = "example-1"
        with mock.patch.dict(
            "os.environ",
            {"LANGSMITH_FEEDBACK_DATASET_NAME": "User feedback"},
            clear=True,
        ):
            with mock.patch.object(
                observability, "_get_feedback_client", return_value=client
            ):
                example_id = create_answer_example(
                    "hi",
                    "hello",
                    "thread-1",
                    "msg-1",
                    "run-1",
                )

        self.assertEqual(example_id, "example-1")
        client.create_dataset.assert_not_called()
        client.create_example.assert_called_once_with(
            dataset_name="User feedback",
            inputs={"user_message": "hi"},
            outputs={"assistant_answer": "hello"},
            metadata={
                "app": observability.APP_NAME,
                "interface": "chainlit",
                "thread_id": "thread-1",
                "message_id": "msg-1",
                "source_run_id": "run-1",
            },
        )

    def test_dataset_id_takes_precedence(self):
        client = mock.Mock()
        client.create_example.return_value.id = "example-1"
        with mock.patch.dict(
            "os.environ",
            {
                "LANGSMITH_FEEDBACK_DATASET_ID": "dataset-id-1",
                "LANGSMITH_FEEDBACK_DATASET_NAME": "User feedback",
            },
            clear=True,
        ):
            with mock.patch.object(
                observability, "_get_feedback_client", return_value=client
            ):
                create_answer_example("hi", "hello", "thread-1", "msg-1", "run-1")

        self.assertEqual(
            client.create_example.call_args.kwargs["dataset_id"],
            "dataset-id-1",
        )
        self.assertNotIn("dataset_name", client.create_example.call_args.kwargs)


class TestDeleteUserFeedback(unittest.TestCase):
    def test_noop_when_client_unavailable(self):
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=None
        ):
            self.assertFalse(delete_user_feedback("msg-1"))

    def test_deletes_derived_feedback_id(self):
        client = mock.Mock()
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            self.assertTrue(delete_user_feedback("msg-1"))
        client.delete_feedback.assert_called_once_with(user_feedback_id("msg-1"))

    def test_never_raises_on_failure(self):
        client = mock.Mock()
        client.delete_feedback.side_effect = RuntimeError("down")
        with mock.patch.object(
            observability, "_get_feedback_client", return_value=client
        ):
            with mock.patch("builtins.print") as printed:
                self.assertFalse(delete_user_feedback("msg-1"))
            printed.assert_called_once()


class TestBuildGraphConfigRunId(unittest.TestCase):
    def test_run_id_included_when_provided(self):
        config = build_graph_config("t-1", interface="chainlit", run_id="rid-1")
        self.assertEqual(config["run_id"], "rid-1")

    def test_run_id_absent_by_default(self):
        config = build_graph_config("t-1", interface="chainlit")
        self.assertNotIn("run_id", config)


class TestNewInvocationConfig(unittest.TestCase):
    def test_fresh_run_id_per_invocation(self):
        import app

        run_id_1, config_1 = app._new_invocation_config("t-1")
        run_id_2, config_2 = app._new_invocation_config("t-1")
        self.assertNotEqual(run_id_1, run_id_2)
        self.assertEqual(config_1["run_id"], run_id_1)
        self.assertEqual(config_2["run_id"], run_id_2)
        self.assertEqual(config_1["configurable"]["thread_id"], "t-1")


class TestHitlStatusDetection(unittest.TestCase):
    def test_detects_chainlit_selected_status(self):
        import app

        self.assertTrue(app._is_hitl_status_output("**Selected:** Approve"))

    def test_does_not_treat_answer_as_status(self):
        import app

        self.assertFalse(app._is_hitl_status_output("Answer text"))


class TestSendMessageParenting(unittest.IsolatedAsyncioTestCase):
    async def test_default_parent_is_not_overwritten(self):
        import app

        created = {}

        class FakeMessage:
            def __init__(self, content, **kwargs):
                self.content = content
                self.kwargs = kwargs
                self.parent_id = "chainlit-run-parent"
                created["msg"] = self

            async def send(self):
                return self

        with mock.patch.object(app.cl, "Message", FakeMessage):
            msg = await app._send_message("answer")

        self.assertIs(msg, created["msg"])
        self.assertEqual(msg.parent_id, "chainlit-run-parent")

    async def test_explicit_parent_is_preserved(self):
        import app

        class FakeMessage:
            def __init__(self, content, **kwargs):
                self.parent_id = "chainlit-run-parent"

            async def send(self):
                return self

        with mock.patch.object(app.cl, "Message", FakeMessage):
            msg = await app._send_message("state", parent_id="user-msg")

        self.assertEqual(msg.parent_id, "user-msg")


def _make_data_layer():
    import app

    # Skip __init__ so no DB engine is created; tests patch the SQL surface.
    return app.LangSmithFeedbackDataLayer.__new__(app.LangSmithFeedbackDataLayer)


def _feedback(for_id="msg-1", value=1, comment=None, feedback_id="fb-1"):
    from chainlit.types import Feedback

    return Feedback(forId=for_id, value=value, comment=comment, id=feedback_id)


class TestLangSmithFeedbackDataLayer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import app

        self.app = app
        self.layer = _make_data_layer()
        self.app.ANSWER_RUN_IDS.clear()
        self.app.ANSWER_EXAMPLE_IDS.clear()
        self.super_upsert = mock.patch.object(
            self.app.SQLAlchemyDataLayer,
            "upsert_feedback",
            new=mock.AsyncMock(return_value="fb-1"),
        )
        self.super_delete = mock.patch.object(
            self.app.SQLAlchemyDataLayer,
            "delete_feedback",
            new=mock.AsyncMock(return_value=True),
        )
        self.super_upsert.start()
        self.super_delete.start()
        self.addCleanup(self.super_upsert.stop)
        self.addCleanup(self.super_delete.stop)

    async def test_thumbs_up_maps_to_score_one(self):
        self.app.ANSWER_RUN_IDS["msg-1"] = "run-1"
        with mock.patch.object(
            self.app, "log_user_feedback", return_value=True
        ) as log_fb:
            result = await self.layer.upsert_feedback(_feedback(value=1))
        self.assertEqual(result, "fb-1")
        log_fb.assert_called_once_with(
            run_id="run-1",
            score=1.0,
            comment=None,
            message_id="msg-1",
            example_id=None,
        )

    async def test_thumbs_down_maps_to_score_zero_with_comment(self):
        self.app.ANSWER_RUN_IDS["msg-1"] = "run-1"
        with mock.patch.object(
            self.app, "log_user_feedback", return_value=True
        ) as log_fb:
            await self.layer.upsert_feedback(_feedback(value=0, comment="wrong"))
        log_fb.assert_called_once_with(
            run_id="run-1",
            score=0.0,
            comment="wrong",
            message_id="msg-1",
            example_id=None,
        )

    async def test_passes_cached_example_id(self):
        self.app.ANSWER_RUN_IDS["msg-1"] = "run-1"
        self.app.ANSWER_EXAMPLE_IDS["msg-1"] = "example-1"
        with mock.patch.object(
            self.app, "log_user_feedback", return_value=True
        ) as log_fb:
            await self.layer.upsert_feedback(_feedback(value=1))
        log_fb.assert_called_once_with(
            run_id="run-1",
            score=1.0,
            comment=None,
            message_id="msg-1",
            example_id="example-1",
        )

    async def test_metadata_fallback_resolves_run_id(self):
        metadata = json.dumps({"langsmith_run_id": "run-from-db"})
        self.layer.execute_sql = mock.AsyncMock(
            return_value=[{"metadata": metadata}]
        )
        with mock.patch.object(
            self.app, "log_user_feedback", return_value=True
        ) as log_fb:
            await self.layer.upsert_feedback(_feedback())
        log_fb.assert_called_once_with(
            run_id="run-from-db",
            score=1.0,
            comment=None,
            message_id="msg-1",
            example_id=None,
        )

    async def test_run_step_parent_fallback_resolves_child_answer_run_id(self):
        # Chainlit's feedback `forId` is the auto on_message run step's id,
        # which has no row of its own in `steps` - only the answer message
        # persisted as its child does.
        answer_metadata = json.dumps({"langsmith_run_id": "run-from-child"})
        self.layer.execute_sql = mock.AsyncMock(
            side_effect=[
                [],  # no step row with id == forId (the run step)
                [{"metadata": answer_metadata}],  # child assistant_message
            ]
        )

        with mock.patch.object(
            self.app, "log_user_feedback", return_value=True
        ) as log_fb:
            await self.layer.upsert_feedback(_feedback(for_id="run-step-1"))

        log_fb.assert_called_once_with(
            run_id="run-from-child",
            score=1.0,
            comment=None,
            message_id="run-step-1",
            example_id=None,
        )

    async def test_status_message_fallback_resolves_next_answer_run_id(self):
        answer_metadata = json.dumps({"langsmith_run_id": "run-from-answer"})
        self.layer.execute_sql = mock.AsyncMock(
            side_effect=[
                [
                    {
                        "metadata": "{}",
                        "output": "**Selected:** Approve",
                        "threadId": "thread-1",
                        "createdAt": "2026-06-14T08:15:20Z",
                    }
                ],
                [
                    {
                        "id": "answer-1",
                        "metadata": answer_metadata,
                    }
                ],
            ]
        )

        with mock.patch.object(
            self.app, "log_user_feedback", return_value=True
        ) as log_fb:
            await self.layer.upsert_feedback(
                _feedback(for_id="approval-status-1", value=1)
            )

        log_fb.assert_called_once_with(
            run_id="run-from-answer",
            score=1.0,
            comment=None,
            message_id="approval-status-1",
            example_id=None,
        )

    async def test_non_status_message_without_metadata_stays_local_only(self):
        self.layer.execute_sql = mock.AsyncMock(
            return_value=[
                {
                    "metadata": "{}",
                    "output": "**State Inspector**",
                    "threadId": "thread-1",
                    "createdAt": "2026-06-14T08:15:29Z",
                }
            ]
        )

        with mock.patch.object(self.app, "log_user_feedback") as log_fb:
            with mock.patch("builtins.print") as printed:
                await self.layer.upsert_feedback(_feedback())

        log_fb.assert_not_called()
        printed.assert_called_once()

    async def test_unresolvable_message_is_local_only(self):
        self.layer.execute_sql = mock.AsyncMock(return_value=[])
        with mock.patch.object(self.app, "log_user_feedback") as log_fb:
            with mock.patch("builtins.print") as printed:
                result = await self.layer.upsert_feedback(_feedback())
        self.assertEqual(result, "fb-1")
        log_fb.assert_not_called()
        printed.assert_called_once()

    async def test_delete_forwards_to_langsmith(self):
        self.layer.execute_sql = mock.AsyncMock(
            return_value=[{"forId": "msg-1"}]
        )
        with mock.patch.object(
            self.app, "delete_user_feedback", return_value=True
        ) as del_fb:
            deleted = await self.layer.delete_feedback("fb-1")
        self.assertTrue(deleted)
        del_fb.assert_called_once_with("msg-1")

    async def test_delete_survives_lookup_failure(self):
        self.layer.execute_sql = mock.AsyncMock(side_effect=RuntimeError("db"))
        with mock.patch.object(self.app, "delete_user_feedback") as del_fb:
            deleted = await self.layer.delete_feedback("fb-1")
        self.assertTrue(deleted)
        del_fb.assert_not_called()


if __name__ == "__main__":
    unittest.main()
