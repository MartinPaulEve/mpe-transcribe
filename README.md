# mpe-transcribe

Global-hotkey voice dictation that pastes into any application. Press the hotkey, speak, press it again — the audio is transcribed on-device and the text is pasted into whatever window you were typing in, with your previous clipboard contents restored afterwards. Everything runs locally by default; a networked mode lets one machine transcribe for others when you want it.

Supports **Linux** (X11/Wayland, NVIDIA Parakeet on CUDA), **macOS** (Apple Silicon, mlx-whisper on Metal), and **Windows** (NVIDIA Parakeet on CUDA).

---

## Quick start (standalone)

1. **Install for your platform.** Each guide covers system packages, model requirements, and an optional autostart service:

   - **[Linux](docs/LINUX.md)** — X11/Wayland, NVIDIA GPU, systemd user service
   - **[macOS](docs/MAC.md)** — Apple Silicon, launchd service
   - **[Windows](docs/WINDOWS.md)** — NVIDIA GPU, manual launch

2. **Run it:**

   ```bash
   uv run transcribe
   ```

   The first run downloads the model for your platform; subsequent runs use the cache.

3. **Dictate.** Press the hotkey (**Ctrl+Shift+;** on Linux/Windows, **Cmd+Shift+'** on macOS) — a notification and ding confirm recording has started. Speak. Press the hotkey again — the recording is transcribed and the text appears in the focused application.

---

## Configuration

User configuration lives in `transcribe.toml` in the repo root. It is gitignored, so machine-specific settings (model, hotkey, network role) never end up in version control. Copy the template to get started:

```bash
cp transcribe.toml.example transcribe.toml
```

Every key is optional — an empty `transcribe.toml` (or none at all) runs standalone with platform defaults. (For backwards compatibility only, a `[tool.transcribe]` section in `pyproject.toml` is still read when no `transcribe.toml` exists; new setups should use `transcribe.toml`.)

> **TOML placement gotcha:** top-level keys (`model`, `hotkey`, `paste_method`) must appear **above** the first `[section]` header. In TOML, a key written below a header belongs to that section, so a misplaced `paste_method` under `[custom_terms]` would otherwise be silently ignored — the app instead rejects misplaced or unknown keys at startup with a `ConfigError`, telling you what to fix.

### Top-level keys

| Key | Default | Meaning |
|---|---|---|
| `model` | platform-dependent (see below) | Which speech model to load |
| `hotkey` | `"ctrl+shift+;"` (Linux/Windows), `"super+shift+'"` (macOS) | The global toggle hotkey |
| `paste_method` | `"ctrl+v"` | `"ctrl+v"` pastes via clipboard + a synthetic Ctrl+V; `"type"` (Wayland only) types the text directly via ydotool — no clipboard involved |

### Models

The default model is selected automatically for your platform:

| Platform | Default model | Engine |
|---|---|---|
| Linux | `nvidia/parakeet-tdt-0.6b-v3` | NeMo on NVIDIA CUDA |
| Windows | `nvidia/parakeet-tdt-0.6b-v3` | NeMo on NVIDIA CUDA |
| macOS | `mlx-community/whisper-large-v3-turbo` | mlx-whisper on Apple Silicon (MLX/Metal) |

Alternatives (higher accuracy or smaller footprint) are listed in the platform guides: [Linux](docs/LINUX.md#available-models), [macOS](docs/MAC.md#available-models), [Windows](docs/WINDOWS.md#model-choices).

### Hotkey format

The hotkey string uses `+`-separated modifier and key names:

- **Modifiers:** `ctrl`, `shift`, `alt`, `super` (super = Cmd on macOS, Win key on Windows). At least one modifier is required.
- **Key:** any single character (`;`, `a`, `/`, …) or key name (`space`, `tab`, …).

```toml
hotkey = "ctrl+shift+;"       # Linux / Windows default
hotkey = "super+shift+'"      # macOS default (Cmd+Shift+')
hotkey = "super+shift+;"
```

> **Wayland caveat:** the Wayland hotkey listener is passive — it observes evdev events but cannot consume the chord, so the keystroke also reaches the focused application. A chord that produces a printable character will type it (e.g. `ctrl+shift+;` types `:`). Pick a chord with no character output, such as `super+shift+;`, and avoid `ctrl+\` variants entirely — terminals map those to SIGQUIT. See [docs/LINUX.md](docs/LINUX.md#wayland-specifics).

### Voice recognition corrections

If the transcriber consistently misrecognises certain words or names, define corrections in `transcribe.toml`. Two types are supported, and they can be combined — exact replacements run first, then fuzzy matching.

**Exact replacements** — case-insensitive find-and-replace applied to every transcription. The key is what the transcriber produces; the value is what you meant:

```toml
[replacements]
comet = "commit"
"martin poll eve" = "Martin Paul Eve"
```

**Fuzzy term matching** — for names and phrases that come out in unpredictably wrong ways, similarity scoring catches close misspellings automatically:

```toml
[custom_terms]
terms = ["Martin Paul Eve", "Birkbeck"]
threshold = 0.8   # optional, default 0.8 (0.0–1.0)
```

`threshold` controls how similar a span of text must be to the target term before it is corrected. Lower values are more aggressive (more corrections, more false positives); higher values are stricter.

> **Where corrections run:** corrections are applied on the machine that *transcribes*, immediately after transcription. In standalone mode that is your machine. In [networked mode](docs/NETWORK.md) it is the **host** — the text is corrected before it is sent to clients, so `[replacements]` and `[custom_terms]` must be configured in the *host's* `transcribe.toml`, not the client's.

On macOS, custom terms are additionally passed to Whisper as an `initial_prompt`, which biases the model toward recognising them correctly at transcription time — before post-processing even kicks in.

When a correction is applied, it is logged at INFO level:

```
Corrections applied: 'push the comet to main' -> 'push the commit to main'
```

### Notifications

Two channels — desktop notifications and the audible ding — with master switches per channel and per-event switches on top:

```toml
[notifications]
visual = true    # master switch: desktop notifications
sound = true     # master switch: the ding

[notifications.events]
ready = true       # "Ready" at startup
recording = true   # recording started
stopped = true     # recording stopped / transcribing
pasted = true      # text pasted (or sent, on a network host)
error = true       # mic / transcription errors
```

Everything defaults to on. Setting an event to `false` silences **both** channels for that event; setting a master switch to `false` silences that channel for **every** event.

---

## Networked mode: dictate into machines that can't transcribe

This is the flagship trick. An Apple Silicon Mac runs as **host**: it records from its own microphone and transcribes on the M-series GPU with mlx-whisper. Lightweight **clients** — say, a Linux VM under Parallels *on that very Mac*, which has no usable GPU — press their own hotkey to trigger a dictation and receive the finished text pasted into their focused window.

Because the VM is a guest on the same physical machine, the host's microphone *is* your microphone — no audio ever crosses the network, only control messages and the final text, and every UDP datagram is end-to-end encrypted and authenticated (ChaCha20-Poly1305 with a pre-shared key; both sides refuse to start without one).

Clients need none of the heavy stack — no model, no GPU, no audio libraries:

```bash
uv run transcribe keygen              # generate the shared key (once)
uv sync --extra client-linux          # or client-macos
uv run transcribe --client
```

Mode is set via `[network] mode = "standalone" | "host" | "client"` in `transcribe.toml`, or the `--standalone` / `--host` / `--client` flags; clients also accept `--server-host` and `--server-port`. A client-only service installer is provided (`./scripts/install_client.sh`).

See **[docs/NETWORK.md](docs/NETWORK.md)** for the full guide: architecture, quick start, configuration reference, security model, and troubleshooting.

---

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
| `app.py` | State machine orchestrator; dispatches standalone/host/client modes; `keygen` CLI |
| `session.py` | Detects macOS vs Windows vs X11 vs Wayland session (env vars, with a live-socket fallback) |
| `factory.py` | Creates the correct backend for the session (hotkey, clipboard, transcriber, notifier) |
| `config.py` | Reads and validates `transcribe.toml`, platform-aware defaults, pre-shared key resolution |
| `corrections.py` | Post-transcription text corrections: exact replacements and fuzzy term matching |
| `recorder.py` | 16 kHz mono audio capture via PortAudio |
| `device_check.py` | Preflight check of the default input device before recording |
| `transcriber.py` | Linux: NeMo Parakeet model inference |
| `macos_transcriber.py` | macOS: mlx-whisper model inference |
| `windows_transcriber.py` | Windows: NeMo Parakeet model inference |
| `hotkey.py` | X11: global hotkey via `XGrabKey` |
| `wayland_hotkey.py` | Wayland: global hotkey via evdev (passive listener) |
| `signal_hotkey.py` | macOS (service): hotkey via SIGUSR1 from the native launcher |
| `macos_hotkey.py` | macOS (terminal): global hotkey via pynput (Quartz event taps) |
| `windows_hotkey.py` | Windows: global hotkey via pynput |
| `notifier.py` | Linux: desktop notifications via `notify-send` + audible ding |
| `macos_notifier.py` | macOS: desktop notifications via `osascript` + audible ding |
| `windows_notifier.py` | Windows: toast notifications via PowerShell + audible ding |
| `clipboard.py` | X11: clipboard save/set/paste/restore via xclip + xdotool |
| `clipboard_content.py` | Clipboard data model and MIME-type target selection |
| `wayland_clipboard.py` | Wayland: clipboard via xclip (XWayland) or wl-clipboard, paste via ydotool |
| `macos_clipboard.py` | macOS: clipboard via pbcopy/pbpaste, paste via native launcher (CGEventPost) or osascript |
| `windows_clipboard.py` | Windows: clipboard via Win32 API (ctypes), paste via SendInput |
| `macos_permissions.py` | macOS: checks accessibility and microphone TCC permissions |
| `net/protocol.py` | Networked mode: MPET wire protocol framing, bodies, chunking |
| `net/crypto.py` | Networked mode: ChaCha20-Poly1305 AEAD, HKDF key derivation, replay guard |
| `net/host.py` | Networked mode: UDP host — subscriber registry, session control, reliable TEXT delivery |
| `net/client.py` | Networked mode: UDP client — trigger, register/renew, verify + reassemble + paste |
| `net/transport.py` | Networked mode: the thin UDP socket layer behind a testable seam |
| `scripts/transcribe_launcher.c` | Native Mach-O launcher for Transcribe.app; registers a Carbon global hotkey and sends SIGUSR1 to the Python child, compiled at install time by `install_macos.sh` |

---

## Development

The project uses [uv](https://docs.astral.sh/uv/) for everything. Install all dependencies including the dev group (`pytest`, `pytest-mock`, `ruff`, `pre-commit`):

```bash
uv sync
```

Set up the pre-commit hooks:

```bash
uv run pre-commit install
```

This installs a git hook that runs Ruff linting (with `--fix`) and formatting on every commit; commits are blocked on unfixable lint errors or formatting issues.

### Running tests

```bash
uv run pytest -v
```

All external dependencies (sounddevice, Xlib, evdev, NeMo, pynput, mlx-whisper, xclip, xdotool, UDP sockets) are mocked in the test suite, so tests run on any machine without GPU, X11, Wayland, macOS, or audio hardware.

### Linting and formatting

[Ruff](https://docs.astral.sh/ruff/) with a line length of 79 characters:

```bash
uv run ruff check .          # lint
uv run ruff format --check . # check formatting
uv run ruff format .         # auto-format
```

### CI

`.github/workflows/ci.yml` runs on every push and pull request to `main`:

- **lint** — `ruff check` and `ruff format --check`
- **test** — `pytest -v`

`.github/workflows/version-release.yml` auto-bumps the version and updates the changelog on merges to `main` using [commitizen](https://commitizen-tools.github.io/commitizen/).

## Notes

This application was coded with the aid of LLMs.
