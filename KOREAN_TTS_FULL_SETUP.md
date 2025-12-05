## Overview

This document records **everything that was required to get this repository fully running with the Korean TTS add-on using the local MeloTTS checkout**, including all environment tweaks and debugging steps.

It assumes:

- You are on Linux (tested on Arch).
- Your clone is at  
  `/home/kaustubh/Documents/GitHub/melotts-anki-kr`
- You want **Anki’s dev build from this repo** + **local MeloTTS** + **Korean TTS add-on** all working together, preferably offline.

If your paths or username differ, adjust the absolute paths accordingly.

---

## Repository layout used here

At `/home/kaustubh/Documents/GitHub/melotts-anki-kr`:

- `anki/` – Anki desktop source (Rust + Python + Qt).
- `MeloTTS/` – Local MeloTTS source tree (trimmed to focus on Korean).
- `MeloTTS-Korean/` – Local Korean model:
  - `checkpoint.pth`
  - `config.json`
- `anki_addon_korean_tts/` – Source for the Korean TTS add-on.
- `tools/test_korean_tts_in_anki_env.py` – Smoketest helper for the add-on.
- `MINIMAL_OFFLINE_SETUP.md` and `OFFLINE_SETUP_GUIDE.md` – Additional notes on offline model/BERT caching.

---

## 1. Build Anki dev build from this repo

### 1.1 Prerequisites (follow upstream docs)

Before touching MeloTTS, follow Anki’s own docs under `docs/`:

- `docs/linux.md`
- `docs/development.md`
- `docs/build.md`

In short (high-level):

- Install a recent Rust toolchain (cargo, rustc) – `rustup` recommended.
- Install Python 3.10+ and basic build tools (gcc/clang, etc.).
- Ensure `node`, `npm`/`yarn`, and `ninja` are available as per the upstream docs.

### 1.2 First build / dev run

From the repo root:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr/anki
./run
```

This will:

- Build the Rust components (release + dev profiles).
- Create a Python virtualenv under `anki/out/pyenv/`.
- Generate Ninja files and other build artifacts under `anki/out/`.
- Launch the Anki dev build once the build completes.

#### 1.2.1 ftl submodule issues (what we had to fix)

On the first run, the build failed with errors like:

- `Failed to clone 'ftl/core-repo'. destination path .../anki/ftl/core-repo already exists and is not an empty directory.`
- `Failed to clone 'ftl/qt-repo'. destination path .../anki/ftl/qt-repo already exists and is not an empty directory.`

There were leftover `ftl/core-repo` and `ftl/qt-repo` directories from a previous attempt that conflicted with the git submodule checkout.

**Fix applied:**

From the `anki/` directory:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr/anki
mv ftl/core-repo ftl/core-repo.bak
mv ftl/qt-repo   ftl/qt-repo.bak
./run
```

This allowed `git submodule update` to recreate clean `ftl/core-repo` and `ftl/qt-repo` directories.

#### 1.2.2 Missing Esperanto FTL file (eo/errors.ftl)

After the submodules were recreated, Ninja complained:

- `n2: error: out/build.ninja:134: input ftl/core-repo/core/eo/errors.ftl missing`

The freshly cloned `ftl/core-repo/core/eo` directory was missing `errors.ftl` (and in the backup we also had `help.ftl`).

**Fix applied:**

Copy the missing files from the backup:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr/anki
cp ftl/core-repo.bak/core/eo/errors.ftl ftl/core-repo/core/eo/errors.ftl
cp ftl/core-repo.bak/core/eo/help.ftl   ftl/core-repo/core/eo/help.ftl  # optional but matched backup
./run
```

After this, the Anki build completed successfully and the dev app launched.

Once this one-time cleanup is done, subsequent `./run` invocations should build quickly with `n2: no work to do`.

---

## 2. Install and register the Korean TTS add-on

### 2.1 Place the add-on in Anki’s profile

Anki add-ons live in:

```text
/home/kaustubh/.local/share/Anki2/addons21/
```

For this project, we copied `anki_addon_korean_tts/` from the repo into the add-ons directory and named it `korean_tts`:

```bash
cd /home/kaustubh/.local/share/Anki2/addons21
cp -r /home/kaustubh/Documents/GitHub/melotts-anki-kr/anki_addon_korean_tts ./korean_tts
```

Resulting layout:

```text
/home/kaustubh/.local/share/Anki2/addons21/korean_tts/
  __init__.py
  manifest.json
  INSTALLATION.md
  README.md
  ...
```

The bundled `INSTALLATION.md` in that directory documents the generic installation steps; the remaining sections here are about the **local MeloTTS integration** and the exact environment we wired up.

---

## 3. Point the add-on at the local MeloTTS checkout

The add-on used to be hardcoded for a different project path (`/home/kaustubh/Documents/GitHub/melotts-all/...`). That caused:

- `_melotts_path.exists()` to be `False`,
- `from melo.api import TTS` to fail,
- `MELOTTS_AVAILABLE = False`,
- and consequently the warning:

> Korean TTS add-on could not import the local MeloTTS library.

To fix this, we edited the **installed** add-on at:

```text
/home/kaustubh/.local/share/Anki2/addons21/korean_tts/__init__.py
```

and updated the paths:

```python
from pathlib import Path

# Add MeloTTS to path if available
# Use the local MeloTTS directory in the current melotts-anki-kr project
_melotts_path = Path("/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS")
if _melotts_path.exists():
    # Add MeloTTS directory to path so we can import melo
    sys.path.insert(0, str(_melotts_path))
```

and in `get_tts_model()`:

```python
        try:
            # Try to use offline model first
            korean_model_dir = Path("/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS-Korean")
            ...
```

So the add-on now:

- imports `melo` from the **local** `MeloTTS` checkout,
- prefers the **offline** model in `MeloTTS-Korean/` if present (`config.json` + `checkpoint.pth`),
- falls back to the online HuggingFace model if the offline files are missing.

After this change and a full Anki restart, the initial warning disappeared and we saw:

> Korean TTS add-on loaded successfully!

---

## 4. Install MeloTTS dependencies into Anki’s Python environment

The Korean TTS add-on runs inside Anki’s **own** Python virtualenv, not your system Python.

That environment lives at:

```text
/home/kaustubh/Documents/GitHub/melotts-anki-kr/anki/out/pyenv/
```

The Python executable is:

```text
/home/kaustubh/Documents/GitHub/melotts-anki-kr/anki/out/pyenv/bin/python
```

### 4.1 Upgrade pip (inside Anki’s env)

From the repo root:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr
anki/out/pyenv/bin/python -m pip install --upgrade pip
```

### 4.2 Work around setuptools/distutils + uv interaction

We hit an assertion error originating from `uv`’s Python when building wheels:

- `AssertionError: .../distutils/core.py`

The fix was to force setuptools to use the stdlib `distutils` when invoking `pip install` inside Anki’s env:

```bash
SETUPTOOLS_USE_DISTUTILS=stdlib \
  anki/out/pyenv/bin/python -m pip install <packages...>
```

All subsequent `pip install` commands into this env were run with `SETUPTOOLS_USE_DISTUTILS=stdlib`.

### 4.3 Free disk/quota before heavy installs

When installing large packages (torch, torchaudio, etc.), we hit:

- `OSError: [Errno 122] Disk quota exceeded`

Mitigation:

```bash
rm -rf /home/kaustubh/.cache/pip
rm -rf /home/kaustubh/.cache/huggingface
```

Then rerun the installs with `--no-cache-dir` where sensible.

### 4.4 Install CPU-only PyTorch into Anki’s env

We chose a **CPU-only** PyTorch build to avoid huge CUDA dependencies:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr

SETUPTOOLS_USE_DISTUTILS=stdlib \
  anki/out/pyenv/bin/python -m pip install \
  'torch==2.3.1' --index-url https://download.pytorch.org/whl/cpu
```

This provided `torch` plus a few accompanying pure-Python deps (`sympy`, `networkx`, `fsspec`, `filelock`) in Anki’s venv.

### 4.5 Install core MeloTTS runtime deps (audio + I/O)

From `MeloTTS/requirements.txt`, we installed the **core audio/runtime subset** into Anki’s env:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr

SETUPTOOLS_USE_DISTUTILS=stdlib \
  anki/out/pyenv/bin/python -m pip install \
  librosa soundfile tqdm cached_path --no-cache-dir
```

This pulled in:

- `librosa` and its deps (`numba`, `llvmlite`, `scipy`, `scikit-learn`, etc.).
- `soundfile` for WAV I/O.
- `tqdm` for progress bars.
- `cached_path` + `huggingface_hub` and cloud clients (for model downloads if you use HF).

We **did not** install `torchaudio` because its CUDA stack was huge and unnecessary for basic Korean TTS.

### 4.6 Install lightweight Korean text frontend deps

The Korean text frontend (`MeloTTS/melo/text/korean.py`) imports:

- `num2words`
- `anyascii`
- `jamo`

These were not installed by default in Anki’s env. When missing, this caused:

- `ModuleNotFoundError: No module named 'num2words'`

inside the add-on’s batch generation loop, which then silently counted errors.

Fix:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr

SETUPTOOLS_USE_DISTUTILS=stdlib \
  anki/out/pyenv/bin/python -m pip install \
  num2words anyascii jamo --no-cache-dir
```

At this point, all imports required by `melo.api.TTS` for Korean synthesis succeed inside Anki’s Python environment.

---

## 5. Verifying MeloTTS in Anki’s Python environment

To be sure Anki’s env can load MeloTTS and the local Korean model, we ran:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr

anki/out/pyenv/bin/python - << 'PY'
import sys
from pathlib import Path

sys.path.insert(0, '/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS')
from melo.api import TTS

korean_model_dir = Path('/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS-Korean')
config_path = korean_model_dir / 'config.json'
ckpt_path   = korean_model_dir / 'checkpoint.pth'

print('Config exists:', config_path.exists(), 'Ckpt exists:', ckpt_path.exists())

tts = TTS(
    language='KR',
    device='cpu',
    config_path=str(config_path),
    ckpt_path=str(ckpt_path),
    use_hf=False,
)
print('TTS model initialized')

speaker_ids = tts.hps.data.spk2id
spk_id = list(speaker_ids.values())[0]
print('Using speaker id:', spk_id)

tts.tts_to_file('안녕하세요', spk_id, 'test_korean_tts.wav', quiet=True)
print('tts_to_file finished successfully')
PY
```

We confirmed:

- The import worked: `from melo.api import TTS`.
- The offline model files existed and loaded correctly.
- `tts_to_file(...)` successfully produced `test_korean_tts.wav` in the repo root.

If this succeeds, the same code path the add-on uses for batch generation is sound.

---

## 6. Using the Korean TTS add-on inside Anki

With everything above in place, the flow inside Anki is:

1. Start the dev build:

   ```bash
   cd /home/kaustubh/Documents/GitHub/melotts-anki-kr/anki
   ./run
   ```

2. Confirm the add-on loads:
   - On startup, you should **not** see the “could not import the local MeloTTS library” warning.
   - A tooltip appears:  
     **“Korean TTS add-on loaded successfully!”**

3. For **batch generation**:
   - Use **Tools → Generate Korean TTS for All Cards** (or the “current deck”/“selected notes” variants if you’re using the extended version).
   - The add-on:
     - Finds notes with Korean text (via `extract_korean_text()` + `contains_korean()`).
     - Skips notes that already have `[sound:...]` references.
     - Uses `model.tts_to_file(...)` to synthesize audio to a temporary WAV.
     - Adds the file to Anki’s media manager and appends a `[sound:...]` tag.

4. For **playback during review**:
   - Review a card with Korean text that has generated audio.
   - A **🔊 Play Korean** button is injected into the card HTML.
   - Clicking it calls `pycmd('play_korean_tts')`, which plays the associated file via `aqt.sound.av_player`.

---

## 7. Troubleshooting summary (what broke and how it was fixed)

This section is a condensed list of issues actually encountered and the fixes applied.

### 7.1 `ftl/core-repo` and `ftl/qt-repo` already exist

**Symptom:**

- `Failed to clone 'ftl/core-repo'. destination path ... already exists and is not an empty directory.`
- `Failed to clone 'ftl/qt-repo'. destination path ... already exists and is not an empty directory.`

**Fix:**

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr/anki
mv ftl/core-repo ftl/core-repo.bak
mv ftl/qt-repo   ftl/qt-repo.bak
./run
```

### 7.2 Missing `ftl/core-repo/core/eo/errors.ftl`

**Symptom:**

- `n2: error: out/build.ninja:134: input ftl/core-repo/core/eo/errors.ftl missing`

**Fix:**

Copy from the backup copy:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr/anki
cp ftl/core-repo.bak/core/eo/errors.ftl ftl/core-repo/core/eo/errors.ftl
cp ftl/core-repo.bak/core/eo/help.ftl   ftl/core-repo/core/eo/help.ftl
./run
```

### 7.3 `Korean TTS add-on could not import the local MeloTTS library`

**Symptom:**

On Anki startup, the add-on shows:

> Korean TTS add-on could not import the local MeloTTS library.  
> It is configured to use the MeloTTS directory in this project,  
> not a pip-installed package.  
> Please ensure that Anki's Python environment has all MeloTTS  
> dependencies installed...

**Root causes:**

1. The installed add-on in `addons21/korean_tts/__init__.py` originally pointed at:
   - `/home/kaustubh/Documents/GitHub/melotts-all/MeloTTS`
   - `/home/kaustubh/Documents/GitHub/melotts-all/MeloTTS-Korean`

   Those paths did **not** exist, so no `melo` import was possible.

2. Anki’s Python env initially lacked `torch`, `librosa`, and other MeloTTS deps.

**Fixes:**

- Update `_melotts_path` and `korean_model_dir` to:

  ```python
  Path("/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS")
  Path("/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS-Korean")
  ```

- Install the dependencies into `anki/out/pyenv/` as described in sections 4.4–4.6.

After this, `MELOTTS_AVAILABLE` becomes `True` and the warning disappears.

### 7.4 `ModuleNotFoundError: No module named 'torch'` / `'librosa'` / `'num2words'`

**Symptom (from manual tests in Anki’s env):**

- `ModuleNotFoundError: No module named 'torch'`
- `ModuleNotFoundError: No module named 'librosa'`
- `ModuleNotFoundError: No module named 'num2words'`

These surfaced when running:

```python
sys.path.insert(0, '/home/kaustubh/Documents/GitHub/melotts-anki-kr/MeloTTS')
from melo.api import TTS
```

**Fix:**

Install missing packages into Anki’s env (see sections 4.4–4.6).

### 7.5 `Errors: N` in batch generation with no visible messages

**Symptom:**

After batch generation:

```text
Batch generation complete!

Processed: 3 notes
Generated: 0 audio files
Errors: 240
```

but with **no error dialogs or console output**.

**Reason:**

The batch loop in `addons21/korean_tts/__init__.py` does:

```python
            except Exception:
                # Count the error but avoid printing...
                errors += 1
```

So all exceptions are swallowed and only contribute to the `Errors` count.

In our case, the underlying exception was `ModuleNotFoundError: num2words`. Once we installed `num2words`, `anyascii`, and `jamo` into Anki’s env, the batch run succeeded and started generating audio files.

**Optional debugging tip:**

For deeper debugging, you can temporarily change that block to:

```python
            except Exception as e:
                errors += 1
                showWarning(f"Error processing note {note_id}: {e}")
```

so you see the actual Python exceptions while iterating.

### 7.6 `Disk quota exceeded` while installing packages

**Symptom:**

During `pip install` in Anki’s env:

```text
OSError: [Errno 122] Disk quota exceeded
```

**Fix:**

Clear large caches and rerun installs with `--no-cache-dir`:

```bash
rm -rf /home/kaustubh/.cache/pip
rm -rf /home/kaustubh/.cache/huggingface
```

---

## 8. Smoketest script for the Korean TTS add-on

The repo includes a helper to verify that the add-on is importable from Anki’s environment:

- `tools/test_korean_tts_in_anki_env.py`

Run it with Anki’s Python:

```bash
cd /home/kaustubh/Documents/GitHub/melotts-anki-kr
anki/out/pyenv/bin/python tools/test_korean_tts_in_anki_env.py
```

It:

- Adds Anki’s `pylib` to `sys.path`.
- Ensures `/home/kaustubh/.local/share/Anki2/addons21` is on `sys.path`.
- Tries to `import korean_tts` and call the smoketest function if present.

Exit codes:

- `0` – smoketest succeeded.
- `1` – import or smoketest failure (see printed message).

---

## 9. Summary

- Anki dev build is compiled and run from `anki/` using `./run`, with initial ftl submodule hiccups fixed by renaming old submodule dirs and copying missing FTL files.
- The Korean TTS add-on is installed as `korean_tts` in the Anki profile and wired to the local `MeloTTS` and `MeloTTS-Korean` directories inside this repository.
- Anki’s internal Python environment (`anki/out/pyenv/`) has been provisioned with all necessary MeloTTS dependencies, including `torch` (CPU build), `librosa`, `soundfile`, `tqdm`, `cached_path`, `num2words`, `anyascii`, and `jamo`.
- End-to-end synthesis (both via a direct Python test and via Anki’s batch generation UI) now works “beautifully”, with offline Korean TTS driven entirely from this project’s local files. 


