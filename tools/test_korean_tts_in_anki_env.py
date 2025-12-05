#!/usr/bin/env python3
"""
Automated smoketest for the Korean TTS add-on in Anki's Python environment.

Usage (from project root):

    anki/out/pyenv/bin/python tools/test_korean_tts_in_anki_env.py

Exit codes:
    0 -> TTS smoketest succeeded
    1 -> TTS smoketest failed (see printed error)
"""

from __future__ import annotations

import sys
from pathlib import Path


def _direct_melotts_smoketest(root: Path) -> int:
    """Fallback smoketest that exercises MeloTTS directly, without Anki.

    This ensures that even if Anki's own Python packages are not available on
    the remote machine, we still verify that the local MeloTTS model can load
    and synthesize audio.
    """

    melotts_root = root / "MeloTTS"
    if not melotts_root.exists():
        print("Korean TTS smoketest: MeloTTS directory not found at", melotts_root)
        return 1

    sys.path.insert(0, str(melotts_root))

    try:
        from melo.simple_korean_tts import (  # type: ignore[import]
            synthesize_korean_tts,
        )
    except Exception as e:  # pragma: no cover - environment-specific
        print("Korean TTS smoketest: failed to import MeloTTS:", e)
        return 1

    from tempfile import NamedTemporaryFile

    sample_text = "안녕하세요, 이것은 한국어 TTS 테스트입니다."

    try:
        with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = tmp.name

        synthesize_korean_tts(
            sample_text,
            temp_path,
            device="auto",
        )

        if not Path(temp_path).exists() or Path(temp_path).stat().st_size == 0:
            print(
                "Korean TTS smoketest: MeloTTS output file missing or empty:",
                temp_path,
            )
            return 1

        Path(temp_path).unlink(missing_ok=True)
        print("Korean TTS smoketest: direct MeloTTS OK")
        return 0
    except Exception as e:  # pragma: no cover - environment-specific
        print("Korean TTS smoketest: direct MeloTTS FAILED:", e)
        return 1


def main() -> int:
    # Ensure Anki's Python libs and the korean_tts add-on are importable.
    root = Path(__file__).resolve().parents[1]
    anki_pylib = root / "anki" / "pylib"
    if anki_pylib.exists():
        sys.path.insert(0, str(anki_pylib))

    # Prefer importing the add-on directly from this repo's source tree so that
    # the smoketest always exercises the current branch, even if the installed
    # Anki add-on is out of date.
    repo_addon_dir = root / "anki_addon_korean_tts"
    if repo_addon_dir.exists():
        sys.path.insert(0, str(repo_addon_dir.parent))
        try:
            import anki_addon_korean_tts as korean_tts  # type: ignore[import]
        except Exception as e:  # pragma: no cover - environment-specific
            print("Korean TTS smoketest: failed to import repo add-on:", e)
            # Fall back to direct MeloTTS smoketest if Anki is not available.
            return _direct_melotts_smoketest(root)
    else:
        # Fallback: import from the user's Anki addons21 folder, if present.
        addons_root = Path.home() / ".local" / "share" / "Anki2" / "addons21"
        addon_dir = addons_root / "korean_tts"

        if not addon_dir.exists():
            print(
                "Korean TTS smoketest: add-on directory not found at",
                addon_dir,
            )
            return 1

        # Insert addons21 so `import korean_tts` works.
        sys.path.insert(0, str(addons_root))

        try:
            import korean_tts  # type: ignore[import]
        except Exception as e:  # pragma: no cover - environment-specific
            print("Korean TTS smoketest: failed to import add-on:", e)
            # Fall back to direct MeloTTS smoketest if Anki is not available.
            return _direct_melotts_smoketest(root)

    if not hasattr(korean_tts, "smoketest_korean_tts"):
        print(
            "Korean TTS smoketest: add-on does not expose "
            "smoketest_korean_tts()."
        )
        return 1

    ok = bool(korean_tts.smoketest_korean_tts(None))  # type: ignore[attr-defined]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


