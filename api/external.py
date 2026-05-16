from __future__ import annotations

import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.support import require_identity, resolve_image_base_url
from services.content_filter import check_request
from services.image_task_service import image_task_service
from services.log_service import LoggedCall
from services.protocol import openai_v1_image_generations


class ExternalImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str = "gpt-image-2"
    n: int = Field(default=1, ge=1, le=4)
    size: str | None = None
    response_format: str = "url"
    async_mode: bool = False
    client_task_id: str | None = None


def _normalize_response_format(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"url", "b64_json"}:
        return normalized
    raise HTTPException(status_code=400, detail={"error": "response_format must be url or b64_json"})


async def _check_prompt_or_log(call: LoggedCall, prompt: str) -> None:
    try:
        await run_in_threadpool(check_request, prompt)
    except HTTPException as exc:
        call.log("调用失败", status="failed", error=str(exc.detail))
        raise


def _task_id(base: str | None, index: int) -> str:
    prefix = str(base or "").strip() or f"external-{int(time.time() * 1000)}"
    return prefix if index == 1 else f"{prefix}-{index}"


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/external/images/generations")
    async def generate_external_image(
        body: ExternalImageGenerationRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        response_format = _normalize_response_format(body.response_format)
        call = LoggedCall(identity, "/api/external/images/generations", body.model, "外部文生图", request_text=body.prompt)
        await _check_prompt_or_log(call, body.prompt)

        if body.async_mode:
            tasks = []
            for index in range(1, body.n + 1):
                try:
                    task = await run_in_threadpool(
                        image_task_service.submit_generation,
                        identity,
                        client_task_id=_task_id(body.client_task_id, index),
                        prompt=body.prompt,
                        model=body.model,
                        size=body.size,
                        base_url=resolve_image_base_url(request),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
                tasks.append(task)
            return {"ok": True, "mode": "async", "tasks": tasks}

        payload = {
            "prompt": body.prompt,
            "model": body.model,
            "n": body.n,
            "size": body.size,
            "response_format": response_format,
            "base_url": resolve_image_base_url(request),
        }
        result = await call.run(openai_v1_image_generations.handle, payload)
        return {"ok": True, "mode": "sync", **result}

    return router
