import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from services.account_service import AccountService
from services.openai_backend_api import AutoImageModelNotFoundError, ChatRequirements, OpenAIBackendAPI
from services.protocol.conversation import ConversationRequest, _generate_single_image, ImageGenerationError
from services.storage.json_storage import JSONStorageBackend
from utils.helper import UpstreamHTTPError
from utils.pow import build_pow_config, build_proof_token, fnv1a_32


class SentinelHandshakeTests(unittest.TestCase):
    def backend(self):
        backend = OpenAIBackendAPI.__new__(OpenAIBackendAPI)
        backend.access_token = "private-account-token"
        backend.base_url = "https://chatgpt.com"
        backend.session = MagicMock()
        backend.session.headers = {}
        backend.user_agent = "old"
        backend.pow_script_sources = []
        backend.pow_data_build = ""
        return backend

    def test_pow_uses_fnv_and_keeps_browser_config(self):
        config = build_pow_config("browser-ua")
        self.assertEqual(len(config), 25)
        p = "gAAAAAC" + base64.b64encode(json.dumps(config).encode()).decode()
        result = build_proof_token("seed", "f", "ignored", source_p=p)
        self.assertTrue(result.endswith("~S"))
        encoded = result[7:-2]
        self.assertLessEqual(fnv1a_32("seed" + encoded)[0], "f")
        proof = json.loads(base64.b64decode(encoded))
        self.assertEqual(proof[4:], config[4:9] + [proof[9]] + config[10:])
        self.assertEqual(fnv1a_32("hello"), "888d766e")

    def test_finalize_fields_and_solver_privacy(self):
        backend = self.backend()
        config = build_pow_config("real-chromium")
        p = "gAAAAAC" + base64.b64encode(json.dumps(config).encode()).decode()
        environment = {"p": p, "user_agent": "real-chromium", "sec_ch_ua": "Chromium",
                       "platform": "Linux", "timezone": "Europe/Berlin", "timezone_offset_min": -120}
        backend.session.post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"prepare_token": "prepare",
                "proofofwork": {"required": True, "seed": "seed", "difficulty": "f"},
                "turnstile": {"required": True, "dx": "challenge"}}),
            MagicMock(status_code=200, json=lambda: {"token": "final"}),
        ]
        with patch("services.openai_backend_api.solver_request", side_effect=[environment, {"token": "answer"}]) as solver:
            result = backend._get_chat_requirements()
        self.assertEqual(result.token, "final")
        self.assertEqual(solver.call_args_list[1].args, ("/v1/turnstile", {"dx": "challenge", "p": p}))
        body = backend.session.post.call_args.kwargs["json"]
        self.assertEqual(set(body), {"prepare_token", "proofofwork", "turnstile"})
        self.assertTrue(body["proofofwork"].endswith("~S"))
        self.assertEqual(body["turnstile"], "answer")
        self.assertEqual(backend.session.headers["User-Agent"], "real-chromium")

    def test_only_exact_auto_image_404_is_classified(self):
        for model, status, body, special in [
            ("auto", 404, {"detail": "Model not found"}, True),
            ("other", 404, {"detail": "Model not found"}, False),
            ("auto", 404, {"detail": "Model not found "}, False),
            ("auto", 404, {"error": "Model not found"}, False),
            ("auto", 400, {"detail": "Model not found"}, False),
            ("auto", 404, "Model not found", False),
        ]:
            with self.subTest(model=model, status=status, body=body):
                backend = self.backend()
                backend._image_model_settings = lambda _: (model, "")
                backend._image_headers = lambda *args: {}
                backend.session.post.return_value = MagicMock(status_code=status, json=lambda: body, headers={})
                with self.assertRaises(UpstreamHTTPError) as raised:
                    backend._start_image_generation("prompt", ChatRequirements("t"), "c", "model")
                self.assertEqual(isinstance(raised.exception, AutoImageModelNotFoundError), special)

    def test_cooldown_expires_without_mutating_quota_or_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AccountService(JSONStorageBackend(Path(directory) / "accounts.json"))
            service.add_accounts(["a", "b"])
            for token in ("a", "b"):
                service.update_account(token, {"status": "正常", "quota": 7})
            before = service.get_account("a")
            with patch("services.account_service.time.monotonic", return_value=100):
                service.cool_down_image_account("a")
                self.assertEqual(service._list_ready_candidate_tokens(), ["b"])
            self.assertEqual(service.get_account("a"), before)
            with patch("services.account_service.time.monotonic", return_value=700):
                self.assertEqual(set(service._list_ready_candidate_tokens()), {"a", "b"})

    def test_model_failure_shares_existing_retry_budget(self):
        error = AutoImageModelNotFoundError("/backend-api/f/conversation", 404, {"detail": "Model not found"})
        with patch("services.protocol.conversation.account_service") as accounts, \
             patch("services.protocol.conversation.OpenAIBackendAPI"), \
             patch("services.protocol.conversation.stream_image_outputs", side_effect=error):
            accounts.get_available_access_token.side_effect = [f"account-{i}" for i in range(5)]
            accounts.get_account.return_value = {}
            with self.assertRaises(ImageGenerationError):
                _generate_single_image(ConversationRequest(prompt="test", model="gpt-image-2"), 1, 1)
            self.assertEqual(accounts.get_available_access_token.call_count, 5)
            self.assertEqual(accounts.cool_down_image_account.call_count, 5)
            self.assertEqual(accounts.release_image_slot.call_count, 5)
            accounts.mark_image_result.assert_not_called()

    def test_download_requires_complete_image(self):
        backend = self.backend()
        buffer = io.BytesIO()
        Image.new("RGB", (256, 256)).save(buffer, format="BMP")
        payload = buffer.getvalue()
        backend.session.get.return_value = MagicMock(status_code=200, content=payload)
        self.assertEqual(backend.download_image_bytes(["https://image"]), [payload])
        backend.session.get.return_value.content = payload[:100]
        with self.assertRaises(OSError):
            backend.download_image_bytes(["https://truncated"])
