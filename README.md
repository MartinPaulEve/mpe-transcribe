# mpe-transcribe

Local voice transcription with a global hotkey. Press the hotkey to start recording, press it again to stop. The audio is transcribed on-device and the resulting text is pasted into the active application.

Supports **Linux** (X11/Wayland with NVIDIA Parakeet), **macOS** (Apple Silicon with mlx-whisper), and **Windows** (NVIDIA Parakeet).

---

## Platform setup

- **[Linux](docs/LINUX.md)** — X11/Wayland, NVIDIA GPU, systemd service
- **[macOS](docs/MAC.md)** — Apple Silicon, launchd service
- **[Windows](docs/WINDOWS.md)** — NVIDIA GPU, manual launch

---

## Configuration

Edit the `[tool.transcribe]` section in `pyproject.toml`:

```toml
[tool.transcribe]
# Uncomment to override the platform default:
# model = "nvidia/parakeet-tdt-0.6b-v3"      # Linux / Windows
# model = "mlx-community/whisper-large-v3-turbo"  # macOS

# hotkey = "ctrl+shift+;"     # Linux / Windows default
# hotkey = "super+shift+'"    # macOS default (Cmd+Shift+')
```

The app automatically selects the appropriate model and hotkey for your platform. Override in `pyproject.toml` only if you want a non-default choice.

### Hotkey format

The hotkey string uses `+`-separated modifier and key names:

- **Modifiers:** `ctrl`, `shift`, `alt`, `super` (super = Cmd on macOS, Win key on Windows)
- **Key:** any single character (`;`, `a`, `/`, etc.)

Examples:

```toml
hotkey = "ctrl+shift+;"       # Linux default
hotkey = "super+shift+'"      # macOS default (Cmd+Shift+')
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
| `__main__.py` | Allows running the package with `python -m transcribe` |
| `app.py` | State machine orchestrator |
| `session.py` | Detects macOS vs Windows vs X11 vs Wayland session |
| `factory.py` | Creates the correct backend for the session (hotkey, clipboard, transcriber, notifier) |
| `config.py` | Reads `[tool.transcribe]` from pyproject.toml, platform-aware defaults |
| `recorder.py` | 16 kHz mono audio capture via PortAudio |
| `transcriber.py` | Linux: NeMo Parakeet model inference |
| `macos_transcriber.py` | macOS: mlx-whisper model inference |
| `hotkey.py` | X11: global hotkey via `XGrabKey` |
| `wayland_hotkey.py` | Wayland: global hotkey via evdev (experimental) |
| `signal_hotkey.py` | macOS (service): hotkey via SIGUSR1 from native launcher |
| `macos_hotkey.py` | macOS (terminal): global hotkey via pynput (Quartz event taps) |
| `notifier.py` | Linux: desktop notifications via `notify-send` + audible ding |
| `macos_notifier.py` | macOS: desktop notifications via `osascript` + audible ding |
| `clipboard.py` | X11: clipboard save/set/paste/restore via xclip + xdotool |
| `clipboard_content.py` | Clipboard data model and MIME-type target selection |
| `wayland_clipboard.py` | Wayland: clipboard via wl-clipboard + ydotool (experimental) |
| `macos_clipboard.py` | macOS: clipboard via pbcopy/pbpaste, paste via native launcher (CGEventPost) or osascript |
| `windows_transcriber.py` | Windows: NeMo Parakeet model inference |
| `windows_hotkey.py` | Windows: global hotkey via pynput |
| `windows_notifier.py` | Windows: toast notifications via PowerShell + audible ding |
| `windows_clipboard.py` | Windows: clipboard via Win32 API (ctypes), paste via SendInput |
| `macos_permissions.py` | macOS: checks accessibility and microphone TCC permissions |
| `scripts/transcribe_launcher.c` | Native Mach-O launcher for Transcribe.app; registers a Carbon global hotkey and sends SIGUSR1 to the Python child process, compiled at install time by `install_macos.sh` |

## Tested on

- **macOS:** Mac M3 Pro (Apple Silicon), macOS 14.2.1 (Sonoma)
- **Linux:** Ubuntu 22.04, X11. Wayland has not been tested.
- **Windows:** Windows 10/11 with NVIDIA GPU and CUDA. Requires manual testing.

## Notes

This application was coded with the aid of LLMs.
