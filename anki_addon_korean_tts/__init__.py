# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
Korean Text-to-Speech Add-on for Anki

This add-on provides Korean TTS functionality for Anki flashcards using MeloTTS.
It allows batch generation of TTS audio files and adds play buttons to cards.
"""

from __future__ import annotations

import os
import re
import sys
import hashlib
import base64
from pathlib import Path
from typing import Any, Optional
import json
import ssl
import urllib.error
import urllib.request

try:
    import aqt
    from aqt import gui_hooks, mw
    from aqt.qt import *
    from aqt.utils import showInfo, showWarning, tooltip
    _ANKI_GUI_AVAILABLE = True
except Exception:  # pragma: no cover - when running outside Anki GUI
    aqt = None  # type: ignore[assignment]
    gui_hooks = None  # type: ignore[assignment]
    mw = None  # type: ignore[assignment]
    _ANKI_GUI_AVAILABLE = False

    def showInfo(msg: str) -> None:  # type: ignore[override]
        print(msg)

    def showWarning(msg: str) -> None:  # type: ignore[override]
        print(msg, file=sys.stderr)

    def tooltip(msg: str) -> None:  # type: ignore[override]
        print(msg)

# Add MeloTTS to path if available.
# 
# We support two common layouts:
# - Development: this add-on lives inside the monorepo that also contains
#   the MeloTTS Python package in a sibling `MeloTTS` directory.
# - Installed: MeloTTS is installed as a normal Python package and can be
#   imported without any sys.path tweaks.
#
# For development convenience we will probe for a sibling MeloTTS checkout and
# add it to sys.path if present. This avoids hardcoding any user-specific
# absolute paths.
_addon_dir = Path(__file__).resolve().parent
_repo_root = _addon_dir.parent
_candidate_melotts = _repo_root / "MeloTTS"
if _candidate_melotts.exists():
    sys.path.insert(0, str(_candidate_melotts))

try:
    from melo.api import TTS
    MELOTTS_AVAILABLE = True
except ImportError:
    MELOTTS_AVAILABLE = False
    TTS = None

try:
    # High-level endpoint API around TTS; preferred entrypoint.
    from melo.simple_korean_tts import synthesize_korean_tts  # type: ignore[import]
except ImportError:  # pragma: no cover - env-specific
    synthesize_korean_tts = None  # type: ignore[assignment]

# -----------------------------------------------------------------------------
# Remote TTS configuration (driven by add-on settings)
# -----------------------------------------------------------------------------

ADDON_CONFIG_KEY = "korean_tts"

# Defaults used when no explicit configuration is provided. These values are
# deliberately generic so the project is portable to other machines by changing
# settings in Anki's add-on config UI instead of editing code.
_DEFAULT_REMOTE_HTTP_URL = "http://127.0.0.1:8000"

_DEFAULT_CONFIG: dict[str, Any] = {
    # Base URL of the remote Korean TTS server (scheme + host + port).
    "server_url": _DEFAULT_REMOTE_HTTP_URL,
    # Whether remote TTS calls are enabled at all.
    "remote_enabled": True,
    # Optional per-client API key for simple shared-secret auth.
    "api_key": "",
    # Network timeouts in seconds.
    "connect_timeout_secs": 3.0,
    "read_timeout_secs": 60.0,
    # Number of notes to send per HTTP batch request in server-only mode.
    "remote_batch_size": 16,
    # Optional extra path to a MeloTTS checkout for advanced configurations.
    "melotts_extra_path": "",
}


def _load_addon_config() -> dict[str, Any]:
    """Load the add-on's configuration from Anki, merged with defaults."""

    if not mw:
        return dict(_DEFAULT_CONFIG)

    try:
        raw_cfg = mw.addonManager.getConfig(ADDON_CONFIG_KEY)  # type: ignore[union-attr]
    except Exception:
        raw_cfg = {}

    cfg: dict[str, Any] = dict(_DEFAULT_CONFIG)
    if isinstance(raw_cfg, dict):
        for key, value in raw_cfg.items():
            if key in cfg:
                cfg[key] = value
    return cfg


def _save_addon_config(cfg: dict[str, Any]) -> None:
    """Persist configuration back to Anki."""

    if not mw:
        return
    try:
        mw.addonManager.writeConfig(ADDON_CONFIG_KEY, cfg)  # type: ignore[union-attr]
    except Exception:
        # Config persistence failures should not break normal add-on usage.
        print("Korean TTS: failed to save config", file=sys.stderr)


# The following globals are derived from configuration and environment
# variables. They are initialised once at import time and can be updated when
# the user changes settings via the config UI.
_REMOTE_TTS_BASE_URL: str = _DEFAULT_REMOTE_HTTP_URL
_REMOTE_TTS_ENDPOINT: str = _DEFAULT_REMOTE_HTTP_URL + "/api/v1/tts/korean"
_REMOTE_TTS_BATCH_ENDPOINT: str = _DEFAULT_REMOTE_HTTP_URL + "/api/v1/tts/korean_batch"
_REMOTE_TTS_API_KEY: str | None = None
_REMOTE_TTS_CONNECT_TIMEOUT: float = 3.0
_REMOTE_TTS_READ_TIMEOUT: float = 60.0
_REMOTE_TTS_ENABLED: bool = True
_REMOTE_BATCH_SIZE: int = 16


def _apply_config_to_globals(cfg: dict[str, Any]) -> None:
    """Apply a loaded config dict to module-level globals."""

    global _REMOTE_TTS_BASE_URL, _REMOTE_TTS_ENDPOINT, _REMOTE_TTS_BATCH_ENDPOINT
    global _REMOTE_TTS_API_KEY, _REMOTE_TTS_CONNECT_TIMEOUT, _REMOTE_TTS_READ_TIMEOUT
    global _REMOTE_TTS_ENABLED, _REMOTE_BATCH_SIZE

    # Base URL: env var overrides config, which falls back to default.
    cfg_server_url = str(cfg.get("server_url") or "").strip() or _DEFAULT_REMOTE_HTTP_URL
    base_url = os.environ.get("KOREAN_TTS_SERVER_URL", cfg_server_url).strip()
    if not base_url:
        base_url = _DEFAULT_REMOTE_HTTP_URL
    _REMOTE_TTS_BASE_URL = base_url.rstrip("/")
    _REMOTE_TTS_ENDPOINT = _REMOTE_TTS_BASE_URL + "/api/v1/tts/korean"
    _REMOTE_TTS_BATCH_ENDPOINT = _REMOTE_TTS_BASE_URL + "/api/v1/tts/korean_batch"

    # API key: environment takes precedence over config.
    api_key_env = os.environ.get("KOREAN_TTS_SERVER_API_KEY")
    if api_key_env:
        _REMOTE_TTS_API_KEY = api_key_env
    else:
        api_key_cfg = str(cfg.get("api_key") or "").strip()
        _REMOTE_TTS_API_KEY = api_key_cfg or None

    # Timeouts.
    _REMOTE_TTS_CONNECT_TIMEOUT = float(cfg.get("connect_timeout_secs", 3.0))
    _REMOTE_TTS_READ_TIMEOUT = float(cfg.get("read_timeout_secs", 60.0))

    # Remote enabled flag: env var can force on/off; otherwise config controls it.
    env_flag = os.environ.get("KOREAN_TTS_REMOTE_ENABLED")
    if env_flag is not None:
        _REMOTE_TTS_ENABLED = env_flag not in ("", "0", "false", "False")
    else:
        _REMOTE_TTS_ENABLED = bool(cfg.get("remote_enabled", True))

    # Batch size.
    try:
        _REMOTE_BATCH_SIZE = int(cfg.get("remote_batch_size", 16)) or 16
    except Exception:
        _REMOTE_BATCH_SIZE = 16


_CONFIG = _load_addon_config()
_apply_config_to_globals(_CONFIG)


def _autodetect_local_server() -> None:
    """No-op placeholder kept for backwards compatibility.

    In earlier versions this attempted to probe a local development server on
    127.0.0.1:8000. The configuration is now entirely driven by the add-on
    settings and optional environment variables, so we intentionally do
    nothing here.
    """

    return


def _remote_synthesize_korean_tts(
    text: str,
    output_path: str,
    *,
    speed: float = 1.0,
) -> bool:
    """Attempt to synthesize Korean TTS via the remote HTTP service.

    Returns:
        True if the remote call succeeded and wrote a WAV file to output_path.
        False if the request failed for any reason (HTTP/network/protocol),
        in which case callers should fall back to local synthesis.
    """

    if not _REMOTE_TTS_ENABLED:
        return False

    text = text.strip()
    if not text:
        return False

    # Log the endpoint we are about to call for easier debugging.
    print(
        f"Remote Korean TTS: using endpoint {_REMOTE_TTS_ENDPOINT!r}",
        file=sys.stderr,
    )

    payload = {
        "text": text,
        "speed": float(speed),
        "device": "auto",
    }

    data = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
    }
    if _REMOTE_TTS_API_KEY:
        headers["X-API-Key"] = _REMOTE_TTS_API_KEY

    req = urllib.request.Request(
        _REMOTE_TTS_ENDPOINT,
        data=data,
        headers=headers,
        method="POST",
    )

    # Use default system trust store; this will validate the HTTPS certificate
    # presented by the remote TTS server when using HTTPS (e.g. via Tailscale).
    context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(
            req,
            timeout=_REMOTE_TTS_CONNECT_TIMEOUT + _REMOTE_TTS_READ_TIMEOUT,
            context=context,
        ) as resp:
            status_code = getattr(resp, "status", 200)
            if status_code != 200:
                print(
                    f"Remote Korean TTS: unexpected HTTP status {status_code}",
                    file=sys.stderr,
                )
                return False

            content_type = resp.headers.get("Content-Type", "")
            if "audio" not in content_type:
                print(
                    "Remote Korean TTS: expected audio response, "
                    f"got Content-Type={content_type!r}",
                    file=sys.stderr,
                )
                return False

            audio_bytes = resp.read()
    except urllib.error.URLError as e:
        # Network connectivity, DNS, TLS handshake, timeout, etc.
        print(
            f"Remote Korean TTS network error talking to "
            f"{_REMOTE_TTS_ENDPOINT!r}: {e}",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(f"Remote Korean TTS unexpected error: {e}", file=sys.stderr)
        return False

    if not audio_bytes:
        print("Remote Korean TTS: empty audio response", file=sys.stderr)
        return False

    try:
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
    except Exception as e:
        print(f"Remote Korean TTS: failed to write {output_path}: {e}", file=sys.stderr)
        return False

    return True


def _remote_synthesize_korean_tts_batch(
    items: list[tuple[str, str]],
    *,
    speed: float = 1.0,
) -> dict[str, bytes]:
    """Batch version of _remote_synthesize_korean_tts.

    Args:
        items: Sequence of (item_id, text) to synthesize.

    Returns:
        Mapping of item_id -> raw WAV bytes for successfully synthesized items.
    """

    if not _REMOTE_TTS_ENABLED or not items:
        return {}

    payload_items: list[dict[str, str]] = []
    for item_id, text in items:
        text = text.strip()
        if not text:
            continue
        payload_items.append({"id": item_id, "text": text})

    if not payload_items:
        return {}

    batch_payload = {
        "items": payload_items,
        "speed": float(speed),
        "device": "auto",
    }

    data = json.dumps(batch_payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
    }
    if _REMOTE_TTS_API_KEY:
        headers["X-API-Key"] = _REMOTE_TTS_API_KEY

    req = urllib.request.Request(
        _REMOTE_TTS_BATCH_ENDPOINT,
        data=data,
        headers=headers,
        method="POST",
    )

    context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(
            req,
            timeout=_REMOTE_TTS_CONNECT_TIMEOUT + _REMOTE_TTS_READ_TIMEOUT,
            context=context,
        ) as resp:
            status_code = getattr(resp, "status", 200)
            if status_code != 200:
                print(
                    f"Remote Korean TTS batch: unexpected HTTP status {status_code}",
                    file=sys.stderr,
                )
                return {}

            content_type = resp.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                print(
                    "Remote Korean TTS batch: expected JSON response, "
                    f"got Content-Type={content_type!r}",
                    file=sys.stderr,
                )
                return {}

            body = resp.read()
    except urllib.error.URLError as e:
        print(
            f"Remote Korean TTS batch network error talking to "
            f"{_REMOTE_TTS_BATCH_ENDPOINT!r}: {e}",
            file=sys.stderr,
        )
        return {}
    except Exception as e:
        print(f"Remote Korean TTS batch unexpected error: {e}", file=sys.stderr)
        return {}

    try:
        decoded = json.loads(body.decode("utf-8"))
    except Exception as e:
        print(f"Remote Korean TTS batch: failed to decode JSON: {e}", file=sys.stderr)
        return {}

    results: dict[str, bytes] = {}
    for item in decoded.get("items", []):
        item_id = item.get("id")
        audio_b64 = item.get("audio_b64")
        if not item_id or not audio_b64:
            continue
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception as e:
            print(
                f"Remote Korean TTS batch: failed to decode base64 for id={item_id!r}: {e}",
                file=sys.stderr,
            )
            continue
        if not audio_bytes:
            continue
        results[item_id] = audio_bytes

    return results


# Global TTS model instance (cached to avoid reloading for local fallback)
_tts_model: TTS | None = None

# Probe flag and cached availability for local TTS. We always attempt to load
# MeloTTS locally once; if that fails, the explicit "local" menu option will be
# disabled so the user cannot select it.
_LOCAL_TTS_PROBED: bool = False
_LOCAL_TTS_AVAILABLE: bool = False


def get_tts_model() -> TTS | None:
    """Get or initialize the TTS model."""
    global _tts_model
    
    if not MELOTTS_AVAILABLE:
        return None
    
    if _tts_model is None:
        try:
            # Fall back to the generic MeloTTS API, which will either use local
            # model files (when configured via MeloTTS itself) or download from
            # HuggingFace as needed. We intentionally avoid hardcoding any
            # user-specific paths here so the add-on remains portable.
            _tts_model = TTS(language="KR", device="auto")
        except Exception as e:
            showWarning(f"Failed to initialize Korean TTS model: {e}")
            return None
    
    return _tts_model


def is_local_tts_available() -> bool:
    """Return True if a local MeloTTS Korean model can be used.

    This will try to initialize the model once per session; if initialization
    fails, the explicit "local" generation option is disabled.
    """

    global _LOCAL_TTS_PROBED, _LOCAL_TTS_AVAILABLE

    if _LOCAL_TTS_PROBED:
        return _LOCAL_TTS_AVAILABLE

    _LOCAL_TTS_PROBED = True
    model = get_tts_model()
    _LOCAL_TTS_AVAILABLE = bool(model)
    return _LOCAL_TTS_AVAILABLE


def contains_korean(text: str) -> bool:
    """Check if text contains Korean characters (Hangul)."""
    # Korean Unicode range: AC00-D7AF (Hangul Syllables)
    # Also includes 1100-11FF (Hangul Jamo) and 3130-318F (Hangul Compatibility Jamo)
    korean_pattern = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]')
    return bool(korean_pattern.search(text))


def extract_korean_text(html: str) -> str:
    """Extract Korean text from HTML, removing tags and non-Korean content."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html)
    # Remove sound tags
    text = re.sub(r'\[sound:[^\]]+\]', '', text)
    # Extract only Korean characters and spaces
    korean_chars = re.findall(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u313F\s]+', text)
    return ''.join(korean_chars).strip()


def _synthesize_to_tempfile(
    korean_text: str,
    temp_path: str,
    *,
    mode: str,
) -> bool:
    """Synthesize *korean_text* into *temp_path* according to *mode*.

    Modes:
        - "remote_only": use server only; no local fallback.
        - "local_only": use local MeloTTS only; no remote calls.
        - "auto": try server first, then local fallback.

    Returns True on success, False on failure.
    """

    assert mode in ("remote_only", "local_only", "auto")

    # Helper to perform local synthesis.
    def _local_synth() -> bool:
        if synthesize_korean_tts is not None:
            try:
                synthesize_korean_tts(
                    korean_text,
                    temp_path,
                    device="auto",
                )
                return True
            except Exception as e:
                print(f"Local synth via synthesize_korean_tts failed: {e}", file=sys.stderr)
                return False

        model = get_tts_model()
        if not model:
            return False

        try:
            speaker_ids = model.hps.data.spk2id
            speaker_id = getattr(
                speaker_ids,
                "KR",
                list(speaker_ids.values())[0],
            )
            model.tts_to_file(
                korean_text, speaker_id, temp_path, quiet=True
            )
            return True
        except Exception as e:
            print(f"Local synth via direct TTS failed: {e}", file=sys.stderr)
            return False

    # Helper to perform remote synthesis.
    def _remote_synth() -> bool:
        try:
            return _REMOTE_TTS_ENABLED and _remote_synthesize_korean_tts(
                korean_text,
                temp_path,
                speed=1.0,
            )
        except Exception as e:
            print(f"Remote synth failed: {e}", file=sys.stderr)
            return False

    if mode == "remote_only":
        return _remote_synth()
    if mode == "local_only":
        return _local_synth()

    # auto mode: remote first, then local fallback.
    if _remote_synth():
        return True
    return _local_synth()


def _korean_tts_filename(note_id: int, field_name: str, korean_text: str) -> str:
    """Deterministic filename for a note+field+text combination.

    Includes a short hash of the Korean text so that:
    - If the text is unchanged and audio already exists, we can skip.
    - If the text changes, a new filename is used and audio is regenerated.
    """
    h = hashlib.sha1(korean_text.encode("utf-8")).hexdigest()[:8]
    safe_field = re.sub(r"[^A-Za-z0-9_]+", "_", field_name)
    return f"ktts_{note_id}_{safe_field}_{h}.wav"


def _prepare_field_for_tts(
    note: Any, field_name: str, korean_text: str
) -> tuple[bool, str, str]:
    """Decide whether TTS needs to be (re)generated, and return base text + filename.

    Returns:
        (should_generate, base_field_text, target_filename)
    """
    current_value = note[field_name]
    if not korean_text:
        return False, current_value, ""

    target_fname = _korean_tts_filename(int(note.id), field_name, korean_text)

    # If we already have an exact match, nothing to do.
    if f"[sound:{target_fname}]" in current_value:
        return False, current_value, target_fname

    # Otherwise, strip any older Korean TTS sound tags we previously injected,
    # so we don't accumulate multiple outdated audio references.
    cleaned_value = re.sub(r"\s*\[sound:ktts_[^\]]+\.wav\]", "", current_value)
    cleaned_value = cleaned_value.rstrip()

    return True, cleaned_value, target_fname


def add_play_button_to_card(text: str, card: Any, kind: str) -> str:
    """Add a play button to cards that contain Korean audio.

    Generation of audio is handled in batch via menu actions; this hook only
    adds playback controls when audio is already present on the card.
    """
    if not mw or not mw.col:
        return text
    
    # Only process review cards
    if kind not in ["reviewQuestion", "reviewAnswer"]:
        return text
    
    # Check if audio already exists for this card
    note = card.note()
    if not note:
        return text
    
    # Look for existing sound tags
    has_audio = "[sound:" in text
    if not has_audio:
        # No pre-generated audio; batch tools will add it later.
        return text

    # Audio already exists, add play button
    play_button = (
        '<div style="margin: 10px 0;">'
        '<button onclick="pycmd(\'play_korean_tts\');" '
        'style="padding: 8px 16px; cursor: pointer; '
        'background: #4CAF50; color: white; border: none; border-radius: 4px; '
        'font-size: 14px; font-weight: bold;">'
        "🔊 Play Korean</button>"
        "</div>"
    )
    
    # Insert button at the end of the content
    # Try to insert before closing tags, otherwise append
    if '</div>' in text:
        # Find the last </div> and insert before it
        last_div = text.rfind('</div>')
        text = text[:last_div] + play_button + text[last_div:]
    else:
        text += play_button
    
    return text


def handle_play_korean_tts(reviewer: Any, url: str) -> bool:
    """Handle play button click for Korean TTS."""
    if url != "play_korean_tts":
        return False
    
    if not reviewer.card:
        return True
    
    note = reviewer.card.note()
    if not note:
        return True
    
    # Find Korean field and play its audio
    for field_name, field_value in note.items():
        if contains_korean(field_value):
            # Look for sound tag in the field
            sound_match = re.search(r'\[sound:([^\]]+)\]', field_value)
            if sound_match:
                filename = sound_match.group(1)
                # Play the audio
                from aqt.sound import av_player
                av_player.play_file(filename)
                return True
    
    tooltip("No Korean audio found for this card.")
    return True


def handle_generate_korean_tts(reviewer: Any, url: str) -> bool:
    """Handle generate button click for Korean TTS."""
    if url != "generate_korean_tts":
        return False
    
    if not reviewer.card:
        return True
    
    note = reviewer.card.note()
    if not note:
        return True
    
    # Find Korean field
    korean_text = None
    korean_field = None
    
    for field_name, field_value in note.items():
        text = extract_korean_text(field_value)
        if text and contains_korean(text):
            korean_text = text
            korean_field = field_name
            break
    
    if not korean_text:
        tooltip("No Korean text found in this card.")
        return True
    
    # Decide if we need to (re)generate TTS for this field.
    should_gen, base_value, target_fname = _prepare_field_for_tts(
        note, korean_field, korean_text
    )
    if not should_gen:
        tooltip("Korean TTS already up to date for this card.")
        return True

    # Generate TTS
    try:
        # Generate audio file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = tmp.name

        # For per-card generation, use the "auto" mode: first try the remote
        # server, and if that fails, fall back to local synthesis.
        success = _synthesize_to_tempfile(
            korean_text,
            temp_path,
            mode="auto",
        )
        if not success:
            showWarning(
                "Failed to generate Korean TTS using both server and local modes."
            )
            return True

        # Add to Anki media folder with deterministic, text-based name.
        media_manager = mw.col.media
        with open(temp_path, "rb") as f:
            final_filename = media_manager.write_data(target_fname, f.read())

        # Clean up temp file
        os.unlink(temp_path)

        # Add sound tag to the field
        note[korean_field] = base_value + f' [sound:{final_filename}]'
        mw.col.update_note(note)
        
        tooltip("Korean TTS generated successfully!")
        
        # Refresh the card
        reviewer._redraw_current_card()
        
    except Exception as e:
        showWarning(f"Failed to generate Korean TTS: {e}")
    
    return True


def _batch_generate_tts_impl(*, mode: str) -> None:
    """Internal helper to batch generate TTS for the current deck.

    mode:
        - "remote_only": use server only (no local fallback).
        - "local_only": use local only (no remote).
        - "auto": try server first, then local fallback.
    """
    if not mw or not mw.col:
        return

    assert mode in ("remote_only", "local_only", "auto")

    # For local-only mode, verify availability up front so we can fail fast
    # instead of erroring per-note. For "auto" mode we intentionally skip this
    # check so that the remote server can still be used even when no local
    # model is available; in that case, "auto" effectively behaves like
    # "remote_only", with local synthesis used only when present.
    if mode == "local_only":
        if synthesize_korean_tts is None and get_tts_model() is None:
            showWarning(
                "Local Korean TTS model is not available. Please check MeloTTS installation."
            )
            return
    
    # Get notes in the current deck only
    # "deck:current" uses the currently selected deck in the deck browser.
    note_ids = mw.col.find_notes("deck:current")
    total_notes = len(note_ids)
    
    if total_notes == 0:
        showInfo("No notes found in collection.")
        return
    
    # Ask for confirmation
    reply = QMessageBox.question(
        mw,
        "Batch Generate Korean TTS",
        f"This will generate TTS audio for all {total_notes} notes with Korean text.\n\n"
        "This may take a while. Continue?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    
    if reply != QMessageBox.StandardButton.Yes:
        return
    
    # Process notes
    processed = 0
    generated = 0
    errors = 0
    cancelled = False

    mgr = mw.progress
    mgr.start(
        max=total_notes,
        label="Generating Korean TTS for current deck...",
        immediate=True,
    )

    # Internal helper to run a remote-only batch using the HTTP batch API.
    def _run_remote_batch(batch_items: list[dict[str, Any]]) -> None:
        nonlocal processed, generated, errors

        if not batch_items:
            return

        # Map target_fname -> (note, field, base_value)
        id_to_meta: dict[str, tuple[Any, str, str]] = {}
        request_items: list[tuple[str, str]] = []

        for item in batch_items:
            target_fname = item["target_fname"]
            korean_text = item["korean_text"]
            request_items.append((target_fname, korean_text))
            id_to_meta[target_fname] = (
                item["note"],
                item["korean_field"],
                item["base_value"],
            )

        remote_results = _remote_synthesize_korean_tts_batch(request_items)

        for target_fname, (note, korean_field, base_value) in id_to_meta.items():
            processed += 1
            audio_bytes = remote_results.get(target_fname)
            if not audio_bytes:
                errors += 1
                continue

            try:
                final_filename = mw.col.media.write_data(target_fname, audio_bytes)
                note[korean_field] = (
                    base_value + f" [sound:{final_filename}]"
                )
                mw.col.update_note(note)
                generated += 1
            except Exception as e:  # pragma: no cover - environment-specific
                errors += 1
                print(f"Error writing media for {target_fname!r}: {e}", file=sys.stderr)

    # Number of notes to send per remote batch request when mode=="remote_only".
    pending_remote: list[dict[str, Any]] = []

    try:
        for i, note_id in enumerate(note_ids):
            if mw.progress.want_cancel():
                cancelled = True
                break

            mgr.update(
                f"Processing note {i + 1}/{total_notes}...", value=i + 1
            )

            try:
                note = mw.col.get_note(note_id)

                # Find Korean field
                korean_text = None
                korean_field = None

                for field_name, field_value in note.items():
                    text = extract_korean_text(field_value)
                    if text and contains_korean(text):
                        korean_text = text
                        korean_field = field_name
                        break

                if not korean_text:
                    processed += 1
                    continue

                # Decide if we need to (re)generate TTS for this field.
                should_gen, base_value, target_fname = _prepare_field_for_tts(
                    note, korean_field, korean_text
                )
                if not should_gen:
                    processed += 1
                    continue
                # Generate TTS according to the requested mode.
                if mode == "remote_only":
                    # Defer to the HTTP batch API; we collect items and send
                    # them in groups to minimise per-note roundtrips.
                    pending_remote.append(
                        {
                            "note": note,
                            "note_id": note_id,
                            "korean_field": korean_field,
                            "korean_text": korean_text,
                            "base_value": base_value,
                            "target_fname": target_fname,
                        }
                    )
                    if len(pending_remote) >= _REMOTE_BATCH_SIZE:
                        _run_remote_batch(pending_remote)
                        pending_remote.clear()
                else:
                    # Local-only and auto modes reuse the existing per-note
                    # helper, which will try the remote server first (for auto)
                    # and fall back to local synthesis when available.
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    ) as tmp:
                        temp_path = tmp.name

                    ok = _synthesize_to_tempfile(
                        korean_text,
                        temp_path,
                        mode=mode,
                    )
                    if not ok:
                        errors += 1
                        continue

                    # Add to Anki media folder with a deterministic, text-based name.
                    with open(temp_path, "rb") as f:
                        final_filename = mw.col.media.write_data(
                            target_fname, f.read()
                        )

                    # Clean up temp file
                    os.unlink(temp_path)

                    # Add sound tag to the field
                    note[korean_field] = (
                        base_value + f" [sound:{final_filename}]"
                    )
                    mw.col.update_note(note)

                    generated += 1
                    processed += 1

            except Exception as e:
                # Log full traceback to the console to aid debugging.
                import traceback
                errors += 1
                print(f"Error processing note {note_id}: {e}")
                traceback.print_exc()
        # Flush any remaining remote items.
        if mode == "remote_only" and pending_remote:
            _run_remote_batch(pending_remote)
            pending_remote.clear()
    finally:
        mgr.finish()

    if cancelled:
        showInfo(
            "Batch generation cancelled by user.\n\n"
            f"Processed: {processed} notes\n"
            f"Generated: {generated} audio files\n"
            f"Errors: {errors}"
        )
    else:
        showInfo(
            f"Batch generation complete!\n\n"
            f"Processed: {processed} notes\n"
            f"Generated: {generated} audio files\n"
            f"Errors: {errors}"
        )


def batch_generate_tts_server() -> None:
    """Public entrypoint: server-only batch generation for current deck."""
    _batch_generate_tts_impl(mode="remote_only")


def batch_generate_tts_local() -> None:
    """Public entrypoint: local-only batch generation for current deck."""
    _batch_generate_tts_impl(mode="local_only")


def batch_generate_tts() -> None:
    """Backwards-compatible entrypoint: auto (server, then local fallback)."""
    _batch_generate_tts_impl(mode="auto")


if _ANKI_GUI_AVAILABLE:

    class KoreanTtsSettingsDialog(QDialog):
        """Simple settings dialog for configuring the Korean TTS add-on."""

        def __init__(self, parent: Any, cfg: dict[str, Any]) -> None:
            super().__init__(parent)
            self.setWindowTitle("Korean TTS Settings")

            layout = QVBoxLayout(self)
            form = QFormLayout()

            # Server URL
            self.server_url_edit = QLineEdit(self)
            self.server_url_edit.setText(str(cfg.get("server_url", "")))
            form.addRow("Server URL:", self.server_url_edit)

            # Remote enabled
            self.remote_enabled_check = QCheckBox("Enable remote TTS", self)
            self.remote_enabled_check.setChecked(bool(cfg.get("remote_enabled", True)))
            form.addRow(self.remote_enabled_check)

            # API key
            self.api_key_edit = QLineEdit(self)
            self.api_key_edit.setText(str(cfg.get("api_key", "")))
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("API key (optional):", self.api_key_edit)

            # Timeouts
            self.connect_timeout_spin = QDoubleSpinBox(self)
            self.connect_timeout_spin.setRange(0.1, 120.0)
            self.connect_timeout_spin.setSingleStep(0.5)
            self.connect_timeout_spin.setValue(
                float(cfg.get("connect_timeout_secs", 3.0))
            )
            form.addRow("Connect timeout (s):", self.connect_timeout_spin)

            self.read_timeout_spin = QDoubleSpinBox(self)
            self.read_timeout_spin.setRange(1.0, 600.0)
            self.read_timeout_spin.setSingleStep(1.0)
            self.read_timeout_spin.setValue(
                float(cfg.get("read_timeout_secs", 60.0))
            )
            form.addRow("Read timeout (s):", self.read_timeout_spin)

            # Batch size
            self.batch_size_spin = QSpinBox(self)
            self.batch_size_spin.setRange(1, 256)
            self.batch_size_spin.setValue(int(cfg.get("remote_batch_size", 16)))
            form.addRow("Remote batch size:", self.batch_size_spin)

            # Optional extra MeloTTS path
            self.melotts_path_edit = QLineEdit(self)
            self.melotts_path_edit.setText(str(cfg.get("melotts_extra_path") or ""))
            form.addRow("Extra MeloTTS path (optional):", self.melotts_path_edit)

            layout.addLayout(form)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
                parent=self,
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        def to_config(self, base_cfg: dict[str, Any]) -> dict[str, Any]:
            cfg = dict(base_cfg)
            cfg["server_url"] = self.server_url_edit.text().strip()
            cfg["remote_enabled"] = bool(self.remote_enabled_check.isChecked())
            cfg["api_key"] = self.api_key_edit.text()
            cfg["connect_timeout_secs"] = float(self.connect_timeout_spin.value())
            cfg["read_timeout_secs"] = float(self.read_timeout_spin.value())
            cfg["remote_batch_size"] = int(self.batch_size_spin.value())
            cfg["melotts_extra_path"] = self.melotts_path_edit.text().strip()
            return cfg


    def show_settings_dialog() -> None:
        """Open the Korean TTS settings dialog."""

        if not mw:
            return

        global _CONFIG
        cfg = _load_addon_config()
        dlg = KoreanTtsSettingsDialog(mw, cfg)
        if dlg.exec():
            new_cfg = dlg.to_config(cfg)
            _save_addon_config(new_cfg)
            _CONFIG = new_cfg
            _apply_config_to_globals(_CONFIG)

            # Optionally update sys.path with a new MeloTTS path for advanced users.
            extra_path = str(new_cfg.get("melotts_extra_path") or "").strip()
            if extra_path:
                p = Path(extra_path)
                if p.exists():
                    sys.path.insert(0, str(p))

            tooltip("Korean TTS settings updated.")

else:

    def show_settings_dialog() -> None:  # type: ignore[dead-code]
        """Stub in headless environments."""

        return


def setup_menu() -> None:
    """Add menu items to Anki."""
    if not mw:
        return
    
    # Add a separator before our menu items to put them at the bottom
    mw.form.menuTools.addSeparator()
    
    # Server-based batch generation
    server_action = QAction("Generate Korean TTS for Current Deck (Server)", mw)
    server_action.triggered.connect(batch_generate_tts_server)
    server_action.setEnabled(_REMOTE_TTS_ENABLED)
    mw.form.menuTools.addAction(server_action)

    # Local batch generation; only enable if a local MeloTTS model is available.
    local_action = QAction("Generate Korean TTS for Current Deck (Local)", mw)
    local_action.triggered.connect(batch_generate_tts_local)
    local_action.setEnabled(is_local_tts_available())
    mw.form.menuTools.addAction(local_action)

    # Settings dialog
    settings_action = QAction("Korean TTS Settings…", mw)
    settings_action.triggered.connect(show_settings_dialog)
    mw.form.menuTools.addAction(settings_action)


def setup_hooks() -> None:
    """Set up Anki hooks."""
    # Hook into card rendering to add play buttons
    gui_hooks.card_will_show.append(add_play_button_to_card)
    
    # Hook into webview messages to handle button clicks
    def on_webview_message(handled: tuple[bool, Any], cmd: str, context: Any) -> tuple[bool, Any]:
        """Handle custom pycmd() messages from JavaScript."""
        if cmd == "play_korean_tts":
            # Check if context is a reviewer
            from aqt import reviewer
            if isinstance(context, reviewer.Reviewer):
                handle_play_korean_tts(context, cmd)
                return (True, None)
        elif cmd == "generate_korean_tts":
            # Check if context is a reviewer
            from aqt import reviewer
            if isinstance(context, reviewer.Reviewer):
                handle_generate_korean_tts(context, cmd)
                return (True, None)
        
        return handled
    
    gui_hooks.webview_did_receive_js_message.append(on_webview_message)

    # Browser: add menu item for generating TTS for selected notes
    def on_browser_menus_did_init(browser: Any) -> None:
        action = QAction("Generate Korean TTS for Selected Notes", browser)

        def on_triggered(checked: bool = False, b: Any = browser) -> None:  # type: ignore[unused-argument]
            if not mw or not mw.col:
                return
            note_ids = list(b.selected_notes())
            if not note_ids:
                tooltip("No notes selected.")
                return

            total_notes = len(note_ids)

            reply = QMessageBox.question(
                mw,
                "Generate Korean TTS (Selection)",
                f"This will generate TTS audio for {total_notes} selected notes "
                "that contain Korean text.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            processed = 0
            generated = 0
            errors = 0

            mgr = mw.progress
            mgr.start(
                max=total_notes,
                label="Generating Korean TTS for selection...",
                immediate=True,
            )

            try:
                for i, note_id in enumerate(note_ids):
                    mgr.update(
                        f"Processing note {i + 1}/{total_notes}...", value=i
                    )
                    try:
                        note = mw.col.get_note(note_id)

                        korean_text = None
                        korean_field = None

                        for field_name, field_value in note.items():
                            text = extract_korean_text(field_value)
                            if text and contains_korean(text):
                                korean_text = text
                                korean_field = field_name
                                break

                        if not korean_text:
                            processed += 1
                            continue

                        if "[sound:" in note[korean_field]:
                            processed += 1
                            continue

                        import tempfile

                        with tempfile.NamedTemporaryFile(
                            suffix=".wav", delete=False
                        ) as tmp:
                            temp_path = tmp.name

                        # Use the same auto mode as card/deck batch generation:
                        # try the remote server first, and fall back to local
                        # synthesis only when available. This ensures that TTS
                        # generation still works even when no local MeloTTS
                        # model is installed.
                        ok = _synthesize_to_tempfile(
                            korean_text,
                            temp_path,
                            mode="auto",
                        )
                        if not ok:
                            errors += 1
                            continue

                        final_filename = mw.col.media.add_file(temp_path)
                        os.unlink(temp_path)

                        current_value = note[korean_field]
                        note[korean_field] = (
                            current_value + f" [sound:{final_filename}]"
                        )
                        note.flush()
                        mw.col.notes.update_notes([note])

                        generated += 1
                        processed += 1
                    except Exception as e:
                        errors += 1
                        print(f"Error processing note {note_id}: {e}")
            finally:
                mgr.finish()

            showInfo(
                "Selection generation complete!\n\n"
                f"Processed: {processed} notes\n"
                f"Generated: {generated} audio files\n"
                f"Errors: {errors}"
            )

        action.triggered.connect(on_triggered)
        browser.form.menuEdit.addAction(action)

    gui_hooks.browser_menus_did_init.append(on_browser_menus_did_init)


def smoketest_korean_tts(col: Any | None = None) -> bool:
    """Headless smoketest: verify Korean TTS can run in Anki's Python env.

    This does not touch the GUI, media folder, or any collections. It only
    checks that the add-on can import MeloTTS and synthesize a short sample
    sentence into a temporary wav file.
    """

    from tempfile import NamedTemporaryFile

    sample_text = "안녕하세요, 이것은 한국어 TTS 테스트입니다."

    try:
        with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = tmp.name

        if synthesize_korean_tts is not None:
            synthesize_korean_tts(
                sample_text,
                temp_path,
                device="auto",
            )
        else:
            model = get_tts_model()
            if not model:
                print("Korean TTS smoketest: model not available")
                return False
            speaker_ids = model.hps.data.spk2id
            speaker_id = getattr(
                speaker_ids,
                "KR",
                list(speaker_ids.values())[0],
            )
            model.tts_to_file(
                sample_text,
                speaker_id,
                temp_path,
                quiet=True,
            )

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            print(
                "Korean TTS smoketest: output file missing or empty:",
                temp_path,
            )
            return False

        os.unlink(temp_path)
        print("Korean TTS smoketest OK")
        return True

    except Exception as e:
        print("Korean TTS smoketest FAILED:", e)
        return False


def init_addon() -> None:
    """Initialize the add-on."""
    # Always set up the menu and hooks, even if MeloTTS isn't available yet
    # The menu item will show an error when clicked if MeloTTS isn't available
    setup_menu()
    setup_hooks()
    
    if not MELOTTS_AVAILABLE:
        if mw:
            tooltip("Korean TTS add-on loaded, but MeloTTS library not found. Please check paths.")
    else:
        if mw:
            tooltip("Korean TTS add-on loaded successfully!")


# Initialize when Anki loads (only in real Anki GUI, not in headless tests)
if _ANKI_GUI_AVAILABLE and os.environ.get("ANKI_IMPORT_ONLY") is None:
    if mw:
        init_addon()
    elif gui_hooks is not None:
        # If mw is not available yet, wait for it
        def on_profile_loaded() -> None:
            init_addon()

        gui_hooks.profile_did_open.append(on_profile_loaded)
