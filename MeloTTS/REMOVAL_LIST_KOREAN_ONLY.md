# Files/Folders to Remove for Korean-Only TTS

This list identifies what can be safely removed to strip down MeloTTS to only Korean TTS functionality while maintaining the same quality.

## ✅ KEEP (Essential for Korean TTS)

### Core Framework
- `melo/__init__.py`
- `melo/api.py` - Main TTS API
- `melo/models.py` - Model architecture
- `melo/utils.py` - Utility functions
- `melo/commons.py` - Common utilities
- `melo/modules.py` - Neural network modules
- `melo/attentions.py` - Attention mechanisms
- `melo/transforms.py` - Transform functions
- `melo/mel_processing.py` - Mel spectrogram processing
- `melo/split_utils.py` - Sentence splitting
- `melo/download_utils.py` - Model downloading (can be simplified)
- `melo/monotonic_align/` - Alignment module

### Korean-Specific
- `melo/text/korean.py` - Korean text processing
- `melo/text/ko_dictionary.py` - Korean dictionary
- `melo/text/japanese_bert.py` - BERT feature extraction (used by Korean)
- `melo/text/symbols.py` - Symbol definitions
- `melo/text/punctuation.py` - Punctuation handling
- `melo/text/cleaner.py` - Text cleaning (modified for lazy loading)
- `melo/text/__init__.py` - Text module init (modified for lazy loading)

### Configuration & Setup
- `setup.py` - Package setup
- `requirements.txt` - Dependencies
- `LICENSE` - License file
- `test_korean_tts.py` - Korean test script
- `test_korean_tts_offline.py` - Offline test script

---

## ❌ REMOVE (Not needed for Korean TTS)

### Other Language Modules
- `melo/text/chinese.py`
- `melo/text/chinese_bert.py`
- `melo/text/chinese_mix.py`
- `melo/text/japanese.py` (NOTE: Keep `japanese_bert.py` - it's used by Korean!)
- `melo/text/english.py`
- `melo/text/english_bert.py`
- `melo/text/french.py`
- `melo/text/french_bert.py`
- `melo/text/spanish.py`
- `melo/text/spanish_bert.py`

### Language-Specific Phonemizers
- `melo/text/es_phonemizer/` - Entire directory (Spanish phonemizer)
- `melo/text/fr_phonemizer/` - Entire directory (French phonemizer)
- `melo/text/english_utils/` - Entire directory (English utilities)

### Language-Specific Data Files
- `melo/text/cmudict_cache.pickle` - English CMU dictionary cache
- `melo/text/cmudict.rep` - English CMU dictionary
- `melo/text/opencpop-strict.txt` - Chinese data
- `melo/text/tone_sandhi.py` - Chinese tone sandhi
- `melo/text/cleaner_multiling.py` - Multilingual cleaner (not used with lazy loading)

### Training & Development Files
- `melo/train.py` - Training script
- `melo/train.sh` - Training shell script
- `melo/data_utils.py` - Data utilities for training
- `melo/losses.py` - Loss functions for training
- `melo/preprocess_text.py` - Text preprocessing for training
- `melo/infer.py` - Custom inference script (not needed if using api.py)
- `melo/init_downloads.py` - Script to download all models

### UI & CLI (Optional - remove if you only use Python API)
- `melo/app.py` - Gradio web UI
- `melo/main.py` - CLI interface

### Test Files (Other Languages)
- `test/test_base_model_tts_package.py` - General test
- `test/test_base_model_tts_package_from_S3.py` - S3 test
- `test/basetts_test_resources/en_egs_text.txt` - English examples
- `test/basetts_test_resources/es_egs_text.txt` - Spanish examples
- `test/basetts_test_resources/fr_egs_text.txt` - French examples
- `test/basetts_test_resources/jp_egs_text.txt` - Japanese examples
- `test/basetts_test_resources/zh_mix_en_egs_text.txt` - Chinese examples
- **KEEP**: `test/basetts_test_resources/kr_egs_text.txt` - Korean examples

### Documentation (Optional)
- `docs/` - Entire directory (can remove if not needed)
- `README.md` - Main README (optional, but useful to keep)
- `logo.png` - Logo (optional)

### Build & Deployment
- `Dockerfile` - Docker setup (if not using Docker)
- `melotts.egg-info/` - Build metadata (regenerated on install)
- `.github/` - GitHub workflows (if not using CI/CD)

### Example Data
- `melo/data/example/` - Example training data

### Config Files (Other Languages)
- `melo/configs/config.json` - Base config (may not be needed if using MeloTTS-Korean config)

### Cache & Build Artifacts
- `melo/__pycache__/` - Python cache (auto-generated)
- `melo/text/__pycache__/` - Python cache
- `melo/monotonic_align/__pycache__/` - Python cache
- `*.pyc` - Compiled Python files
- `*.wav` - Generated audio files (test outputs)

### Virtual Environment (Keep if using, remove if packaging)
- `venv/` - Virtual environment (keep if you're using it, remove if packaging for distribution)

---

## 📋 Quick Removal Commands

### Remove Other Language Modules
```bash
cd MeloTTS
rm -rf melo/text/chinese*.py
rm -rf melo/text/english*.py
rm -rf melo/text/french*.py
rm -rf melo/text/spanish*.py
rm -f melo/text/japanese.py  # Keep japanese_bert.py!
rm -rf melo/text/es_phonemizer/
rm -rf melo/text/fr_phonemizer/
rm -rf melo/text/english_utils/
```

### Remove Training Files
```bash
rm -f melo/train.py melo/train.sh
rm -f melo/data_utils.py melo/losses.py melo/preprocess_text.py
rm -f melo/infer.py melo/init_downloads.py
```

### Remove UI/CLI (if not needed)
```bash
rm -f melo/app.py melo/main.py
```

### Remove Test Files (Other Languages)
```bash
rm -f test/test_base_model_tts_package*.py
rm -f test/basetts_test_resources/en_egs_text.txt
rm -f test/basetts_test_resources/es_egs_text.txt
rm -f test/basetts_test_resources/fr_egs_text.txt
rm -f test/basetts_test_resources/jp_egs_text.txt
rm -f test/basetts_test_resources/zh_mix_en_egs_text.txt
```

### Remove Language-Specific Data
```bash
rm -f melo/text/cmudict*.pickle melo/text/cmudict.rep
rm -f melo/text/opencpop-strict.txt
rm -f melo/text/tone_sandhi.py
rm -f melo/text/cleaner_multiling.py
```

### Remove Documentation (optional)
```bash
rm -rf docs/
rm -f logo.png
```

### Remove Build Artifacts
```bash
rm -rf melotts.egg-info/
rm -rf melo/__pycache__/
rm -rf melo/text/__pycache__/
rm -rf melo/monotonic_align/__pycache__/
rm -f *.wav  # Generated test files
```

### Remove Docker & CI (if not needed)
```bash
rm -f Dockerfile
rm -rf .github/
```

### Remove Example Data
```bash
rm -rf melo/data/
```

---

## 📊 Estimated Size Reduction

**Before**: ~1.8GB (MeloTTS directory)
**After**: ~50-100MB (Korean-only)

**Savings**: ~95% reduction in size

---

## ⚠️ Important Notes

1. **Keep `japanese_bert.py`** - Korean TTS uses this for BERT feature extraction
2. **Keep `cleaner.py` and `__init__.py`** - But they're already modified for lazy loading
3. **Test after removal** - Run `test_korean_tts.py` to ensure everything still works
4. **Virtual environment** - Keep `venv/` if you're using it, or remove if packaging

---

## ✅ Verification

After removal, test with:
```bash
cd MeloTTS
source venv/bin/activate
python test_korean_tts.py
```

If it works, you've successfully stripped it down to Korean-only! 🎉

