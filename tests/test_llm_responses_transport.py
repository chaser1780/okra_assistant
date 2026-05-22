from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from multiagent_utils import describe_api_failure, is_retryable_provider_status, responses_endpoint, responses_headers


class LlmResponsesTransportTests(unittest.TestCase):
    def test_responses_endpoint_accepts_v1_base_url(self):
        self.assertEqual(responses_endpoint({"base_url": "https://api.vip1129.cc/v1"}), "https://api.vip1129.cc/v1/responses")

    def test_responses_endpoint_does_not_duplicate_path(self):
        self.assertEqual(responses_endpoint({"base_url": "https://api.vip1129.cc/v1/responses"}), "https://api.vip1129.cc/v1/responses")

    def test_responses_headers_use_sse_accept_for_stream(self):
        headers = responses_headers("sk-test", stream=True)
        self.assertEqual(headers["Authorization"], "Bearer sk-test")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "text/event-stream")

    def test_502_is_retryable_provider_failure(self):
        self.assertTrue(is_retryable_provider_status(502))
        self.assertIn("Retryable HTTP 502", describe_api_failure(502, "bad gateway", "agent", "direct"))


if __name__ == "__main__":
    unittest.main()
