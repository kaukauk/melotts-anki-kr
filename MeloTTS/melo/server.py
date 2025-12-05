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

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .api import TTS


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
    """Return the path to the local MeloTTS-Korean model dir if it exists.

    Expected layout (as in this repo):

        repo_root/
          MeloTTS/
          MeloTTS-Korean/

    When this is not present, callers can still rely on remote download via
    HuggingFace (TTS(use_hf=True)).
    """

    here = Path(__file__).resolve()
    melo_root = here.parent.parent  # MeloTTS/melo/ -> MeloTTS
    candidate = melo_root.parent / "MeloTTS-Korean"
    return candidate if candidate.exists() else None


def _synthesize_korean_once(params: SynthParams) -> bytes:
    """Synthesize Korean speech for a single request.

    This function **always** constructs a fresh TTS model instance and discards
    it after use, so the model only lives in memory for the duration of the
    request.
    """

    model_dir = _find_local_korean_model_dir()
    config_path: Optional[str] = None
    ckpt_path: Optional[str] = None

    if model_dir is not None:
        cfg = model_dir / "config.json"
        ckpt = model_dir / "checkpoint.pth"
        if cfg.exists() and ckpt.exists():
            config_path = str(cfg)
            ckpt_path = str(ckpt)

    if config_path and ckpt_path:
        model = TTS(
            language="KR",
            device=params.device,
            config_path=config_path,
            ckpt_path=ckpt_path,
            use_hf=False,
        )
    else:
        # Fall back to HuggingFace download if local files are missing.
        model = TTS(language="KR", device=params.device)

    try:
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
        audio_bytes = buf.getvalue()
    finally:
        # Ensure that we promptly release model resources between requests.
        del model  # type: ignore[unused-ignore]
        try:
            torch.cuda.empty_cache()
        except Exception:
            # Safe to ignore if CUDA is not available.
            pass

    return audio_bytes


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


