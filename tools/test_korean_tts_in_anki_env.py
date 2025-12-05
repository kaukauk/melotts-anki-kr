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


def main() -> int:
    # Ensure Anki's Python libs and the korean_tts add-on are importable.
    root = Path(__file__).resolve().parents[1]
    anki_pylib = root / "anki" / "pylib"
    if anki_pylib.exists():
        sys.path.insert(0, str(anki_pylib))

    # Ensure the korean_tts add-on package is importable from addons21.
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
        return 1

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


