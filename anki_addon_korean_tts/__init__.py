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

# Add MeloTTS to path if available
# Use the local MeloTTS directory in the project
_melotts_path = Path("/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS")
if _melotts_path.exists():
    # Add MeloTTS directory to path so we can import melo
    sys.path.insert(0, str(_melotts_path))

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
# Remote TTS configuration
# -----------------------------------------------------------------------------

# Base URL for the remote Korean TTS server.
#
# Default behaviour:
#
# - If KOREAN_TTS_SERVER_URL is set, use it as-is.
# - Otherwise, default to the MeloTTS HTTP server running on the *server*
#   machine (tts-server.your-tailnet.ts.net) on port 8000:
#       http://tts-server.your-tailnet.ts.net:8000
#   This matches the uvicorn command we run there.
# - On startup we will also auto-detect a local development server on
#   http://127.0.0.1:8000 when Anki and the server are running on the same
#   machine.
_DEFAULT_REMOTE_HOST = "tts-server.your-tailnet.ts.net"
_DEFAULT_REMOTE_HTTP_URL = f"http://{_DEFAULT_REMOTE_HOST}:8000"

_REMOTE_TTS_BASE_URL = _DEFAULT_REMOTE_HTTP_URL
_REMOTE_TTS_ENDPOINT = _REMOTE_TTS_BASE_URL.rstrip("/") + "/api/v1/tts/korean"

# Optional shared secret for simple API-key based auth. When set on both the
# server and the client, requests must include this value in X-API-Key.
_REMOTE_TTS_API_KEY = os.environ.get("KOREAN_TTS_SERVER_API_KEY") or None

# Network timeouts (in seconds) for calls to the TTS server.
_REMOTE_TTS_CONNECT_TIMEOUT = 3.0
_REMOTE_TTS_READ_TIMEOUT = 60.0

# Feature flag: allow disabling remote TTS entirely via environment, e.g. for
# fully offline usage or debugging.
_REMOTE_TTS_ENABLED = os.environ.get("KOREAN_TTS_REMOTE_ENABLED", "1") not in (
    "",
    "0",
    "false",
    "False",
)


def _autodetect_local_server() -> None:
    """Disabled local-autodetect in this configuration.

    We always target the explicit KOREAN_TTS_SERVER_URL or the default remote
    host (tts-server.your-tailnet.ts.net:8000), and avoid probing
    127.0.0.1:8000 from inside Anki, as that can be misleading when Anki runs
    on a different machine than the TTS server.
    """

    # Intentionally a no-op: leave _REMOTE_TTS_BASE_URL as configured above.
    return


_autodetect_local_server()


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
    # presented by tts-server.your-tailnet.ts.net (e.g. via Tailscale).
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
            # Try to use offline model first
            korean_model_dir = Path("/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS-Korean")
            
            if korean_model_dir.exists():
                config_path = korean_model_dir / "config.json"
                ckpt_path = korean_model_dir / "checkpoint.pth"
            else:
                config_path = None
                ckpt_path = None
            
            if config_path and ckpt_path and config_path.exists() and ckpt_path.exists():
                # Use offline model
                _tts_model = TTS(
                    language='KR',
                    device='auto',
                    config_path=str(config_path),
                    ckpt_path=str(ckpt_path),
                    use_hf=False
                )
            else:
                # Use online model (downloads from HuggingFace)
                _tts_model = TTS(language='KR', device='auto')
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
