## melotts-anki-kr - Korean TTS for Anki with MeloTTS

This repository provides a production-ready Korean text-to-speech (TTS) setup
integrated with Anki, backed by the [MeloTTS](https://github.com/myshell-ai/MeloTTS)
Korean model, and an optional HTTP server for offloading synthesis to a remote
machine.

If you just want to **install the Anki add-on and start generating Korean TTS**,
this page walks you through:

- Installing and configuring the Anki add-on
- Setting up MeloTTS locally (optional, for offline/local-only mode)
- Running the remote TTS server on your own machine

For more detail, including troubleshooting and deployment notes, see
`PRODUCTION_READY_GUIDE.md`.

---

### 1. Installing the Anki add-on

1. Clone this repo:

```bash
git clone https://github.com/kaukauk/melotts-anki-kr.git
cd melotts-anki-kr
```

2. Copy the add-on into Anki's `addons21` folder:

```bash
cp -r anki_addon_korean_tts ~/.local/share/Anki2/addons21/korean_tts
```

3. Restart Anki.

4. In Anki, go to:
   - **Tools → Korean TTS Settings…**

5. Configure:
   - **Server URL**: `http://your-server:8000` (or `http://127.0.0.1:8000` if you
     run the server locally)
   - **Enable remote TTS**: checked
   - **TTS speed**: use the slider (0.1–2.0x, where 1.0x is normal speed)
   - **Remote batch size**: usually `16` is a good default
   - **Extra MeloTTS path**: leave empty unless you have a non-standard
     installation of MeloTTS

You can now:

- Use **Tools → Generate Korean TTS for Current Deck (Server)** to batch-generate
  audio via the remote server.
- Use **Tools → Generate Korean TTS for Current Deck (Local)** if a local MeloTTS
  model is available.
- Use the reviewer/browser actions to generate TTS per card or selection, using
  an “auto” mode that tries the server first and falls back to local when needed.

To package the add-on as a redistributable `.ankiaddon` file, you can run:

```bash
cd anki_addon_korean_tts
zip -r ../korean_tts.ankiaddon . \
  -x '*.pyc' '*__pycache__*' '.git*' '.DS_Store'
```

You can then share `korean_tts.ankiaddon`, and users can install it via
**Tools → Add-ons → Install from file**.

---

### 2. Setting up MeloTTS locally (optional)

A local MeloTTS installation is **optional**; it is only required if you want
to use the **Local** TTS mode or have the “auto” mode fall back to local
synthesis when the server is not reachable.

1. Ensure you have the MeloTTS repo checked out inside this project:

```bash
cd /path/to/melotts-anki-kr
ls MeloTTS/melo
```

2. Place the Korean model files (if you have them locally) in:

```bash
/path/to/melotts-anki-kr/MeloTTS-Korean
  ├─ config.json
  └─ checkpoint.pth
```

3. In Anki, if MeloTTS lives in a non-standard location, set the
   **“Extra MeloTTS path”** in **Korean TTS Settings…** to point to the folder
   containing the `melo` package (the MeloTTS repo root).

The add-on will:

- Lazy-load MeloTTS only when you invoke a local TTS action.
- Prefer the offline `MeloTTS-Korean` model when present.
- Fall back to downloading from HuggingFace when necessary.

---

### 3. Running the remote TTS server

The TTS server is a small FastAPI app (`melo.server`) that exposes:

- `POST /api/v1/tts/korean` – single-text synthesis
- `POST /api/v1/tts/korean_batch` – batch synthesis with base64-encoded WAVs
- `GET /health` – liveness
- `GET /healthz` – readiness (verifies model load)
- `GET /metrics` – Prometheus metrics (if `prometheus_client` is installed)

#### 3.1. Starting the server manually

From the repo root:

```bash
cd /path/to/melotts-anki-kr
./run_melo_server
```

This will:

- Set up `PYTHONPATH` so that the `melo` package is importable.
- Run `uvicorn melo.server:app --host 0.0.0.0 --port 8000`.

You can then test:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/healthz
```

#### 3.2. systemd service (optional)

For a more “production” setup, you can use the provided `melotts-server.service`:

```bash
sudo cp melotts-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable melotts-server
sudo systemctl start melotts-server
```

This will run `run_melo_server` on boot and restart it automatically on failure.

---

### 4. Configuration and hardcoded values

All deployment-specific values are now driven by configuration:

- **Server side**: `server_config.json` holds things like:
  - `client_ssh`
  - `client_repo_root`
  - `health_url`

- **Client side (Anki add-on)**: configuration is stored in Anki’s add-on
  config system and editable via **Korean TTS Settings…**. The shipped
  `config.json` just provides sensible defaults.

Any hostnames (e.g. your Tailscale hostname) and paths should be customised
through these config files and Anki’s UI, not hard-coded in the Python code.

---

For a deeper, end-to-end walkthrough (including troubleshooting, performance
tuning, and security considerations), see `PRODUCTION_READY_GUIDE.md`.


