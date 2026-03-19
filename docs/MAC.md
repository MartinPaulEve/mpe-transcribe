# macOS Setup (Apple Silicon)

## System requirements

### Hardware

- **Mac:** Apple Silicon (M1, M2, M3, M4 or later). Intel Macs are not supported.
- **RAM:** 8 GB minimum. The default whisper-large-v3-turbo model uses ~1.4 GB.
- **Microphone:** Built-in or any CoreAudio-compatible input device.

### Software

- **OS:** macOS 13 (Ventura) or later
- **Python:** 3.12+
- **uv:** 0.4+ (for dependency management)

No additional system packages are needed — `pbcopy`, `pbpaste`, and `osascript` are built into macOS.

## Installation

Clone the repo and install with the macOS extras:

```bash
git clone <repo-url> transcribe
cd transcribe
uv sync --extra macos
```

The first run will download the Whisper model (~1.4 GB for the default model) from Hugging Face. Subsequent runs use the cached model.

### Permissions (required)

macOS requires two permissions for transcribe to work. The app checks both at startup and will warn you if either is missing.

#### Accessibility

> **Important:** Without accessibility permissions, the global hotkey will not work and transcribe will be unable to paste text into other applications.

**System Settings → Privacy & Security → Accessibility**

Add the app that runs transcribe to the allowed list:
- If running from a terminal: add your terminal app (Terminal.app, iTerm2, Warp, etc.)
- If running as a launchd service: add the `transcribe` binary itself (navigate to the `.venv/bin/transcribe` path inside the project)

You may need to restart the app after granting permissions.

#### Microphone

> **Important:** Without microphone permissions, the app will record silence and transcription will fail. macOS only shows the permission prompt when running interactively (not from a launchd service).

The install script (`./scripts/install_macos.sh`) handles this automatically — it codesigns the binaries (so macOS can track them in System Settings) and triggers the microphone permission prompt. Click **Allow** when the dialog appears.

If running manually without the install script, run `uv run transcribe` once from the terminal. macOS will show the permission dialog on first use.

If you previously denied the prompt, reset and try again:
```bash
tccutil reset Microphone
```

### launchd service (auto-start on login)

An install script sets up a launchd user agent that auto-starts transcribe when you log in. It also codesigns the binaries and requests microphone permission:

```bash
./scripts/install_macos.sh
```

After installing, either:
- Log out and back in (the service starts automatically), or
- Start it immediately: `launchctl start com.mpe.transcribe`

To uninstall:

```bash
./scripts/uninstall_macos.sh
```

## Usage

### Running directly

```bash
uv run transcribe
```

### As a service

```bash
launchctl start com.mpe.transcribe    # start
launchctl stop com.mpe.transcribe     # stop
launchctl list | grep transcribe      # check status
```

View logs:
```bash
cat /tmp/transcribe.stdout.log        # stdout
cat /tmp/transcribe.stderr.log        # stderr
tail -f /tmp/transcribe.stderr.log    # follow logs
```

### Workflow

1. Press **Cmd+Shift+;** (default hotkey) — a notification and ding confirm recording has started.
2. Speak.
3. Press **Cmd+Shift+;** again — recording stops, transcription runs.
4. The transcribed text is pasted into the currently focused application. Your previous clipboard contents are preserved.

Press **Ctrl+C** to quit (when running directly).

## Available models

All models run locally via Apple's MLX framework with Metal GPU acceleration.

| Model | Download | Speed | Accuracy |
|---|---|---|---|
| `mlx-community/whisper-large-v3-turbo` | ~1.4 GB | Fast | Best (default) |
| `mlx-community/whisper-small` | ~488 MB | Faster | Good |
| `mlx-community/whisper-base` | ~142 MB | Fastest | Lower |

All models support multiple languages. The default (large-v3-turbo) is recommended for the best accuracy/speed tradeoff on Apple Silicon.

## Troubleshooting

**Hotkey not working** — Ensure your terminal app has accessibility permissions (System Settings → Privacy & Security → Accessibility).

**"No audio detected" or transcription returns garbage** — Microphone permissions are missing. Re-run `./scripts/install_macos.sh` which will codesign the binaries and trigger the permission prompt. If you previously denied the prompt, reset first:
```bash
tccutil reset Microphone
./scripts/install_macos.sh
```

**App not appearing in System Settings → Microphone** — macOS cannot track unsigned CLI binaries. The install script codesigns them automatically. If you skipped the install script, codesign manually:
```bash
codesign -s - -f .venv/bin/python3
codesign -s - -f .venv/bin/transcribe
```

**Model download hangs** — The first run downloads from Hugging Face. Check your internet connection. Models are cached in `~/.cache/huggingface/`.

**Service won't start** — Check logs:
```bash
cat /tmp/transcribe.stderr.log
```
Common causes: missing accessibility or microphone permissions, or the `transcribe` binary not found (run `uv sync --extra macos` first).

**Service not loading** — If `launchctl start` reports an error, try reloading:
```bash
launchctl unload ~/Library/LaunchAgents/com.mpe.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.mpe.transcribe.plist
```
