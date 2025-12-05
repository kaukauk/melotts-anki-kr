# Korean-Only TTS: Removal Summary

## Quick Answer

**Total files in `melo/text/`**: 35 Python files
**Essential for Korean**: 10 files
**Can be removed**: 25 files (~224KB of code)

## Essential Files for Korean TTS (KEEP)

### Core Text Processing
1. `melo/text/korean.py` - Korean text processing
2. `melo/text/ko_dictionary.py` - Korean dictionary
3. `melo/text/japanese_bert.py` - BERT feature extraction (used by Korean)
4. `melo/text/symbols.py` - Symbol definitions
5. `melo/text/punctuation.py` - Punctuation handling
6. `melo/text/cleaner.py` - Text cleaning (lazy loading)
7. `melo/text/__init__.py` - Module init (lazy loading)

### Framework Core (Keep All)
- All files in `melo/` except training/UI files
- See REMOVAL_LIST_KOREAN_ONLY.md for details

## Files to Remove

### Language Modules (Remove)
- `chinese.py`, `chinese_bert.py`, `chinese_mix.py`
- `japanese.py` (but KEEP `japanese_bert.py`)
- `english.py`, `english_bert.py`
- `french.py`, `french_bert.py`
- `spanish.py`, `spanish_bert.py`

### Phonemizers (Remove Entire Directories)
- `es_phonemizer/` - Spanish phonemizer
- `fr_phonemizer/` - French phonemizer
- `english_utils/` - English utilities

### Data Files (Remove)
- `cmudict_cache.pickle`, `cmudict.rep` - English dictionary
- `opencpop-strict.txt` - Chinese data
- `tone_sandhi.py` - Chinese tone rules
- `cleaner_multiling.py` - Multilingual cleaner

### Training Files (Remove)
- `train.py`, `train.sh`
- `data_utils.py`, `losses.py`, `preprocess_text.py`
- `infer.py`, `init_downloads.py`

### UI/CLI (Optional - Remove if not using)
- `app.py` - Web UI
- `main.py` - CLI

### Tests (Remove Other Languages)
- All test files except Korean examples

## Size Impact

**Current**: ~1.8GB (full MeloTTS)
**After removal**: ~50-100MB (Korean-only)
**Reduction**: ~95%

## Complete Removal Script

See `REMOVAL_LIST_KOREAN_ONLY.md` for detailed removal commands.

## Verification

After removal, test with:
```bash
python test_korean_tts.py
```

If it works, you've successfully created a Korean-only TTS system! ✅

