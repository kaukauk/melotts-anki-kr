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
from typing import Any

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

# Global TTS model instance (cached to avoid reloading)
_tts_model: TTS | None = None


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
    
    model = get_tts_model()
    if not model:
        showWarning("Korean TTS model is not available. Please check MeloTTS installation.")
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
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_path = tmp.name

        if synthesize_korean_tts is not None:
            synthesize_korean_tts(
                korean_text,
                temp_path,
                device="auto",
            )
        else:
            model = get_tts_model()
            if not model:
                showWarning(
                    "Korean TTS model is not available. Please check MeloTTS installation."
                )
                return True
            speaker_ids = model.hps.data.spk2id
            speaker_id = getattr(
                speaker_ids,
                "KR",
                list(speaker_ids.values())[0],
            )
            model.tts_to_file(
                korean_text, speaker_id, temp_path, quiet=True
            )

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


def batch_generate_tts() -> None:
    """Batch generate TTS for all notes with Korean text in the current deck."""
    if not mw or not mw.col:
        return
    
    model = None
    if synthesize_korean_tts is None:
        # Fallback to direct TTS usage if the high-level endpoint is unavailable.
        model = get_tts_model()
        if not model:
            showWarning(
                "Korean TTS model is not available. Please check MeloTTS installation."
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

                # Generate TTS
                import tempfile

                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as tmp:
                    temp_path = tmp.name

                if synthesize_korean_tts is not None:
                    synthesize_korean_tts(
                        korean_text,
                        temp_path,
                        device="auto",
                    )
                else:
                    assert model is not None
                    speaker_ids = model.hps.data.spk2id
                    # HParams behaves like a dict but has no .get(), so use getattr().
                    speaker_id = getattr(
                        speaker_ids, "KR", list(speaker_ids.values())[0]
                    )
                    model.tts_to_file(
                        korean_text, speaker_id, temp_path, quiet=True
                    )

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


def setup_menu() -> None:
    """Add menu items to Anki."""
    if not mw:
        return
    
    # Add a separator before our menu item to put it at the bottom
    mw.form.menuTools.addSeparator()
    
    action = QAction("Generate Korean TTS for Current Deck", mw)
    action.triggered.connect(batch_generate_tts)
    mw.form.menuTools.addAction(action)


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

            # Reuse batch logic but restricted to these notes
            model = get_tts_model()
            if not model:
                showWarning(
                    "Korean TTS model is not available. Please check MeloTTS installation."
                )
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

                        if synthesize_korean_tts is not None:
                            synthesize_korean_tts(
                                korean_text,
                                temp_path,
                                device="auto",
                            )
                        else:
                            assert model is not None
                            speaker_ids = model.hps.data.spk2id
                            speaker_id = getattr(
                                speaker_ids,
                                "KR",
                                list(speaker_ids.values())[0],
                            )

                            model.tts_to_file(
                                korean_text, speaker_id, temp_path, quiet=True
                            )

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
