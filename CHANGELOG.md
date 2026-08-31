## 1.9.2 (2026-08-31)

### Fix

- **net**: bind the UDP port exclusively

## 1.9.1 (2026-08-31)

### Fix

- **app**: run the host stop pipeline off the network thread
- **net**: watchdog for stuck sessions, stop-failure recovery, drop logging
- **notifier**: async dispatch and subprocess timeouts

## 1.9.0 (2026-08-25)

### Feat

- **notifications**: per-event notification controls

## 1.8.1 (2026-08-24)

### Fix

- **app**: clearer stop notification, longer record safeguard, formatting
- **session**: detect Wayland via runtime-dir socket when env is stale

## 1.8.0 (2026-08-24)

### Feat

- **host**: log effective host flags and local-paste decisions
- **config**: reject unknown and misplaced config keys
- **config**: transcribe.toml user config; notifier hardening + toggles

### Fix

- **wayland**: xclip clipboard via XWayland bridge + paste_method=type escape hatch
- **wayland**: isolate paste chord from clipboard focus churn
- **wayland**: inject Ctrl+V at human speed to avoid app double-paste

## 1.7.0 (2026-08-22)

### Feat

- **scripts**: client-only install/uninstall + service unit
- **cli**: add `transcribe keygen`
- **app**: dispatch standalone/host/client; wire triggers + paste + state
- **net**: UDP Client with trigger, register/renew/ack, reassembly
- **net**: UDP Host with registry, session control + retransmit (host.py)
- **net**: AEAD seal/open, replay + freshness guards (crypto.py) with tests
- **net**: wire protocol framing + chunking (protocol.py) with tests
- **config**: parse [tool.transcribe.network] and resolve the PSK

## 1.6.0 (2026-04-04)

### Feat

- **corrections**: log when corrections are applied to transcription
- **corrections**: add voice recognition custom terms correction

## 1.5.1 (2026-03-26)

### Fix

- **clipboard**: prevent bare "v" paste on X11 due to modifier race
- **service**: use uv run with --extra linux in systemd service

## 1.5.0 (2026-03-25)

### Feat

- **recorder**: check USB audio device health before recording
- **windows**: add Windows platform support

## 1.4.0 (2026-03-19)

### Feat

- **mac**: detect missing accessibility permissions on startup
- add macOS Apple Silicon support with mlx-whisper STT

### Fix

- request Accessibility permission at launcher startup
- use pipe instead of SIGUSR2 for paste IPC
- post Cmd+V from launcher process via SIGUSR2
- use CGEventPost for Cmd+V instead of osascript
- declare RunApplicationEventLoop symbols removed from SDK headers
- use RunApplicationEventLoop for Carbon hotkey dispatch
- use RegisterEventHotKey to consume keystroke, fallback to CGEventTap
- consume hotkey event so it doesn't reach the focused app
- register as NSApplication for TCC, remove LSBackgroundOnly
- move hotkey monitoring to C launcher for service TCC compatibility
- request accessibility interactively instead of just warning
- generate app icon before codesigning to preserve TCC trust
- **mac**: launchctl stop now actually stops the app
- **mac**: change default hotkey to Cmd+Shift+' to avoid Chrome conflict
- **mac**: use compiled native Mach-O trampoline for TCC identity
- **mac**: use open -W -a for TCC responsible process, no exec
- **mac**: use .app bundle for stable TCC permissions
- **mac**: add __main__.py so python -m transcribe works
- **mac**: fix hotkey regression and improve permission handling
- **mac**: codesign binaries so macOS can track permissions
- **mac**: replace slow swift subprocess with instant ctypes calls
- **mac**: request microphone permission interactively before service use
- **mac**: detect missing microphone permissions and silent recordings
- **mac**: pass audio array directly to mlx_whisper, removing ffmpeg dependency
- **mac**: prevent spurious shutdown and handle PortAudio errors

## 1.3.1 (2026-03-18)

### Fix

- **clipboard**: preserve non-text content and increase restore delay

## 1.3.0 (2026-03-15)

### Feat

- **wayland**: add experimental Wayland support via evdev and ydotool

## 1.2.0 (2026-03-15)

### Feat

- **app**: notify with ding when model is loaded and ready

### Fix

- **hotkey**: debounce rapid keypresses to prevent X11 auto-repeat

## 1.1.0 (2026-03-12)

### Feat

- initial implementation of voice transcription app

### Fix

- **app**: handle empty recordings and prevent event loop blocking
