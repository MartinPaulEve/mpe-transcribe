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
