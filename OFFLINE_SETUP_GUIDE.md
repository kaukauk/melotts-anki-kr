# Korean TTS Offline Setup Guide

## Current Status: **PARTIALLY OFFLINE**

The current setup works **mostly offline** but still requires:
1. ✅ **TTS Model** - Can use local files from `MeloTTS-Korean/`
2. ⚠️ **BERT Model** - Currently loads from HuggingFace cache (needs internet on first run)

## Minimal Files Needed for Full Offline Operation

### 1. TTS Model Files (Already Available)
- **Location**: `MeloTTS-Korean/`
- **Files**:
  - `checkpoint.pth` (198MB) - TTS model weights
  - `config.json` (3.3KB) - Model configuration
- **Total**: ~198MB

### 2. BERT Model Files (Currently in HuggingFace Cache)
- **Model**: `kykim/bert-kor-base`
- **Location**: `~/.cache/huggingface/hub/models--kykim--bert-kor-base/`
- **Required Files**:
  - `config.json` - BERT model configuration
  - `pytorch_model.bin` or `model.safetensors` - Model weights (~400MB)
  - `tokenizer_config.json` - Tokenizer configuration
  - `vocab.txt` - Vocabulary file
  - `tokenizer.json` - Tokenizer data
- **Total**: ~908MB (entire cache directory)

### 3. Framework Code
- **Location**: `MeloTTS/` directory
- **Size**: ~1.8GB (includes all language support, but only Korean is needed)

## Total Minimal Size for Korean TTS Offline

**Minimum Required:**
- TTS Model: 198MB
- BERT Model: ~400-500MB (just the model files, not entire cache)
- Framework: ~50-100MB (minimal subset, or full 1.8GB if keeping all languages)
- **Total: ~650-700MB** (minimal) or **~2.9GB** (full setup)

## How to Make It Fully Offline

### Option 1: Use Local BERT Model Path (Recommended)

Modify `MeloTTS/melo/text/korean.py` to use a local BERT model:

```python
# Change line 94 from:
model_id = 'kykim/bert-kor-base'

# To:
model_id = '/path/to/local/bert-kor-base'  # Local directory path
```

Then copy the BERT model from HuggingFace cache:
```bash
# Find the snapshot directory
BERT_SNAPSHOT=$(find ~/.cache/huggingface/hub/models--kykim--bert-kor-base/snapshots -type d -mindepth 1 -maxdepth 1 | head -1)

# Copy to a local directory
mkdir -p /path/to/local/bert-kor-base
cp -r $BERT_SNAPSHOT/* /path/to/local/bert-kor-base/
```

### Option 2: Set HuggingFace Offline Mode

The BERT model will use cached files if available:
```python
import os
os.environ['HF_HUB_OFFLINE'] = '1'  # Force offline mode
```

## Testing Offline Operation

1. **Disconnect from internet**
2. **Run the offline test script**:
   ```bash
   cd MeloTTS
   source venv/bin/activate
   python test_korean_tts_offline.py
   ```

If the BERT model is already cached, it should work offline.

## Summary

**Current Setup:**
- ✅ TTS model: Fully offline (using local files)
- ⚠️ BERT model: Uses HuggingFace cache (works offline if already downloaded)

**To Make Fully Offline:**
- Copy BERT model from cache to a local directory
- Modify code to use local path OR ensure cache is present
- **Minimal size: ~650-700MB** (TTS model + BERT model + minimal framework)

