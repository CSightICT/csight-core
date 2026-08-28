"""Loopback-only HTTP boundary for the host-native E3 Vision runtime."""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, cast

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from infra.vision_e3.runtime import (
    EXPECTED_TASK,
    MODEL_PACKAGE_DIRECTORY,
    E3VisionRuntime,
    VisionImageInputError,
    canonical_response,
)


def _positive_integer(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


def _runtime(request: Request) -> E3VisionRuntime:
    return cast(E3VisionRuntime, request.app.state.runtime)


def _authorize(request: Request) -> None:
    expected = os.getenv("VISION_E3_API_KEY", "").strip()
    if not expected:
        return
    supplied = request.headers.get("Authorization", "")
    if not secrets.compare_digest(supplied, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Vision service authentication failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    checkpoint_value = os.getenv("VISION_E3_CHECKPOINT_PATH", "").strip()
    if not checkpoint_value:
        raise RuntimeError("VISION_E3_CHECKPOINT_PATH is required")
    package_value = os.getenv("VISION_E3_PACKAGE_DIRECTORY", "").strip()
    package_directory = Path(package_value) if package_value else MODEL_PACKAGE_DIRECTORY
    runtime = E3VisionRuntime(
        checkpoint_path=Path(checkpoint_value),
        package_directory=package_directory,
        device_name=os.getenv("VISION_E3_DEVICE", "auto").strip().lower(),
    )
    if os.getenv("VISION_E3_WARMUP", "true").strip().lower() == "true":
        await run_in_threadpool(runtime.warmup)
    app.state.runtime = runtime
    yield


app = FastAPI(
    title="CSight E3 Vision runtime",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health")
def health(request: Request) -> dict[str, object]:
    _authorize(request)
    return _runtime(request).health()


@app.post("/v1/vision/analyze")
async def analyze(
    request: Request,
    file: Annotated[UploadFile, File()],
    task: Annotated[str, Form()],
) -> JSONResponse:
    _authorize(request)
    if task != EXPECTED_TASK:
        raise HTTPException(status_code=422, detail="unsupported Vision task")
    content_type = (file.content_type or "").lower()
    max_image_bytes = _positive_integer("VISION_E3_MAX_IMAGE_BYTES", 10 * 1024 * 1024)
    image_bytes = await file.read(max_image_bytes + 1)
    await file.close()
    if not image_bytes or len(image_bytes) > max_image_bytes:
        raise HTTPException(status_code=413, detail="image is empty or exceeds the service limit")
    try:
        prediction = await run_in_threadpool(
            _runtime(request).predict,
            image_bytes=image_bytes,
            content_type=content_type,
        )
    except VisionImageInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return JSONResponse(canonical_response(_runtime(request), prediction))
