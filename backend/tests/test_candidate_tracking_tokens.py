import os
import unittest

from fastapi import HTTPException

from backend.core.config import get_settings
from backend.core.security import create_candidate_tracking_token, decode_candidate_tracking_token


class CandidateTrackingTokenTests(unittest.TestCase):
    def setUp(self):
        os.environ["JWT_SECRET"] = "unit-test-secret-that-is-long-enough"
        os.environ["CANDIDATE_TRACKING_TOKEN_DAYS"] = "7"
        get_settings.cache_clear()

    def tearDown(self):
        get_settings.cache_clear()

    def test_candidate_tracking_token_round_trip(self):
        token = create_candidate_tracking_token("candidate-123", "job-456")

        payload = decode_candidate_tracking_token(token)

        self.assertEqual(payload["purpose"], "candidate_tracking")
        self.assertEqual(payload["candidate_id"], "candidate-123")
        self.assertEqual(payload["job_id"], "job-456")

    def test_rejects_non_tracking_token_payload(self):
        token = create_candidate_tracking_token("candidate-123")
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

        with self.assertRaises(HTTPException):
            decode_candidate_tracking_token(tampered)


if __name__ == "__main__":
    unittest.main()
