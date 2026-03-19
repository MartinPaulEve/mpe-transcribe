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
1. Build **Transcribe.app** (a lightweight native wrapper in `~/Applications/`)
2. Compile and code-sign the native launcher binary
3. Install and start a **launchd service** that auto-runs on login

On first launch, macOS will prompt you for two permissions:

1. **Accessibility** — the launcher requests this automatically at startup. A system dialog will appear directing you to **System Settings → Privacy & Security → Accessibility**. Toggle on **Transcribe** and restart the service.
2. **Microphone** — prompted when you first press the hotkey to record. Click **Allow**.

After granting both permissions, restart the service:

```bash
launchctl stop com.mpe.transcribe && launchctl start com.mpe.transcribe
```

The first run will download the Whisper model (~1.4 GB) from Hugging Face. Subsequent runs use the cached model at `~/.cache/huggingface/`.

## Permissions

macOS requires two permissions for Transcribe to function. Both are granted to **Transcribe.app** (not to a Python binary), so they persist across reboots and reinstalls (unless the code signature changes).

### Accessibility (required for paste)

The launcher uses `CGEventPost` to send a synthetic Cmd+V keystroke to paste transcribed text into the focused application. macOS requires Accessibility permission for any app that posts keyboard events to other apps.

On first launch, the launcher calls `AXIsProcessTrustedWithOptions` which triggers the macOS permission dialog automatically. You can also grant it manually:

1. Go to **System Settings → Privacy & Security → Accessibility**
2. Toggle on **Transcribe**

If Transcribe doesn't appear in the list, click the **+** button and navigate to `~/Applications/Transcribe.app`.

> **Note:** The global hotkey itself works without Accessibility (it uses Carbon `RegisterEventHotKey`). Accessibility is needed specifically for pasting the transcribed text.

> **Running directly from the terminal** (`uv run transcribe`): grant accessibility to your terminal app (Terminal.app, iTerm2, Warp, etc.) instead.

### Microphone (required for recording)

Without this, the app records silence and transcription will fail.

macOS prompts for microphone access when the app first tries to open the audio input stream (i.e. the first time you press the hotkey). Click **Allow**.

If you missed or denied the prompt:

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

The install script creates a proper macOS `.app` bundle at `~/Applications/Transcribe.app`. This is necessary because macOS TCC (Transparency, Consent, and Control) requires a **native Mach-O executable** with a stable **bundle identifier** to persistently track permission grants.

The `.app` contains:
- A compiled C launcher (`transcribe-launcher`) as the native `CFBundleExecutable`
- An `Info.plist` with bundle ID `com.mpe.transcribe` and `LSUIElement=true` (background agent, no Dock icon)
- `NSMicrophoneUsageDescription` for the mic permission dialog
- An app icon

### Launcher architecture

The launcher (`transcribe_launcher.c`) is the long-lived process that macOS associates with TCC grants. On startup it:

1. Initialises `NSApplication` so the window server and TCC recognise it as a bundled app
2. Requests Accessibility permission (prompts the user if not yet granted)
3. Registers the global hotkey via Carbon `RegisterEventHotKey` (consumes the keystroke so it doesn't reach the focused app)
4. Forks and execs the Python transcription process as a child
5. Sets up a pipe so Python can request Cmd+V paste operations
6. Runs the Carbon/CoreFoundation event loop

When the hotkey is pressed, the launcher sends `SIGUSR1` to the Python child. Python handles recording, transcription, and clipboard operations, then writes to the pipe to request the launcher post a `Cmd+V` keystroke via `CGEventPost`.

If `RegisterEventHotKey` fails (rare), the launcher falls back to a listen-only `CGEventTap` (which does require Accessibility for hotkey detection too).

## Usage

### Running directly

```bash
uv run transcribe
```

When running directly, permissions are granted to your **terminal app**, not to Transcribe.app. Press **Ctrl+C** to quit.

### As a service

```bash
launchctl start com.mpe.transcribe    # start
launchctl stop com.mpe.transcribe     # stop
launchctl list | grep transcribe      # check status
```

View logs:
```bash
cat /tmp/transcribe.stderr.log        # main log output
tail -f /tmp/transcribe.stderr.log    # follow logs in real-time
cat /tmp/transcribe.stdout.log        # stdout (usually empty)
```

### Workflow

1. Press **Cmd+Shift+'** (default hotkey) — a notification and ding confirm recording has started.
2. Speak.
3. Press **Cmd+Shift+'** again — recording stops, transcription runs.
4. The transcribed text is pasted into the currently focused application. Your previous clipboard contents are preserved.

### Changing the hotkey

Edit `pyproject.toml`:

```toml
[tool.transcribe]
hotkey = "super+shift+'"      # macOS default (Cmd+Shift+')
```

After changing the hotkey, reinstall (the hotkey is compiled into the launcher):

```bash
./scripts/install_macos.sh
```

### Changing the model

Edit `pyproject.toml`:

```toml
[tool.transcribe]
model = "mlx-community/whisper-large-v3-turbo"   # default
```

Then restart the service. See [Available models](#available-models) for options.

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

### Checking logs

The launcher and Python process both log to stderr:

```bash
tail -f /tmp/transcribe.stderr.log
```

Key lines to look for:
- `transcribe-launcher: bundle ID = com.mpe.transcribe` — app identity recognised
- `transcribe-launcher: accessibility granted` — paste will work
- `transcribe-launcher: accessibility NOT granted` — paste will silently fail; grant Accessibility in System Settings
- `transcribe-launcher: registered Carbon hotkey` — hotkey is active
- `INFO:transcribe.app:Recording started` — hotkey press detected, recording
- `transcribe-launcher: posting Cmd+V` — paste requested by Python

### Hotkey not working

- As a service: check logs for `registered Carbon hotkey`. If you see `CGEventTap fallback`, grant **Accessibility** to Transcribe.app in System Settings → Privacy & Security → Accessibility.
- From a terminal: ensure your **terminal app** has accessibility permissions.
- After granting, restart: `launchctl stop com.mpe.transcribe && launchctl start com.mpe.transcribe`

### Text not pasting

If the hotkey works (you see "Recording started" / "Recording stopped" in logs) but text doesn't appear in the focused app:

1. Check logs for `accessibility NOT granted` — this is the most common cause
2. Grant **Accessibility** to Transcribe.app in **System Settings → Privacy & Security → Accessibility**
3. Restart the service
4. Confirm logs now show `accessibility granted`

### "No audio detected" or transcription returns garbage

- Microphone permission is missing. Check **System Settings → Privacy & Security → Microphone** → toggle on **Transcribe**.
- If Transcribe doesn't appear, reset and reinstall:
  ```bash
  tccutil reset Microphone com.mpe.transcribe
  ./scripts/install_macos.sh
  ```

### Permissions keep resetting after reinstall

Each reinstall recompiles and re-signs the launcher, which changes its code signature. macOS may invalidate previous TCC grants. After reinstalling, re-grant permissions in System Settings and restart the service.

In rare cases, macOS TCC databases become corrupted. Fix with:
```bash
tccutil reset Accessibility com.mpe.transcribe
tccutil reset Microphone com.mpe.transcribe
```
Then re-grant permissions in System Settings.

### Model download hangs

The first run downloads from Hugging Face. Check your internet connection. Models are cached in `~/.cache/huggingface/`.

### Service won't start

- Check logs: `cat /tmp/transcribe.stderr.log`
- Verify the app exists: `ls ~/Applications/Transcribe.app`
- Try reinstalling: `./scripts/uninstall_macos.sh && ./scripts/install_macos.sh`

### "C compiler (cc) not found" during install

Install Xcode Command Line Tools: `xcode-select --install`

### Service not loading

Try reloading:
```bash
launchctl unload ~/Library/LaunchAgents/com.mpe.transcribe.plist
launchctl load ~/Library/LaunchAgents/com.mpe.transcribe.plist
launchctl start com.mpe.transcribe
```
