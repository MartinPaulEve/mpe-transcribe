# transcribe

Local voice transcription for Ubuntu/GNOME on X11. Press a global hotkey to start recording, press it again to stop. The audio is transcribed on-device using an Nvidia Parakeet ASR model running on your GPU, and the resulting text is pasted into the active application.

## System requirements

### Hardware

- **GPU:** NVIDIA GPU with CUDA support and at least 2 GB VRAM (for the default 0.6B model) or 4 GB VRAM (for the 1.1B model). Tested on RTX 5090.
- **Microphone:** Any PulseAudio/PipeWire-compatible input device.
- **RAM:** 8 GB minimum; 16 GB recommended. The Parakeet model and NeMo toolkit are memory-hungry during initial load.

### Software

- **OS:** Ubuntu 22.04+ (or any Linux distro with X11 and systemd)
- **Display server:** X11 (Wayland is not supported — XGrabKey and xdotool require X11)
- **Python:** 3.12+
- **NVIDIA driver:** 525+ with CUDA 11.8+ (PyTorch will pull its own CUDA runtime via pip)
- **uv:** 0.4+ (for dependency management)

### System packages

Install these via `apt` before proceeding:

```bash
sudo apt install libportaudio2 xdotool xclip libnotify-bin
```

| Package | Purpose |
|---|---|
| `libportaudio2` | Audio I/O backend for `sounddevice` |
| `xdotool` | Simulates Ctrl+V paste into the active window |
| `xclip` | Sets/reads the X11 clipboard |
| `libnotify-bin` | Provides `notify-send` for desktop notifications |

## Installation

Clone the repo and sync dependencies:

```bash
git clone <repo-url> transcribe
cd transcribe
uv sync
```

The first run will download the Parakeet model (~1.2 GB for the default model) from NVIDIA NGC. Subsequent runs use the cached model.

### Desktop launcher and systemd service

An install script sets up both a desktop launcher icon (visible in the app grid and pinnable to the dock) and a systemd user service that auto-starts with your graphical session:

```bash
./scripts/install.sh
```

After installing, either:
- Log out and back in (the service starts automatically), or
- Start it immediately: `systemctl --user start transcribe`

To uninstall:

```bash
./scripts/uninstall.sh
```

## Usage

### Running directly

```bash
uv run transcribe
```

### As a service

```bash
systemctl --user start transcribe    # start
systemctl --user stop transcribe     # stop
systemctl --user status transcribe   # check status
journalctl --user -u transcribe -f   # follow logs
```

### Workflow

1. Press **Ctrl+Shift+;** (default hotkey) — a notification and ding confirm recording has started.
2. Speak.
3. Press **Ctrl+Shift+;** again — recording stops, a second notification appears while transcription runs.
4. The transcribed text is pasted into the currently focused application. Your previous clipboard contents are preserved.

Press **Ctrl+C** to quit (when running directly).

## Configuration

Edit the `[tool.transcribe]` section in `pyproject.toml`:

```toml
[tool.transcribe]
model = "nvidia/parakeet-tdt-0.6b-v3"
hotkey = "ctrl+shift+;"
```

### Available models

| Model | Size | Speed | Accuracy | VRAM |
|---|---|---|---|---|
| `nvidia/parakeet-tdt-0.6b-v3` | 0.6B params | Fast | Good | ~2 GB |
| `nvidia/parakeet-rnnt-1.1b` | 1.1B params | Slower | Higher | ~4 GB |

Both are English-only models. The default (0.6B) is recommended for interactive use since transcription latency matters.

### Hotkey format

The hotkey string uses `+`-separated modifier and key names:

- **Modifiers:** `ctrl`, `shift`, `alt`, `super`
- **Key:** any single character (`;`, `a`, `/`, etc.)

Examples:

```toml
hotkey = "ctrl+shift+;"       # default
hotkey = "ctrl+alt+t"
hotkey = "super+shift+space"
```

At least one modifier is required.

## Development

Install all dependencies including dev tools:

```bash
uv sync
```

This pulls in the dev dependency group (`pytest`, `pytest-mock`, `ruff`, `pre-commit`).

Set up the pre-commit hooks:

```bash
uv run pre-commit install
```

This installs a git pre-commit hook that automatically runs Ruff linting (with `--fix`) and formatting on every commit. Commits will be blocked if there are unfixable lint errors or formatting issues.

### Running tests

```bash
uv run pytest -v
```

All external dependencies (sounddevice, Xlib, NeMo, xclip, xdotool) are mocked in the test suite, so tests run on any machine without GPU, X11, or audio hardware.

### Linting and formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, configured with a line length of 79 characters.

```bash
uv run ruff check .          # lint
uv run ruff format --check . # check formatting
uv run ruff format .         # auto-format
```

### CI

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and pull request to `main`:

- **lint** — `ruff check` and `ruff format --check`
- **test** — `pytest -v`

A separate workflow (`.github/workflows/version-release.yml`) auto-bumps the version and updates the changelog on merges to `main` using [commitizen](https://commitizen-tools.github.io/commitizen/).

## Architecture

The app is a state machine:

```
IDLE ──[hotkey]──> RECORDING ──[hotkey]──> TRANSCRIBING ──[done]──> IDLE
                                                │
                                           [error]──> IDLE
```

| Module | Responsibility |
|---|---|
| `app.py` | State machine orchestrator |
| `recorder.py` | 16 kHz mono audio capture via PortAudio |
| `transcriber.py` | NeMo Parakeet model inference |
| `hotkey.py` | Global hotkey via X11 `XGrabKey` (suppresses key from reaching apps) |
| `notifier.py` | Desktop notifications + audible ding |
| `clipboard.py` | Clipboard save/set/paste/restore via xclip + xdotool |
| `config.py` | Reads `[tool.transcribe]` from pyproject.toml |

## Troubleshooting

**"PortAudio library not found"** — Install `libportaudio2`:
```bash
sudo apt install libportaudio2
```

**Hotkey not working** — Ensure you are running X11, not Wayland. Check with:
```bash
echo $XDG_SESSION_TYPE   # should print "x11"
```
If another application has already grabbed the same key combination, `XGrabKey` will silently fail. Try a different hotkey in `pyproject.toml`.

**Model download hangs** — The first run downloads ~1.2 GB from NVIDIA NGC. Check your internet connection and firewall rules. The model is cached in `~/.cache/torch/NeMo/` after the first download.

**Service won't start** — Check logs:
```bash
journalctl --user -u transcribe -e
```
Common causes: missing `DISPLAY` environment variable (the service sets `DISPLAY=:0` by default), or missing system packages.

## Notes

This application was coded with the aid of LLMs.