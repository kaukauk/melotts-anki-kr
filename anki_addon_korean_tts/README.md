# Korean Text-to-Speech Add-on for Anki

This add-on provides Korean text-to-speech functionality for Anki flashcards using MeloTTS.

## Features

- **Automatic Korean Text Detection**: Automatically detects Korean text (Hangul) in your flashcards
- **On-Demand TTS Generation**: Generate TTS audio for individual cards with a single click
- **Batch Processing**: Generate TTS for all cards in your collection with Korean text
- **Play Buttons**: Automatically adds play buttons to cards with Korean text
- **Model Caching**: The TTS model is loaded once and cached to avoid reloading delays

## Installation

1. Copy the `anki_addon_korean_tts` folder to your Anki add-ons directory:
   - **Windows**: `%APPDATA%\Anki2\addons21\korean_tts`
   - **macOS**: `~/Library/Application Support/Anki2/addons21/korean_tts`
   - **Linux**: `~/.local/share/Anki2/addons21/korean_tts`

2. Ensure MeloTTS is installed:
   ```bash
   pip install melotts
   ```

3. (Optional) For offline usage, place the Korean model files in the `MeloTTS-Korean` directory:
   - `config.json`
   - `checkpoint.pth`

## Usage

### Generating TTS for a Single Card

1. While reviewing a card with Korean text, click the **"🎤 Generate Korean TTS"** button
2. The add-on will generate the audio and add it to the card
3. The button will change to **"🔊 Play Korean"** for future reviews

### Batch Generating TTS for All Cards

1. Go to **Tools** → **Generate Korean TTS for All Cards**
2. Confirm the operation
3. The add-on will process all cards with Korean text and generate audio files

### Playing Audio

- Click the **"🔊 Play Korean"** button on any card with Korean audio
- The audio will play automatically when the card is shown (if autoplay is enabled)

## How It Works

1. **Korean Text Detection**: The add-on scans card fields for Korean characters (Hangul)
2. **Audio Generation**: Uses MeloTTS to generate high-quality Korean speech
3. **Media Management**: Audio files are stored in Anki's media folder and embedded using `[sound:filename]` tags
4. **UI Integration**: Play buttons are automatically added to cards via Anki's card rendering hooks

## Requirements

- Anki 2.1.50 or later
- Python 3.8 or later
- MeloTTS library
- (Optional) PyTorch with CUDA support for faster generation

## Troubleshooting

### "MeloTTS is not available" Error

- Ensure MeloTTS is installed: `pip install melotts`
- Check that MeloTTS is in your Python path
- Verify the installation: `python -c "from melo.api import TTS; print('OK')"`

### Model Loading Issues

- For offline usage, ensure `MeloTTS-Korean/config.json` and `MeloTTS-Korean/checkpoint.pth` exist
- For online usage, ensure you have internet access for the first model download

### Audio Not Playing

- Check that the audio file exists in Anki's media folder
- Verify the `[sound:filename]` tag is correctly added to the field
- Try regenerating the audio for the card

## License

This add-on is licensed under the GNU AGPL, version 3 or later.

## Credits

- Uses [MeloTTS](https://github.com/myshell-ai/MeloTTS) for text-to-speech synthesis
- Built for Anki by the community

