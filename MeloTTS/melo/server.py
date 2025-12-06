from __future__ import annotations

"""
Korean TTS HTTP service for MeloTTS.

This module exposes a small, production-grade HTTP API that:

- Accepts Korean text and synthesis parameters over HTTPS (via a reverse proxy
  or Tailscale HTTPS on the hostname tts-server.your-tailnet.ts.net).
- Loads the MeloTTS Korean model **only for the lifetime of a single request**.
- Streams back synthesized audio as a WAV binary response.
- Optionally enforces an API key via the X-API-Key header.

Intended deployment (recommended):

- Run this service locally on the TTS host, e.g.:

      python -m melo.server

  or:

      uvicorn melo.server:app --host 0.0.0.0 --port 8000

- Front it with Tailscale's HTTPS listener on
  tts-server.your-tailnet.ts.net, or with a standard TLS reverse proxy.
"""

import base64
import io
import os
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from threading import Semaphore
from typing import Deque, Dict, List, Optional

import torch
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .simple_korean_tts import get_korean_tts_model


API_TITLE = "MeloTTS Korean TTS Service"
API_VERSION = "1.0.0"

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = int(os.environ.get("MELOTTS_SERVER_PORT", "8000"))

# If set, incoming requests must include X-API-Key matching this value.
API_KEY_ENV_VAR = "MELOTTS_API_KEY"

# Upper bound to protect the service against accidentally huge requests.
MAX_TEXT_LENGTH = 500  # characters

# Concurrency guard for TTS synthesis. This protects the host from being
# overwhelmed when multiple clients send requests simultaneously.
MAX_CONCURRENT_TTS = int(os.environ.get("MELOTTS_MAX_CONCURRENT_TTS", "4"))
_TTS_SEMAPHORE = Semaphore(MAX_CONCURRENT_TTS if MAX_CONCURRENT_TTS > 0 else 1)

# Simple in-process per-IP rate limiting (best-effort). This is intentionally
# lightweight and resets on process restart; for serious multi-instance
# deployments, prefer a shared limiter (e.g. API gateway, nginx, envoy).
RATE_LIMIT_MAX_PER_MIN = int(os.environ.get("MELOTTS_RATE_LIMIT_PER_MIN", "120"))
_RATE_LIMIT_WINDOW_SECS = 60.0
_rate_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def _enforce_rate_limit(client_ip: str) -> None:
    """Enforce a simple per-IP rate limit."""

    if RATE_LIMIT_MAX_PER_MIN <= 0:
        return

    now = time.time()
    bucket = _rate_buckets[client_ip]

    # Drop entries older than the window.
    while bucket and now - bucket[0] > _RATE_LIMIT_WINDOW_SECS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_MAX_PER_MIN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down and retry later.",
        )

    bucket.append(now)


# Structured logging: emit compact JSON lines suitable for ingestion by common
# log pipelines (e.g. journalctl, Loki, Datadog, etc.).
import logging


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            base.update(extra_data)
        return json.dumps(base, ensure_ascii=False)


logger = logging.getLogger("melotts.server")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(JsonLogFormatter())
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# Optional Prometheus metrics. If prometheus_client is not installed, the
# service continues to work without exporting metrics.
try:  # pragma: no cover - optional dependency
    from prometheus_client import (
        Counter,
        Histogram,
        CONTENT_TYPE_LATEST,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True

    REQUEST_LATENCY = Histogram(
        "melotts_request_latency_seconds",
        "HTTP request latency in seconds.",
        ["endpoint"],
    )
    REQUEST_COUNTER = Counter(
        "melotts_requests_total",
        "Total HTTP requests.",
        ["endpoint", "status"],
    )
    TTS_CHARACTERS = Counter(
        "melotts_tts_characters_total",
        "Total characters synthesized.",
        ["endpoint"],
    )
    TTS_FAILURES = Counter(
        "melotts_tts_failures_total",
        "Total failed synthesis attempts.",
        ["endpoint", "reason"],
    )
except Exception:  # pragma: no cover - metrics are optional
    PROMETHEUS_AVAILABLE = False
    REQUEST_LATENCY = None  # type: ignore[assignment]
    REQUEST_COUNTER = None  # type: ignore[assignment]
    TTS_CHARACTERS = None  # type: ignore[assignment]
    TTS_FAILURES = None  # type: ignore[assignment]


app = FastAPI(title=API_TITLE, version=API_VERSION)


class KoreanTTSRequest(BaseModel):
    text: str = Field(..., description="Korean text to synthesize.")
    speed: float = Field(
        1.0,
        gt=0.0,
        le=5.0,
        description="Playback speed multiplier (1.0 = normal).",
    )
    device: str = Field(
        "auto",
        description="Torch device hint (auto / cpu / cuda / mps).",
    )


class KoreanTTSBatchItem(BaseModel):
    id: str = Field(..., description="Caller-provided identifier for this item.")
    text: str = Field(..., description="Korean text to synthesize.")


class KoreanTTSBatchRequest(BaseModel):
    items: List[KoreanTTSBatchItem] = Field(
        ..., description="Batch of texts to synthesize."
    )
    speed: float = Field(
        1.0,
        gt=0.0,
        le=5.0,
        description="Playback speed multiplier (1.0 = normal).",
    )
    device: str = Field(
        "auto",
        description="Torch device hint (auto / cpu / cuda / mps).",
    )


@dataclass
class SynthParams:
    text: str
    speed: float
    device: str


def _require_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    """Optional API-key based auth.

    If MELOTTS_API_KEY is set in the environment, all requests must include a
    matching X-API-Key header. If it is unset, the check is disabled.
    """

    expected = os.environ.get(API_KEY_ENV_VAR)
    if not expected:
        # No API key configured; auth is effectively disabled (dev mode).
        return

    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


def _find_local_korean_model_dir() -> Optional[Path]:
    """(Legacy) path resolver for MeloTTS-Korean model dir.

    Kept for backwards compatibility but no longer used directly, as we now
    rely on the shared cached model loader in `simple_korean_tts`.
    """

    here = Path(__file__).resolve()
    melo_root = here.parent.parent  # MeloTTS/melo/ -> MeloTTS
    candidate = melo_root.parent / "MeloTTS-Korean"
    return candidate if candidate.exists() else None


def _synthesize_korean_once(params: SynthParams) -> bytes:
    """Synthesize Korean speech for a single request using a cached model.

    We now delegate to the shared cached model loader in simple_korean_tts so
    that the heavy MeloTTS model is constructed once and reused across many
    HTTP requests, matching the behaviour used in the local Anki client.
    """

    with _TTS_SEMAPHORE:
        model = get_korean_tts_model(device=params.device)

        speaker_ids = model.hps.data.spk2id
        speaker_id = getattr(speaker_ids, "KR", list(speaker_ids.values())[0])

        buf = io.BytesIO()
        model.tts_to_file(
            params.text,
            speaker_id,
            buf,
            speed=params.speed,
            quiet=True,
            format="wav",
        )
        return buf.getvalue()


@app.get("/health", summary="Liveness probe")
def health_check() -> dict[str, str]:
    """Simple health endpoint used for liveness checks."""

    return {"status": "ok"}


@app.get("/healthz", summary="Readiness probe")
def readiness_check() -> dict[str, str]:
    """Readiness endpoint that verifies the Korean TTS model can be loaded."""

    try:
        # This will construct or return the cached model instance.
        model = get_korean_tts_model(device="auto")
        if model is None:
            raise RuntimeError("Model not available")
    except Exception as exc:  # pragma: no cover - runtime-specific
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model not ready: {exc}",
        ) from exc

    return {"status": "ok", "model": "loaded"}


if PROMETHEUS_AVAILABLE:

    @app.get("/metrics", summary="Prometheus metrics")
    def metrics() -> Response:  # pragma: no cover - trivial wrapper
        payload = generate_latest()
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


@app.post(
    "/api/v1/tts/korean",
    summary="Synthesize Korean speech",
    response_description="WAV audio data.",
)
def synthesize_korean(
    body: KoreanTTSRequest,
    request: Request,
    _: None = Depends(_require_api_key),
) -> Response:
    """Convert Korean text to speech and return a WAV audio payload."""

    endpoint = "korean_single"
    client_ip = request.client.host if request.client else "unknown"

    _enforce_rate_limit(client_ip)

    text = body.text.strip()
    if not text:
        if PROMETHEUS_AVAILABLE:
            REQUEST_COUNTER.labels(endpoint=endpoint, status="400").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text must not be empty.",
        )
    if len(text) > MAX_TEXT_LENGTH:
        if PROMETHEUS_AVAILABLE:
            REQUEST_COUNTER.labels(endpoint=endpoint, status="413").inc()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Text too long (>{MAX_TEXT_LENGTH} chars).",
        )

    params = SynthParams(text=text, speed=body.speed, device=body.device)

    start = time.time()
    try:
        audio_bytes = _synthesize_korean_once(params)
        duration = time.time() - start

        if PROMETHEUS_AVAILABLE:
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
            REQUEST_COUNTER.labels(endpoint=endpoint, status="200").inc()
            TTS_CHARACTERS.labels(endpoint=endpoint).inc(len(text))
    except HTTPException:
        # HTTPExceptions are deliberate and already counted above where needed.
        raise
    except Exception as exc:  # pragma: no cover - runtime specific
        if PROMETHEUS_AVAILABLE:
            REQUEST_COUNTER.labels(endpoint=endpoint, status="500").inc()
            TTS_FAILURES.labels(endpoint=endpoint, reason="exception").inc()
        logger.error(
            "synthesis_failed",
            extra={
                "extra_data": {
                    "endpoint": endpoint,
                    "client_ip": client_ip,
                    "error": repr(exc),
                }
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synthesis failed: {exc}",
        ) from exc

    if not audio_bytes:
        if PROMETHEUS_AVAILABLE:
            REQUEST_COUNTER.labels(endpoint=endpoint, status="500").inc()
            TTS_FAILURES.labels(endpoint=endpoint, reason="empty_output").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Synthesis produced empty output.",
        )

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            # Hint that this is a short binary asset; clients may choose to
            # cache it on disk keyed by their own note IDs.
            "Cache-Control": "no-store",
        },
    )


@app.post(
    "/api/v1/tts/korean_batch",
    summary="Synthesize Korean speech for a batch of texts",
    response_description="JSON with base64-encoded WAV audio per item.",
)
def synthesize_korean_batch(
    body: KoreanTTSBatchRequest,
    request: Request,
    _: None = Depends(_require_api_key),
) -> dict:
    """Convert a batch of Korean texts to speech in a single request.

    The response is a JSON object of the form:

        {
          "items": [
            {"id": "item-id-1", "audio_b64": "..."},
            {"id": "item-id-2", "audio_b64": "..."},
            ...
          ]
        }
    """

    endpoint = "korean_batch"
    client_ip = request.client.host if request.client else "unknown"

    _enforce_rate_limit(client_ip)

    if not body.items:
        if PROMETHEUS_AVAILABLE:
            REQUEST_COUNTER.labels(endpoint=endpoint, status="400").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch must contain at least one item.",
        )

    # Reuse the cached Korean TTS model across the entire batch for efficiency.
    start = time.time()
    try:
        with _TTS_SEMAPHORE:
            model = get_korean_tts_model(device=body.device)
            speaker_ids = model.hps.data.spk2id
            speaker_id = getattr(speaker_ids, "KR", list(speaker_ids.values())[0])

            results: List[dict[str, str]] = []
            total_chars = 0
            failures = 0

            for item in body.items:
                text = item.text.strip()
                if not text:
                    continue
                if len(text) > MAX_TEXT_LENGTH:
                    # Skip over-long items; the client can decide how to handle this.
                    failures += 1
                    continue

                try:
                    buf = io.BytesIO()
                    model.tts_to_file(
                        text,
                        speaker_id,
                        buf,
                        speed=body.speed,
                        quiet=True,
                        format="wav",
                    )
                    audio_bytes = buf.getvalue()
                    if not audio_bytes:
                        failures += 1
                        continue

                    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                    results.append({"id": item.id, "audio_b64": audio_b64})
                    total_chars += len(text)
                except Exception as exc:  # pragma: no cover - runtime specific
                    failures += 1
                    if PROMETHEUS_AVAILABLE:
                        TTS_FAILURES.labels(
                            endpoint=endpoint, reason="item_exception"
                        ).inc()
                    logger.error(
                        "batch_item_failed",
                        extra={
                            "extra_data": {
                                "endpoint": endpoint,
                                "client_ip": client_ip,
                                "item_id": item.id,
                                "error": repr(exc),
                            }
                        },
                    )
                    continue

        duration = time.time() - start
        if PROMETHEUS_AVAILABLE:
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
            REQUEST_COUNTER.labels(endpoint=endpoint, status="200").inc()
            if total_chars:
                TTS_CHARACTERS.labels(endpoint=endpoint).inc(total_chars)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime specific
        if PROMETHEUS_AVAILABLE:
            REQUEST_COUNTER.labels(endpoint=endpoint, status="500").inc()
            TTS_FAILURES.labels(endpoint=endpoint, reason="exception").inc()
        logger.error(
            "batch_synthesis_failed",
            extra={
                "extra_data": {
                    "endpoint": endpoint,
                    "client_ip": client_ip,
                    "error": repr(exc),
                }
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch synthesis failed: {exc}",
        ) from exc

    return {"items": results}


def main() -> None:
    """Run a development server.

    For production, prefer invoking `uvicorn melo.server:app` directly and
    terminate TLS at a reverse proxy or Tailscale HTTPS listener bound to
    tts-server.your-tailnet.ts.net.
    """

    import uvicorn

    uvicorn.run(
        "melo.server:app",
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        reload=False,
        factory=False,
    )


if __name__ == "__main__":  # pragma: no cover - manual invocation
    main()



