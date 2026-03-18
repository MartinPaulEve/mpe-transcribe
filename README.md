# mpe-transcribe

Local voice transcription with a global hotkey. Press the hotkey to start recording, press it again to stop. The audio is transcribed on-device and the resulting text is pasted into the active application.

Supports **Linux** (X11/Wayland with NVIDIA Parakeet) and **macOS** (Apple Silicon with mlx-whisper).

---

## Linux

### System requirements

#### Hardware

- **GPU:** NVIDIA GPU with CUDA support and at least 2 GB VRAM (for the default 0.6B model) or 4 GB VRAM (for the 1.1B model). Tested on RTX 5090.
- **Microphone:** Any PulseAudio/PipeWire-compatible input device.
- **RAM:** 8 GB minimum; 16 GB recommended. The Parakeet model and NeMo toolkit are memory-hungry during initial load.

#### Software

- **OS:** Ubuntu 22.04+ (or any Linux distro with systemd)
- **Python:** 3.12+
- **NVIDIA driver:** 525+ with CUDA 11.8+ (PyTorch will pull its own CUDA runtime via pip)
- **uv:** 0.4+ (for dependency management)

#### System packages — X11

X11 is the primary display server target and where all testing has been done. Install these via `apt`:

```bash
sudo apt install libportaudio2 xdotool xclip libnotify-bin
```

| Package | Purpose |
|---|---|
| `libportaudio2` | Audio I/O backend for `sounddevice` |
| `xdotool` | Simulates Ctrl+V paste into the active window |
| `xclip` | Sets/reads the X11 clipboard |
| `libnotify-bin` | Provides `notify-send` for desktop notifications |

#### System packages — Wayland (experimental)

Wayland support is experimental and has not been tested in production. If you are running a Wayland session (e.g. Ubuntu 24.04+ defaults to Wayland on GNOME), the app will auto-detect it and use the Wayland backend. You will need different system packages:

```bash
sudo apt install libportaudio2 wl-clipboard ydotool libnotify-bin
```

| Package | Purpose |
|---|---|
| `libportaudio2` | Audio I/O backend for `sounddevice` |
| `wl-clipboard` | Provides `wl-copy`/`wl-paste` for Wayland clipboard access |
| `ydotool` | Simulates key release and Ctrl+V paste via the kernel input layer |
| `libnotify-bin` | Provides `notify-send` for desktop notifications |

**Additional Wayland setup:**

1. **`input` group membership** — The Wayland hotkey listener reads keyboard events via evdev, which requires permission to access `/dev/input/` devices. Add your user to the `input` group:

   ```bash
   sudo usermod -aG input $USER
   ```

   Then log out and back in for the group change to take effect.

2. **`ydotoold` daemon** — `ydotool` requires its daemon to be running. Enable and start it:

   ```bash
   sudo systemctl enable ydotoold
   sudo systemctl start ydotoold
   ```

If you run into problems with the Wayland backend, please open an issue. We are actively looking for feedback to stabilise this path.

### Installation (Linux)

Clone the repo and install with the Linux extras:

```bash
git clone <repo-url> transcribe
cd transcribe
uv sync --extra linux
```

The first run will download the Parakeet model (~1.2 GB for the default model) from NVIDIA NGC. Subsequent runs use the cached model.

#### Desktop launcher and systemd service

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

### Usage (Linux)

#### Running directly

```bash
uv run transcribe
```

#### As a service

```bash
systemctl --user start transcribe    # start
systemctl --user stop transcribe     # stop
systemctl --user status transcribe   # check status
journalctl --user -u transcribe -f   # follow logs
```

#### Workflow

1. Press **Ctrl+Shift+;** (default hotkey) — a notification and ding confirm recording has started.
2. Speak.
3. Press **Ctrl+Shift+;** again — recording stops, a second notification appears while transcription runs.
4. The transcribed text is pasted into the currently focused application. Your previous clipboard contents are preserved.

Press **Ctrl+C** to quit (when running directly).

### Available models (Linux)

| Model | Size | Speed | Accuracy | VRAM |
|---|---|---|---|---|
| `nvidia/parakeet-tdt-0.6b-v3` | 0.6B params | Fast | Good | ~2 GB |
| `nvidia/parakeet-rnnt-1.1b` | 1.1B params | Slower | Higher | ~4 GB |

Both are English-only models. The default (0.6B) is recommended for interactive use since transcription latency matters.

### Troubleshooting (Linux)

**"PortAudio library not found"** — Install `libportaudio2`:
```bash
sudo apt install libportaudio2
```

**Hotkey not working (X11)** — Check you are running X11:
```bash
echo $XDG_SESSION_TYPE   # should print "x11"
```
If another application has already grabbed the same key combination, `XGrabKey` will silently fail. Try a different hotkey in `pyproject.toml`.

**Hotkey not working (Wayland)** — Ensure your user is in the `input` group:
```bash
groups   # should include "input"
```
If not, add yourself (`sudo usermod -aG input $USER`) and log out/in. Also check that `ydotoold` is running:
```bash
systemctl status ydotoold
```

**Model download hangs** — The first run downloads ~1.2 GB from NVIDIA NGC. Check your internet connection and firewall rules. The model is cached in `~/.cache/torch/NeMo/` after the first download.

**Service won't start** — Check logs:
```bash
journalctl --user -u transcribe -e
```
Common causes: missing `DISPLAY` environment variable (the service sets `DISPLAY=:0` by default), or missing system packages.

---

## macOS (Apple Silicon)

### System requirements

#### Hardware

- **Mac:** Apple Silicon (M1, M2, M3, M4 or later). Intel Macs are not supported.
- **RAM:** 8 GB minimum. The default whisper-large-v3-turbo model uses ~1.4 GB.
- **Microphone:** Built-in or any CoreAudio-compatible input device.

#### Software

- **OS:** macOS 13 (Ventura) or later
- **Python:** 3.12+
- **uv:** 0.4+ (for dependency management)

No additional system packages are needed — `pbcopy`, `pbpaste`, and `osascript` are built into macOS.

### Installation (macOS)

Clone the repo and install with the macOS extras:

```bash
git clone <repo-url> transcribe
cd transcribe
uv sync --extra macos
```

The first run will download the Whisper model (~1.4 GB for the default model) from Hugging Face. Subsequent runs use the cached model.

#### Accessibility permissions

The global hotkey listener and paste simulation require accessibility permissions. Go to:

**System Settings → Privacy & Security → Accessibility**

Add your terminal app (Terminal.app, iTerm2, Warp, etc.) to the list.

#### launchd service (auto-start on login)

```bash
./scripts/install_macos.sh
```

To start now: `launchctl start com.mpe.transcribe`

To uninstall:

```bash
./scripts/uninstall_macos.sh
```

### Usage (macOS)

#### Running directly

```bash
uv run transcribe
```

#### Workflow

1. Press **Cmd+Shift+;** (default hotkey) — a notification and ding confirm recording has started.
2. Speak.
3. Press **Cmd+Shift+;** again — recording stops, transcription runs.
4. The transcribed text is pasted into the currently focused application. Your previous clipboard contents are preserved.

Press **Ctrl+C** to quit (when running directly).

### Available models (macOS)

All models run locally via Apple's MLX framework with Metal GPU acceleration.

| Model | Download | Speed | Accuracy |
|---|---|---|---|
| `mlx-community/whisper-large-v3-turbo` | ~1.4 GB | Fast | Best (default) |
| `mlx-community/whisper-small` | ~488 MB | Faster | Good |
| `mlx-community/whisper-base` | ~142 MB | Fastest | Lower |

All models support multiple languages. The default (large-v3-turbo) is recommended for the best accuracy/speed tradeoff on Apple Silicon.

### Troubleshooting (macOS)

**Hotkey not working** — Ensure your terminal app has accessibility permissions (System Settings → Privacy & Security → Accessibility).

**Model download hangs** — The first run downloads from Hugging Face. Check your internet connection. Models are cached in `~/.cache/huggingface/`.

**Logs** — When running as a launchd service:
```bash
cat /tmp/transcribe.stdout.log
cat /tmp/transcribe.stderr.log
```

---

## Configuration

Edit the `[tool.transcribe]` section in `pyproject.toml`:

```toml
[tool.transcribe]
# Uncomment to override the platform default:
# model = "nvidia/parakeet-tdt-0.6b-v3"      # Linux
# model = "mlx-community/whisper-large-v3-turbo"  # macOS

# hotkey = "ctrl+shift+;"     # Linux default
# hotkey = "super+shift+;"    # macOS default (Cmd+Shift+;)
```

The app automatically selects the appropriate model and hotkey for your platform. Override in `pyproject.toml` only if you want a non-default choice.

### Hotkey format

The hotkey string uses `+`-separated modifier and key names:

- **Modifiers:** `ctrl`, `shift`, `alt`, `super` (super = Cmd on macOS)
- **Key:** any single character (`;`, `a`, `/`, etc.)

Examples:

```toml
hotkey = "ctrl+shift+;"       # Linux default
hotkey = "super+shift+;"      # macOS default (Cmd+Shift+;)
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

All external dependencies (sounddevice, Xlib, evdev, NeMo, pynput, mlx-whisper, xclip, xdotool) are mocked in the test suite, so tests run on any machine without GPU, X11, Wayland, macOS, or audio hardware.

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

The app is a state machine with auto-detected platform backends:

```
IDLE ──[hotkey]──> RECORDING ──[hotkey]──> TRANSCRIBING ──[done]──> IDLE
                                                │
                                           [error]──> IDLE
```

| Module | Responsibility |
|---|---|
| `app.py` | State machine orchestrator |
| `session.py` | Detects macOS vs X11 vs Wayland session |
| `factory.py` | Creates the correct backend for the session (hotkey, clipboard, transcriber, notifier) |
| `config.py` | Reads `[tool.transcribe]` from pyproject.toml, platform-aware defaults |
| `recorder.py` | 16 kHz mono audio capture via PortAudio |
| `transcriber.py` | Linux: NeMo Parakeet model inference |
| `macos_transcriber.py` | macOS: mlx-whisper model inference |
| `hotkey.py` | X11: global hotkey via `XGrabKey` |
| `wayland_hotkey.py` | Wayland: global hotkey via evdev (experimental) |
| `macos_hotkey.py` | macOS: global hotkey via pynput (Quartz event taps) |
| `notifier.py` | Linux: desktop notifications via `notify-send` + audible ding |
| `macos_notifier.py` | macOS: desktop notifications via `osascript` + audible ding |
| `clipboard.py` | X11: clipboard save/set/paste/restore via xclip + xdotool |
| `wayland_clipboard.py` | Wayland: clipboard via wl-clipboard + ydotool (experimental) |
| `macos_clipboard.py` | macOS: clipboard via pbcopy/pbpaste + osascript |

## Notes

This application was coded with the aid of LLMs.
