from __future__ import annotations

"""
Server-side CLI for remote Korean TTS.

This script is intended to run on the *server* machine
(`kaustubh@tts-server.your-tailnet.ts.net`) that hosts the MeloTTS
Korean model. It complements the existing HTTP server (`melo.server`) that
the Anki Korean TTS add-on talks to as a *client*.

The Anki add-on (“Generate Korean TTS for Current Deck (Server)”) is the
client: it sends Korean text to the HTTP API on this machine and stores audio
back into Anki's media folder. This CLI stays on the server side and offers:

- `--tts "TEXT" --output OUTPUT_DIR`:
      Synthesize a single sentence into a WAV file under OUTPUT_DIR on the
      server. This is mainly for debugging/benchmarking the core TTS model.

- `--tts-batch INPUT_FILE --output OUTPUT_DIR`:
      Synthesize each non-empty line from INPUT_FILE into OUTPUT_DIR as
      separate WAV files on the server.

- `--run-test-cycle`:
      Server-centric health check that:
        * verifies the Git working tree is clean and pushes to origin,
        * (optionally) runs a lightweight HTTP health check against
          `melo.server`,
        * (optionally) SSHes into the client machine
          (`user@client-host.your-tailnet.ts.net`) to run
          `tools/test_korean_tts_in_anki_env.py` inside Anki's Python
          environment, confirming the add-on and MeloTTS can run.

- `--restart-self`:
      Re-exec the current Python process in place.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List


REPO_ROOT = Path("/home/kaustubh/Documents/GitHub/melotts-anki-kr").resolve()

# Ensure the local MeloTTS source tree is importable as `melo`, mirroring the
# logic used by the Anki korean_tts add-on.
_melotts_path = REPO_ROOT / "MeloTTS"
if _melotts_path.exists():
    sys.path.insert(0, str(_melotts_path))

from melo.simple_korean_tts import synthesize_korean_tts  # type: ignore[import]

# Optional client machine (where Anki runs the korean_tts add-on)
CLIENT_SSH = "user@client-host.your-tailnet.ts.net"
CLIENT_REPO_ROOT = "/home/kaustubh/Documents/GitHub/melotts-anki-kr"

# Per-sentence synthesis timeout in seconds (local, on server)
TTS_TIMEOUT = 10.0

# HTTP health endpoint for the FastAPI server (melo.server).
HEALTH_URL = os.environ.get(
    "MELOTTS_HEALTH_URL",
    "http://127.0.0.1:8000/health",
)


def _run_subprocess(
    args: List[str],
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess and raise on non-zero exit."""

    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout}s: {args}") from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {proc.returncode}: {args}\n"
            f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
        )

    return proc


def _synthesize_with_timeout(text: str, local_path: Path) -> None:
    """Synthesize `text` to `local_path` with a hard timeout."""

    def _worker() -> None:
        synthesize_korean_tts(text, str(local_path), device="auto")

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_worker)
        try:
            fut.result(timeout=TTS_TIMEOUT)
        except concurrent.futures.TimeoutError as exc:
            raise RuntimeError(
                f"TTS synthesis exceeded {TTS_TIMEOUT} seconds for text={text!r}"
            ) from exc


def cmd_tts_single(text: str, output_dir: str) -> int:
    text = text.strip()
    if not text:
        print("ERROR: --tts requires non-empty TEXT", file=sys.stderr)
        return 1

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use a deterministic filename based on a timestamp to keep things simple.
    ts = int(time.time() * 1000)
    local_path = out_dir / f"tts_{ts}.wav"

    start = time.monotonic()
    try:
        _synthesize_with_timeout(text, local_path)
    except Exception as exc:  # noqa: BLE001
        print(f"TTS synthesis failed: {exc}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - start

    if not local_path.exists() or local_path.stat().st_size == 0:
        print("ERROR: TTS output file missing or empty", file=sys.stderr)
        return 1

    print(f"TTS OK ({elapsed:.2f}s). Wrote {local_path}")
    return 0


def cmd_tts_batch(input_file: str, output_dir: str) -> int:
    path = Path(input_file)
    if not path.exists():
        print(f"Input file not found: {path}", file=sys.stderr)
        return 1

    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    sentences = [ln for ln in lines if ln]
    if not sentences:
        print(f"No sentences found in {path}", file=sys.stderr)
        return 1

    for idx, text in enumerate(sentences, start=1):
        print(f"[batch] Sentence {idx}/{len(sentences)}", flush=True)
        rc = cmd_tts_single(text, output_dir)
        if rc != 0:
            print(f"[batch] Stopping at sentence {idx} due to error.", file=sys.stderr)
            return rc

    return 0


def _run_git_push() -> None:
    """Ensure local repo is clean and push to origin."""

    status = _run_subprocess(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        timeout=10.0,
    )
    if status.stdout.strip():
        raise RuntimeError(
            "Git working tree is not clean; please commit or stash changes before "
            "running --run-test-cycle."
        )

    _run_subprocess(
        ["git", "-C", str(REPO_ROOT), "push"],
        timeout=60.0,
    )


def _run_client_smoketest() -> None:
    """Optionally run the add-on smoketest on the client via SSH.

    This uses the existing helper:

        anki/out/pyenv/bin/python tools/test_korean_tts_in_anki_env.py

    on the client machine, which verifies that the korean_tts add-on can import
    MeloTTS and synthesize a short sample sentence.
    """

    remote_cmd = (
        f"cd {CLIENT_REPO_ROOT} && "
        "anki/out/pyenv/bin/python tools/test_korean_tts_in_anki_env.py"
    )

    _run_subprocess(
        ["ssh", CLIENT_SSH, remote_cmd],
        timeout=300.0,
    )


def cmd_run_test_cycle() -> int:
    """Run a server-centric health check for the remote TTS pipeline.

    This primarily validates that:
    - the server repo can push cleanly, and
    - the Anki-side korean_tts add-on (client) can run its smoketest in Anki's
      Python environment on the client machine.
    """

    print("Running remote Korean TTS server/client health check...", flush=True)
    try:
        _run_git_push()
        print("Git push OK.")

        # Check that the HTTP TTS service itself is healthy.
        try:
            req = urllib.request.Request(HEALTH_URL, method="GET")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise RuntimeError(
                        f"Health endpoint {HEALTH_URL!r} returned HTTP {status}"
                    )
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"HTTP health check failed: {e}") from e

        print(f"HTTP health check OK at {HEALTH_URL}")

        # Optionally validate that the Anki-side client (korean_tts add-on) can
        # run its smoketest in Anki's Python environment on the client.
        _run_client_smoketest()
        print("Client Anki smoketest OK.")
    except Exception as exc:  # noqa: BLE001
        print(f"Test cycle FAILED: {exc}", file=sys.stderr)
        return 1

    print("Test cycle succeeded.")
    return 0


def cmd_restart_self() -> int:
    """Re-exec this script in place."""

    print("Restarting server_main.py process...", flush=True)
    os.execv(sys.executable, [sys.executable, "server_main.py"] + sys.argv[1:])
    return 0  # Unreachable


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote Korean TTS server CLI")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--tts", metavar="TEXT", help="Synthesize a single sentence.")
    grp.add_argument(
        "--tts-batch",
        metavar="INPUT_FILE",
        help="Batch synthesis from a text file (one sentence per line).",
    )
    grp.add_argument(
        "--run-test-cycle",
        action="store_true",
        help="Run full server→client→server test cycle.",
    )
    grp.add_argument(
        "--restart-self",
        action="store_true",
        help="Restart server_main.py process in-place.",
    )

    parser.add_argument(
        "--output",
        metavar="OUTPUT_DIR",
        help="Client output directory for generated audio (required for --tts/--tts-batch).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    ns = parser.parse_args(argv)

    if ns.tts is not None:
        if not ns.output:
            parser.error("--output is required when using --tts")
        return cmd_tts_single(ns.tts, ns.output)
    if ns.tts_batch is not None:
        if not ns.output:
            parser.error("--output is required when using --tts-batch")
        return cmd_tts_batch(ns.tts_batch, ns.output)
    if ns.run_test_cycle:
        return cmd_run_test_cycle()
    if ns.restart_self:
        return cmd_restart_self()

    parser.error("No mode selected.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


