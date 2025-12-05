# Minimal Offline Korean TTS Setup

## Answer: Does it work fully offline?

**Current Status: YES, but requires initial download**

✅ **Works offline** if:
1. TTS model files are local (you have `MeloTTS-Korean/`)
2. BERT model is cached (already downloaded to `~/.cache/huggingface/`)

⚠️ **First run requires internet** to download the BERT model (`kykim/bert-kor-base`)

## Minimal Files Needed for Offline Korean TTS

### Essential Files (Total: ~650MB)

#### 1. TTS Model (199MB)
**Location**: `MeloTTS-Korean/`
- `checkpoint.pth` - **198MB** (TTS model weights)
- `config.json` - **4KB** (model configuration)

#### 2. BERT Model (~454MB)
**Location**: `~/.cache/huggingface/hub/models--kykim--bert-kor-base/`
**Required files** (from snapshot directory):
- `pytorch_model.bin` or `model.safetensors` - **454MB** (BERT weights - only need ONE)
- `config.json` - **725 bytes** (BERT config)
- `tokenizer_config.json` - **80 bytes** (tokenizer config)
- `vocab.txt` - **337KB** (vocabulary)
- `tokenizer.json` - (if exists, for tokenizer)

**Actual minimal size**: ~454MB (just the model file + small config files)

#### 3. Framework Code (~22MB minimum)
**Location**: `MeloTTS/melo/`
- Core TTS engine code
- Korean text processing modules
- Can be reduced further by removing unused language modules

### Total Minimal Size: **~675MB**
- TTS Model: 199MB
- BERT Model: 454MB  
- Framework: 22MB

## How to Use Offline

### Method 1: Use Local TTS Model (Already Working)

```python
from melo.api import TTS

model = TTS(
    language='KR',
    device='cpu',
    config_path='../MeloTTS-Korean/config.json',
    ckpt_path='../MeloTTS-Korean/checkpoint.pth',
    use_hf=False  # Don't download TTS model
)
```

The BERT model will automatically use cached files if available.

### Method 2: Force Offline Mode

```python
import os
os.environ['HF_HUB_OFFLINE'] = '1'  # Force HuggingFace to use cache only

from melo.api import TTS
model = TTS(language='KR', device='cpu', use_hf=False)
```

### Method 3: Copy BERT Model to Local Directory (Fully Portable)

```bash
# 1. Find the BERT snapshot
BERT_SNAPSHOT=$(find ~/.cache/huggingface/hub/models--kykim--bert-kor-base/snapshots -type d -mindepth 1 -maxdepth 1 | head -1)

# 2. Create local directory
mkdir -p ./local_models/bert-kor-base

# 3. Copy essential files (resolve symlinks to actual blobs)
cp -L $BERT_SNAPSHOT/pytorch_model.bin ./local_models/bert-kor-base/
cp -L $BERT_SNAPSHOT/config.json ./local_models/bert-kor-base/
cp -L $BERT_SNAPSHOT/tokenizer_config.json ./local_models/bert-kor-base/
cp -L $BERT_SNAPSHOT/vocab.txt ./local_models/bert-kor-base/
if [ -f $BERT_SNAPSHOT/tokenizer.json ]; then
    cp -L $BERT_SNAPSHOT/tokenizer.json ./local_models/bert-kor-base/
fi
```

Then modify `MeloTTS/melo/text/korean.py`:
```python
# Change line 94 from:
model_id = 'kykim/bert-kor-base'
# To:
model_id = './local_models/bert-kor-base'  # Local path
```

## File Structure for Minimal Offline Setup

```
offline-korean-tts/
├── MeloTTS-Korean/
│   ├── checkpoint.pth      (198MB)
│   └── config.json         (4KB)
├── bert-kor-base/          (or in HuggingFace cache)
│   ├── pytorch_model.bin   (454MB)
│   ├── config.json         (725 bytes)
│   ├── tokenizer_config.json (80 bytes)
│   └── vocab.txt           (337KB)
└── MeloTTS/                (framework code)
    └── melo/                (22MB)
```

## Testing Offline Operation

1. **Disconnect from internet**
2. **Run offline test**:
   ```bash
   cd MeloTTS
   source venv/bin/activate
   python test_korean_tts_offline.py
   ```

## Summary

✅ **Current setup works offline** (after initial download)
- TTS model: Uses local files from `MeloTTS-Korean/`
- BERT model: Uses HuggingFace cache (works if already downloaded)

📦 **Minimal portable size: ~675MB**
- TTS: 199MB
- BERT: 454MB
- Framework: 22MB

🔧 **To make fully portable**: Copy BERT model from cache to local directory and modify code to use local path.

