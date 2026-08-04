"""Unit tests for Gemini ops alert service (log + persist + webhook + dedup)."""
import os
import unittest
from unittest import mock

from services.ops_alert_service import (
    PARTIAL_ANALYSIS,
    QUOTA_EXHAUSTED,
    classify_gemini_error,
    report_gemini_failure,
    reset_dedup_state,
)


class OpsAlertServiceTest(unittest.TestCase):
    def setUp(self):
        reset_dedup_state()
        self.env = {
            "OPS_ALERTS_ENABLED": "true",
            "OPS_ALERT_WEBHOOK_URL": "https://hooks.example.test/gemini",
            "OPS_ALERT_COOLDOWN_SECONDS": "1800",
        }
        self.env_patcher = mock.patch.dict(os.environ, self.env, clear=False)
        self.env_patcher.start()
        self.persist_patcher = mock.patch(
            "services.ops_alert_service._persist_ops_alert",
            return_value=42,
        )
        self.mock_persist = self.persist_patcher.start()

    def tearDown(self):
        self.persist_patcher.stop()
        self.env_patcher.stop()
        reset_dedup_state()

    def test_classify_quota_and_model(self):
        self.assertEqual(classify_gemini_error("429 quota exceeded"), QUOTA_EXHAUSTED)
        self.assertEqual(
            classify_gemini_error("404 models/gemini-1.5-flash is not found"),
            "model_error",
        )

    @mock.patch("services.ops_alert_service.requests.post")
    def test_webhook_posted_once_then_deduped(self, mock_post):
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with mock.patch("services.ops_alert_service._mark_webhook_sent") as mock_mark:
            first = report_gemini_failure(
                failure_class=PARTIAL_ANALYSIS,
                message="partial for test",
                severity="warning",
                bill_identifier="119-HR23",
                bill_id=1,
                completion_percentage=18.2,
                source="analyzer",
            )
            second = report_gemini_failure(
                failure_class=PARTIAL_ANALYSIS,
                message="partial for test again",
                severity="warning",
                bill_identifier="119-HR23",
                bill_id=1,
                completion_percentage=18.2,
                source="routes",
            )

        self.assertTrue(first["logged"])
        self.assertTrue(first["persisted"])
        self.assertEqual(first["ops_alert_id"], 42)
        self.assertTrue(first["webhook_attempted"])
        self.assertTrue(first["webhook_sent"])
        self.assertFalse(first["skipped_dedup"])
        mock_mark.assert_called()

        self.assertTrue(second["logged"])
        self.assertTrue(second["persisted"])
        self.assertTrue(second["skipped_dedup"])
        self.assertFalse(second["webhook_attempted"])
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(self.mock_persist.call_count, 2)

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://hooks.example.test/gemini")
        payload = kwargs["json"]
        self.assertEqual(payload["event"], "gemini_failure")
        self.assertEqual(payload["failure_class"], PARTIAL_ANALYSIS)
        self.assertEqual(payload["bill_identifier"], "119-HR23")
        self.assertNotIn("api_key", str(payload).lower())
        self.assertEqual(kwargs["timeout"], 5)

    @mock.patch("services.ops_alert_service.requests.post")
    def test_persist_without_webhook_url(self, mock_post):
        with mock.patch.dict(os.environ, {"OPS_ALERT_WEBHOOK_URL": ""}, clear=False):
            status = report_gemini_failure(
                failure_class=PARTIAL_ANALYSIS,
                message="no url",
                bill_identifier="119-HR24",
                source="analyzer",
            )
        self.assertTrue(status["logged"])
        self.assertTrue(status["persisted"])
        self.assertFalse(status["webhook_attempted"])
        mock_post.assert_not_called()
        self.mock_persist.assert_called_once()

    @mock.patch("services.ops_alert_service.requests.post")
    def test_kill_switch_still_persists(self, mock_post):
        with mock.patch.dict(os.environ, {"OPS_ALERTS_ENABLED": "false"}, clear=False):
            status = report_gemini_failure(
                failure_class=PARTIAL_ANALYSIS,
                message="disabled",
                bill_identifier="119-HR25",
                source="analyzer",
            )
        self.assertTrue(status["alerts_disabled"])
        self.assertTrue(status["persisted"])
        self.assertFalse(status["webhook_attempted"])
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
