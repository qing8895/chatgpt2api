import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class PrivateSolverTests(unittest.TestCase):
    def setUp(self):
        # Browser I/O is isolated; these tests exercise HTTP validation and fail-closed behavior.
        fake = types.ModuleType("playwright.async_api")
        fake.async_playwright = None
        stealth = types.ModuleType("playwright_stealth")
        stealth.Stealth = None
        spec = importlib.util.spec_from_file_location("solver_test_app", Path(__file__).parents[1] / "sentinel_solver/app.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.async_api": fake, "playwright_stealth": stealth}), \
             patch.dict(os.environ, {"SENTINEL_SOLVER_KEY": "private-key", "SENTINEL_SOLVER_TIMEZONE": "Europe/Berlin"}):
            spec.loader.exec_module(self.module)
        self.module.page = AsyncMock()
        self.client = TestClient(self.module.app)
        self.headers = {"Authorization": "Bearer private-key"}

    def test_every_endpoint_requires_key(self):
        for endpoint in ("/health", "/v1/prepare", "/v1/turnstile"):
            method = self.client.get if endpoint == "/health" else self.client.post
            self.assertEqual(method(endpoint).status_code, 401)

    def test_account_data_and_prompts_are_rejected(self):
        for extra in ("token", "cookie", "prompt", "access_token", "requirements"):
            response = self.client.post("/v1/turnstile", headers=self.headers,
                json={"p": "gAAAAACxxx", "dx": "challenge", extra: "private-data"})
            self.assertEqual(response.status_code, 422)
            response = self.client.post("/v1/prepare", headers=self.headers, json={extra: "private-data"})
            self.assertEqual(response.status_code, 422)
        self.module.page.evaluate.assert_not_awaited()

    def test_challenge_error_tokens_are_not_accepted(self):
        import base64
        for token in ("", "123", "gAAAAACxxx", base64.b64encode(b"12: TypeError").decode()):
            self.module.page.evaluate.return_value = token
            response = self.client.post("/v1/turnstile", headers=self.headers,
                json={"p": "gAAAAACxxx", "dx": "challenge"})
            self.assertEqual(response.status_code, 503)

    def test_real_browser_result_is_returned(self):
        import base64
        token = base64.b64encode(b"browser-challenge-result").decode()
        self.module.page.evaluate.return_value = token
        response = self.client.post("/v1/turnstile", headers=self.headers,
            json={"p": "gAAAAACxxx", "dx": "challenge"})
        self.assertEqual(response.json(), {"token": token})
