from __future__ import annotations

from pathlib import Path
from typing import Optional

from .api import TTS

# Cached global model instance
__korean_tts_model: Optional[TTS] = None


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
    # MeloTTS/melo/ -> MeloTTS
    melo_root = here.parent.parent
    candidate = melo_root.parent / "MeloTTS-Korean"
    return candidate if candidate.exists() else None


def get_korean_tts_model(
    *,
    device: str = "auto",
    config_path: Optional[str] = None,
    ckpt_path: Optional[str] = None,
) -> TTS:
    """Return a cached Korean TTS model.

    - If local MeloTTS-Korean files are found, use them (offline).
    - Otherwise, fall back to the standard HuggingFace-based download.
    """

    global __korean_tts_model
    if __korean_tts_model is not None:
        return __korean_tts_model

    model_dir = _find_local_korean_model_dir()

    if model_dir is not None and (config_path is None or ckpt_path is None):
        cfg = model_dir / "config.json"
        ckpt = model_dir / "checkpoint.pth"
        if cfg.exists() and ckpt.exists():
            config_path = str(cfg)
            ckpt_path = str(ckpt)

    if config_path and ckpt_path:
        # Fully offline
        __korean_tts_model = TTS(
            language="KR",
            device=device,
            config_path=config_path,
            ckpt_path=ckpt_path,
            use_hf=False,
        )
    else:
        # Allow TTS to download from HuggingFace if offline files are missing.
        __korean_tts_model = TTS(language="KR", device=device)

    return __korean_tts_model


def synthesize_korean_tts(
    text: str,
    output_path: str,
    *,
    speed: float = 1.0,
    device: str = "auto",
    config_path: Optional[str] = None,
    ckpt_path: Optional[str] = None,
) -> str:
    """Synthesize Korean speech for *text* into *output_path*.

    Returns the path to the written audio file.
    """

    model = get_korean_tts_model(
        device=device, config_path=config_path, ckpt_path=ckpt_path
    )

    # Choose Korean speaker ID
    speaker_ids = model.hps.data.spk2id
    speaker_id = getattr(speaker_ids, "KR", list(speaker_ids.values())[0])

    model.tts_to_file(text, speaker_id, output_path, speed=speed, quiet=True)
    return output_path

{
  "cells": [],
  "metadata": {
    "language_info": {
      "name": "python"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 2
}