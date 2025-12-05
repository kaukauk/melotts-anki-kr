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
from pathlib import Path
from typing import Any

import aqt
from aqt import gui_hooks, mw
from aqt.qt import *
from aqt.utils import showInfo, showWarning, tooltip

# Add MeloTTS to path if available
# Use the local MeloTTS directory in the project
_melotts_path = Path("/home/kaustubh/Documents/GitHub/melotts-all/MeloTTS")
if _melotts_path.exists():
    # Add MeloTTS directory to path so we can import melo
    sys.path.insert(0, str(_melotts_path))

try:
    from melo.api import TTS
    MELOTTS_AVAILABLE = True
except ImportError:
    MELOTTS_AVAILABLE = False
    TTS = None

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
            korean_model_dir = Path("/home/kaustubh/Documents/GitHub/melotts-all/MeloTTS-Korean")
            
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


def add_play_button_to_card(text: str, card: Any, kind: str) -> str:
    """Add a play button to cards that contain Korean text."""
    if not mw or not mw.col:
        return text
    
    # Only process review cards
    if kind not in ["reviewQuestion", "reviewAnswer"]:
        return text
    
    # Extract Korean text
    korean_text = extract_korean_text(text)
    
    if not korean_text or not contains_korean(korean_text):
        return text
    
    # Check if audio already exists for this card
    note = card.note()
    if not note:
        return text
    
    # Look for existing sound tags
    has_audio = '[sound:' in text
    
    # Add play button
    if has_audio:
        # Audio already exists, add play button
        play_button = (
            '<div style="margin: 10px 0;">'
            '<button onclick="pycmd(\'play_korean_tts\');" '
            'style="padding: 8px 16px; cursor: pointer; '
            'background: #4CAF50; color: white; border: none; border-radius: 4px; '
            'font-size: 14px; font-weight: bold;">'
            '🔊 Play Korean</button>'
            '</div>'
        )
    else:
        # No audio yet, add a button to generate it
        play_button = (
            '<div style="margin: 10px 0;">'
            '<button onclick="pycmd(\'generate_korean_tts\');" '
            'style="padding: 8px 16px; cursor: pointer; '
            'background: #2196F3; color: white; border: none; border-radius: 4px; '
            'font-size: 14px; font-weight: bold;">'
            '🎤 Generate Korean TTS</button>'
            '</div>'
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
    
    # Generate TTS
    try:
        # Generate audio file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_path = tmp.name
        
        speaker_ids = model.hps.data.spk2id
        speaker_id = speaker_ids.get('KR', list(speaker_ids.values())[0])
        
        model.tts_to_file(korean_text, speaker_id, temp_path, quiet=True)
        
        # Add to Anki media folder
        media_manager = mw.col.media
        filename = f"korean_tts_{note.id}_{korean_field}.wav"
        final_filename = media_manager.add_file(temp_path)
        
        # Clean up temp file
        os.unlink(temp_path)
        
        # Add sound tag to the field
        current_value = note[korean_field]
        if '[sound:' not in current_value:
            note[korean_field] = current_value + f' [sound:{final_filename}]'
            note.flush()
            mw.col.notes.update_notes([note])
        
        tooltip("Korean TTS generated successfully!")
        
        # Refresh the card
        reviewer._redraw_current_card()
        
    except Exception as e:
        showWarning(f"Failed to generate Korean TTS: {e}")
    
    return True


def batch_generate_tts() -> None:
    """Batch generate TTS for all cards with Korean text."""
    if not mw or not mw.col:
        return
    
    model = get_tts_model()
    if not model:
        showWarning("Korean TTS model is not available. Please check MeloTTS installation.")
        return
    
    # Get all notes
    note_ids = mw.col.find_notes("")
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
    
    from aqt.progress import ProgressManager
    
    mgr = mw.progress
    mgr.start(max=total_notes, label="Generating Korean TTS...", immediate=True)
    
    try:
        for i, note_id in enumerate(note_ids):
            mgr.update(f"Processing note {i+1}/{total_notes}...", value=i)
            
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
                
                # Check if audio already exists
                if '[sound:' in note[korean_field]:
                    processed += 1
                    continue
                
                # Generate TTS
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                    temp_path = tmp.name
                
                speaker_ids = model.hps.data.spk2id
                speaker_id = speaker_ids.get('KR', list(speaker_ids.values())[0])
                
                model.tts_to_file(korean_text, speaker_id, temp_path, quiet=True)
                
                # Add to Anki media folder
                filename = f"korean_tts_{note.id}_{korean_field}.wav"
                final_filename = mw.col.media.add_file(temp_path)
                
                # Clean up temp file
                os.unlink(temp_path)
                
                # Add sound tag to the field
                current_value = note[korean_field]
                note[korean_field] = current_value + f' [sound:{final_filename}]'
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
        f"Batch generation complete!\n\n"
        f"Processed: {processed} notes\n"
        f"Generated: {generated} audio files\n"
        f"Errors: {errors}"
    )


def setup_menu() -> None:
    """Add menu items to Anki."""
    if not mw:
        return
    
    action = QAction("Generate Korean TTS for All Cards", mw)
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


def init_addon() -> None:
    """Initialize the add-on."""
    if not MELOTTS_AVAILABLE:
        showWarning(
            "Korean TTS add-on could not import the local MeloTTS library.\n\n"
            "It is configured to use the MeloTTS directory in this project,\n"
            "not a pip-installed package.\n\n"
            "Please ensure that Anki's Python environment has all MeloTTS\n"
            "dependencies installed (torch, numpy, librosa, soundfile,\n"
            "torchaudio, tqdm, cached_path, etc.)."
        )
        return
    
    setup_menu()
    setup_hooks()
    
    if mw:
        tooltip("Korean TTS add-on loaded successfully!")


# Initialize when Anki loads
if mw:
    init_addon()
else:
    # If mw is not available yet, wait for it
    def on_profile_loaded():
        init_addon()
    
    gui_hooks.profile_did_open.append(on_profile_loaded)
