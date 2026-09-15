from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from services.config import config
from services.openai_backend_api import OpenAIBackendAPI
from services.protocol.conversation import ConversationRequest, stream_codex_image_outputs


class _CodexResponse:
    headers = {"content-type": "text/event-stream"}
    status = 200

    def __init__(self, body: bytes = b"data: [DONE]\n\n") -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class Image25Tests(unittest.TestCase):
    def test_codex_request_preserves_image_25_tool_model(self) -> None:
        backend = OpenAIBackendAPI(access_token="test-token")
        backend._ensure_codex_source_account = mock.Mock()
        original_main_model = config.data.get("codex_images_main_model")
        config.data["codex_images_main_model"] = "gpt-5.6-luna"
        try:
            with (
                mock.patch.dict(os.environ, {"CHATGPT2API_IMAGES_MAIN_MODEL": ""}),
                mock.patch(
                    "services.openai_backend_api.urllib.request.urlopen",
                    return_value=_CodexResponse(),
                ) as urlopen,
            ):
                list(backend.iter_codex_image_response_events(
                    prompt="draw a red cup",
                    model="gpt-image-2.5-flare-2026-09-08",
                    size="1536x864",
                    quality="max",
                ))

            request = urlopen.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload["model"], "gpt-5.6-luna")
            self.assertEqual(payload["tools"][0]["model"], "gpt-image-2.5-flare-2026-09-08")
            self.assertEqual(payload["tools"][0]["size"], "1536x864")
            self.assertEqual(payload["tools"][0]["quality"], "max")
        finally:
            backend.close()
            if original_main_model is None:
                config.data.pop("codex_images_main_model", None)
            else:
                config.data["codex_images_main_model"] = original_main_model

    def test_main_model_environment_override(self) -> None:
        with mock.patch.dict(os.environ, {"CHATGPT2API_IMAGES_MAIN_MODEL": "gpt-5.6-sol"}):
            self.assertEqual(config.codex_images_main_model, "gpt-5.6-sol")

    def test_conversation_forwards_selected_image_model(self) -> None:
        backend = mock.Mock()
        backend.iter_codex_image_response_events.return_value = [{
            "type": "response.output_item.done",
            "item": {"type": "image_generation_call", "result": "aGVsbG8="},
        }]
        request = ConversationRequest(
            prompt="draw a red cup",
            model="gpt-image-2.5-sunburst",
            quality="xhigh",
        )

        outputs = list(stream_codex_image_outputs(backend, request))

        self.assertEqual(len(outputs), 1)
        backend.iter_codex_image_response_events.assert_called_once_with(
            prompt="draw a red cup",
            images=[],
            size=None,
            quality="xhigh",
            model="gpt-image-2.5-sunburst",
        )


if __name__ == "__main__":
    unittest.main()
