# Strip to Korean-Only Script

## Quick Start

Run the script to automatically strip MeloTTS down to Korean-only:

```bash
cd MeloTTS
./strip_to_korean_only.sh
```

## Options

### Basic Usage (with backup)
```bash
./strip_to_korean_only.sh
```
- Creates a backup before removing files
- Keeps UI/CLI and documentation

### No Backup
```bash
./strip_to_korean_only.sh --no-backup
```
- Skips backup creation (faster, but no safety net)

### Remove UI and CLI
```bash
./strip_to_korean_only.sh --remove-ui
```
- Removes `app.py` (Gradio web UI) and `main.py` (CLI)
- Use this if you only need the Python API

### Remove Documentation
```bash
./strip_to_korean_only.sh --remove-docs
```
- Removes `docs/` directory and `logo.png`

### Combine Options
```bash
./strip_to_korean_only.sh --no-backup --remove-ui --remove-docs
```
- Maximum reduction: no backup, no UI, no docs

## What Gets Removed

1. **Other Language Modules** (Chinese, Japanese, English, French, Spanish)
2. **Phonemizer Directories** (Spanish, French, English utilities)
3. **Language-Specific Data** (CMU dict, Chinese data, etc.)
4. **Training Files** (train.py, data_utils.py, losses.py, etc.)
5. **Test Files** (other languages, keeps Korean tests)
6. **Build Artifacts** (cache, compiled Python files, generated audio)
7. **Docker & CI** (Dockerfile, .github workflows)
8. **Example Data** (training examples)

## What Gets Kept

✅ **Essential Korean Files:**
- `melo/text/korean.py`
- `melo/text/ko_dictionary.py`
- `melo/text/japanese_bert.py` (used by Korean)
- `melo/text/symbols.py`
- `melo/text/punctuation.py`
- `melo/text/cleaner.py`
- `melo/text/__init__.py`

✅ **Core Framework:**
- All core TTS engine files (api.py, models.py, utils.py, etc.)
- Neural network modules
- Audio processing

✅ **Test Scripts:**
- `test_korean_tts.py`
- `test_korean_tts_offline.py`
- Korean test examples

## Safety Features

1. **Backup Creation** (default): Creates timestamped backup before removal
2. **Verification**: Checks that all essential files are present after removal
3. **Error Handling**: Exits on error, won't continue if something goes wrong

## After Running

1. **Test the setup:**
   ```bash
   source venv/bin/activate
   python test_korean_tts.py
   ```

2. **If everything works**, you can remove the backup:
   ```bash
   rm -rf backup_before_strip_*
   ```

3. **If something broke**, restore from backup:
   ```bash
   cp -r backup_before_strip_*/melo ./melo
   ```

## Size Reduction

- **Before**: ~1.8GB
- **After**: ~50-100MB
- **Reduction**: ~95%

## Troubleshooting

### Script won't run
```bash
chmod +x strip_to_korean_only.sh
```

### "korean.py not found" error
Make sure you're in the MeloTTS directory:
```bash
cd /path/to/MeloTTS
./strip_to_korean_only.sh
```

### Test fails after stripping
Restore from backup and check the removal list manually.

## Manual Removal

If you prefer to remove files manually, see `REMOVAL_LIST_KOREAN_ONLY.md` for detailed instructions.

