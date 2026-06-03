import os
import unittest

from fastapi import HTTPException

from backend.core.config import get_settings
from backend.routers import auth


class SignupGateTests(unittest.TestCase):
    def setUp(self):
        self.old_values = {key: os.environ.get(key) for key in ["SIGNUP_MODE", "PAID_SIGNUP_ACCESS_CODES"]}

    def tearDown(self):
        for key, value in self.old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        auth.settings = get_settings()

    def refresh_settings(self):
        get_settings.cache_clear()
        auth.settings = get_settings()

    def test_access_code_mode_blocks_missing_code(self):
        os.environ["SIGNUP_MODE"] = "access_code"
        os.environ["PAID_SIGNUP_ACCESS_CODES"] = "paid-123"
        self.refresh_settings()

        with self.assertRaises(HTTPException) as ctx:
            auth._validate_signup_access(None, "buyer@example.com", "")

        self.assertEqual(ctx.exception.status_code, 402)

    def test_access_code_mode_allows_configured_paid_code(self):
        os.environ["SIGNUP_MODE"] = "access_code"
        os.environ["PAID_SIGNUP_ACCESS_CODES"] = "paid-123,agency-456"
        self.refresh_settings()

        result = auth._validate_signup_access(None, "buyer@example.com", "agency-456")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
