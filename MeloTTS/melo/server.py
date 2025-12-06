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
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import torch
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .api import TTS
from .simple_korean_tts import get_korean_tts_model


API_TITLE = "MeloTTS Korean TTS Service"
API_VERSION = "1.0.0"

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = int(os.environ.get("MELOTTS_SERVER_PORT", "8000"))

# If set, incoming requests must include X-API-Key matching this value.
API_KEY_ENV_VAR = "MELOTTS_API_KEY"

# Upper bound to protect the service against accidentally huge requests.
MAX_TEXT_LENGTH = 500  # characters


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


@app.post(
    "/api/v1/tts/korean",
    summary="Synthesize Korean speech",
    response_description="WAV audio data.",
)
def synthesize_korean(
    body: KoreanTTSRequest,
    _: None = Depends(_require_api_key),
) -> Response:
    """Convert Korean text to speech and return a WAV audio payload."""

    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text must not be empty.",
        )
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Text too long (>{MAX_TEXT_LENGTH} chars).",
        )

    params = SynthParams(text=text, speed=body.speed, device=body.device)

    try:
        audio_bytes = _synthesize_korean_once(params)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime specific
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synthesis failed: {exc}",
        ) from exc

    if not audio_bytes:
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

    if not body.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch must contain at least one item.",
        )

    # Reuse the cached Korean TTS model across the entire batch for efficiency.
    model = get_korean_tts_model(device=body.device)
    speaker_ids = model.hps.data.spk2id
    speaker_id = getattr(speaker_ids, "KR", list(speaker_ids.values())[0])

    results: List[dict[str, str]] = []

    for item in body.items:
        text = item.text.strip()
        if not text:
            continue
        if len(text) > MAX_TEXT_LENGTH:
            # Skip over-long items; the client can decide how to handle this.
            continue

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
            continue

        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        results.append({"id": item.id, "audio_b64": audio_b64})

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



