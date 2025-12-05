#!/usr/bin/env python3
"""
Simple automated test for the Korean TTS endpoint in MeloTTS.

Usage (from repo root):

    anki/out/pyenv/bin/python MeloTTS/tools/test_simple_korean_tts_endpoint.py

Exit codes:
    0 -> endpoint works and produced a non-empty wav file
    1 -> failure (see printed error)
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import NamedTemporaryFile


def main() -> int:
    # Ensure MeloTTS is importable
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    try:
        from melo.simple_korean_tts import (  # type: ignore[import]
            synthesize_korean_tts,
        )
    except Exception as e:  # pragma: no cover - env-specific
        print("Korean TTS endpoint test: failed to import endpoint:", e)
        return 1

    try:
        text = "안녕하세요, 이것은 테스트입니다."
        with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            out_path = tmp.name

        synthesize_korean_tts(text, out_path, device="cpu")

        out = Path(out_path)
        if not out.exists() or out.stat().st_size == 0:
            print("Korean TTS endpoint test: output file missing or empty:", out)
            return 1

        print("Korean TTS endpoint test OK:", out)
        return 0
    except Exception as e:
        print("Korean TTS endpoint test FAILED:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

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