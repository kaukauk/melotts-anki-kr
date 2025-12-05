# Installation Guide

## Quick Start

1. **Locate your Anki add-ons folder:**
   - **Windows**: `%APPDATA%\Anki2\addons21\`
   - **macOS**: `~/Library/Application Support/Anki2/addons21/`
   - **Linux**: `~/.local/share/Anki2/addons21/`

2. **Copy the add-on:**
   - Copy the entire `anki_addon_korean_tts` folder to your add-ons directory
   - Rename it to `korean_tts` (remove the `anki_addon_` prefix)
   - Final path should be: `addons21/korean_tts/`

3. **Install MeloTTS:**
   ```bash
   pip install melotts
   ```

4. **Restart Anki:**
   - Close and reopen Anki
   - The add-on should load automatically

## Verification

After restarting Anki:

1. Go to **Tools** → **Add-ons**
2. You should see "Korean Text-to-Speech" in the list
3. Create a test card with Korean text (e.g., "안녕하세요")
4. Start reviewing the card - you should see a "Generate Korean TTS" button

## Troubleshooting

### Add-on not appearing
- Check that the folder is named `korean_tts` (not `anki_addon_korean_tts`)
- Verify the folder contains `__init__.py` and `manifest.json`
- Check Anki's add-ons folder path is correct

### MeloTTS import error
- Run: `python -c "from melo.api import TTS; print('OK')"`
- If it fails, install: `pip install melotts`
- On some systems, you may need: `pip3 install melotts`

### Model loading issues
- First run will download the model from HuggingFace (requires internet)
- For offline use, place model files in `MeloTTS-Korean/` directory
- Check that `config.json` and `checkpoint.pth` exist

## Next Steps

- See [README.md](README.md) for usage instructions
- Test with a few cards before batch processing
- The model loads once and is cached for faster subsequent use

