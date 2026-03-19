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
- **Xcode Command Line Tools:** required to compile the native launcher (the install script will tell you if these are missing)

No additional system packages are needed — `pbcopy`, `pbpaste`, and `osascript` are built into macOS.

## Quick start

```bash
git clone <repo-url> transcribe
cd transcribe
uv sync --extra macos
./scripts/install_macos.sh
```

The install script will:
1. Build **Transcribe.app** (a lightweight wrapper in `~/Applications/`)
2. Prompt you for **microphone** permission — click **Allow**
3. Prompt you for **accessibility** permission — follow the dialog
4. Install and start a **launchd service** that auto-runs on login

After installing, grant permissions (see below), then restart the service:

```bash
launchctl stop com.mpe.transcribe && launchctl start com.mpe.transcribe
```

The first run will download the Whisper model (~1.4 GB) from Hugging Face. Subsequent runs use the cached model.

## Permissions

macOS requires two permissions for Transcribe to function. Both are granted to **Transcribe.app** (not to a Python binary), so they persist across reboots.

### Accessibility (required for hotkey + paste)

Without this, the global hotkey will not work and Transcribe cannot paste text into other applications.

Go to **System Settings → Privacy & Security → Accessibility** and toggle on **Transcribe**.

If Transcribe doesn't appear in the list, click the **+** button and navigate to `~/Applications/Transcribe.app`.

> **Running directly from the terminal** (`uv run transcribe`): grant accessibility to your terminal app (Terminal.app, iTerm2, Warp, etc.) instead.

### Microphone (required for recording)

Without this, the app records silence and transcription will fail.

The install script triggers the macOS microphone permission dialog during installation. If you missed it or denied it:

1. Go to **System Settings → Privacy & Security → Microphone**
2. Toggle on **Transcribe**

If Transcribe doesn't appear in the Microphone list, reset and re-run the install script:

```bash
tccutil reset Microphone com.mpe.transcribe
./scripts/install_macos.sh
```

### After granting permissions

Restart the service for changes to take effect:

```bash
launchctl stop com.mpe.transcribe && launchctl start com.mpe.transcribe
```

## How it works

The install script creates a proper macOS `.app` bundle at `~/Applications/Transcribe.app`. This is important because macOS TCC (Transparency, Consent, and Control) requires a **native Mach-O executable** with a stable **bundle identifier** to persistently track permission grants.

The `.app` contains:
- A compiled C launcher (`transcribe-launcher`) as the native `CFBundleExecutable`
- An `Info.plist` with bundle ID `com.mpe.transcribe`
- `NSMicrophoneUsageDescription` for the mic permission dialog

The launcher runs Python as a child process (not `exec`), keeping the native binary alive as the process that macOS associates with TCC grants. The launchd plist uses `open -W -a Transcribe.app` so macOS designates the app as the "responsible process" for TCC.

## Usage

### Running directly

```bash
uv run transcribe
```

When running directly, permissions are granted to your **terminal app**, not to Transcribe.app.

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

1. Press **Cmd+Shift+'** (default hotkey) — a notification and ding confirm recording has started.
2. Speak.
3. Press **Cmd+Shift+'** again — recording stops, transcription runs.
4. The transcribed text is pasted into the currently focused application. Your previous clipboard contents are preserved.

Press **Ctrl+C** to quit (when running directly).

### Changing the hotkey

Edit `pyproject.toml`:

```toml
[tool.transcribe]
hotkey = "super+shift+'"      # macOS default (Cmd+Shift+')
```

Then restart the service.

## Uninstalling

```bash
./scripts/uninstall_macos.sh
```

This removes the launchd agent and `~/Applications/Transcribe.app`. To also remove TCC grants:

```bash
tccutil reset Accessibility com.mpe.transcribe
tccutil reset Microphone com.mpe.transcribe
```

## Available models

All models run locally via Apple's MLX framework with Metal GPU acceleration.

| Model | Download | Speed | Accuracy |
|---|---|---|---|
| `mlx-community/whisper-large-v3-turbo` | ~1.4 GB | Fast | Best (default) |
| `mlx-community/whisper-small` | ~488 MB | Faster | Good |
| `mlx-community/whisper-base` | ~142 MB | Fastest | Lower |

All models support multiple languages. The default (large-v3-turbo) is recommended for the best accuracy/speed tradeoff on Apple Silicon.

## Troubleshooting

**Hotkey not working**
- As a service: ensure **Transcribe** has accessibility permissions (System Settings → Privacy & Security → Accessibility).
- From a terminal: ensure your **terminal app** has accessibility permissions.
- Check logs: `cat /tmp/transcribe.stderr.log` — look for "This process is not trusted".

**"No audio detected" or transcription returns garbage**
- Microphone permissions are missing. Check System Settings → Privacy & Security → Microphone → toggle on Transcribe.
- If Transcribe doesn't appear, reset and reinstall:
  ```bash
  tccutil reset Microphone com.mpe.transcribe
  ./scripts/install_macos.sh
  ```

**Permissions keep resetting after reboot**
- This can happen if the `.app` bundle was rebuilt (which changes its code signature). After reinstalling, re-grant permissions and restart.
- In rare cases, macOS TCC databases become corrupted. Fix with:
  ```bash
  tccutil reset Accessibility com.mpe.transcribe
  tccutil reset Microphone com.mpe.transcribe
  ```
  Then re-grant permissions in System Settings.

**Model download hangs**
- The first run downloads from Hugging Face. Check your internet connection. Models are cached in `~/.cache/huggingface/`.

**Service won't start**
- Check logs: `cat /tmp/transcribe.stderr.log`
- Verify the app exists: `ls ~/Applications/Transcribe.app`
- Try reinstalling: `./scripts/uninstall_macos.sh && ./scripts/install_macos.sh`

**"C compiler (cc) not found" during install**
- Install Xcode Command Line Tools: `xcode-select --install`

**Service not loading**
- Try reloading:
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.mpe.transcribe.plist
  launchctl load ~/Library/LaunchAgents/com.mpe.transcribe.plist
  launchctl start com.mpe.transcribe
  ```
