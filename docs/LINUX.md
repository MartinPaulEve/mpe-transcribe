# Linux Setup

## System requirements

### Hardware

- **GPU:** NVIDIA GPU with CUDA support and at least 2 GB VRAM (for the default 0.6B model) or 4 GB VRAM (for the 1.1B model). Tested on RTX 5090. *Not needed for [client-only installs](#using-this-machine-as-a-network-client-no-gpu-needed).*
- **Microphone:** Any PulseAudio/PipeWire-compatible input device.
- **RAM:** 8 GB minimum; 16 GB recommended. The Parakeet model and NeMo toolkit are memory-hungry during initial load.

### Software

- **OS:** Ubuntu 22.04+ (or any Linux distro with systemd)
- **Python:** 3.12+
- **NVIDIA driver:** 525+ with CUDA 11.8+ (PyTorch will pull its own CUDA runtime via pip)
- **uv:** 0.4+ (for dependency management)

### System packages — X11

Install these via `apt`:

```bash
sudo apt install libportaudio2 xdotool xclip libnotify-bin
```

| Package | Purpose |
|---|---|
| `libportaudio2` | Audio I/O backend for `sounddevice` |
| `xdotool` | Simulates Ctrl+V paste into the active window |
| `xclip` | Sets/reads the X11 clipboard |
| `libnotify-bin` | Provides `notify-send` for desktop notifications |

### System packages — Wayland

If you are running a Wayland session (e.g. Ubuntu 24.04+ defaults to Wayland on GNOME), the app auto-detects it and uses the Wayland backend. You need:

```bash
sudo apt install libportaudio2 xclip wl-clipboard ydotool libnotify-bin
```

| Package | Purpose |
|---|---|
| `libportaudio2` | Audio I/O backend for `sounddevice` |
| `xclip` | Preferred clipboard access, via the XWayland bridge (see [Wayland specifics](#wayland-specifics)) |
| `wl-clipboard` | Provides `wl-copy`/`wl-paste` — fallback when `xclip` or XWayland is unavailable |
| `ydotool` | Injects the Ctrl+V paste chord (or types text directly) via the kernel input layer |
| `libnotify-bin` | Provides `notify-send` for desktop notifications |

**Additional Wayland setup:**

1. **`input` group membership** — the Wayland hotkey listener reads keyboard events via evdev, which requires permission to access `/dev/input/` devices:

   ```bash
   sudo usermod -aG input $USER
   ```

   Then log out and back in for the group change to take effect.

2. **`ydotoold` daemon** — `ydotool` requires its daemon to be running:

   ```bash
   sudo systemctl enable ydotoold
   sudo systemctl start ydotoold
   ```

**NixOS:** install the packages via your system configuration rather than `apt`, and enable ydotool with `programs.ydotool.enable = true;` (which sets up `ydotoold` and the required permissions).

## Wayland specifics

Wayland deliberately gives applications less global access than X11, so the backends work differently. Knowing how saves debugging time.

### The hotkey listener is passive

The listener reads raw evdev events (hence the `input` group requirement). It **cannot consume the chord** — the keystroke also reaches the focused application. A chord that produces a printable character will therefore type that character where you're working: `ctrl+shift+;` types `:`.

Pick a hotkey with no character output, such as:

```toml
hotkey = "super+shift+;"
```

Avoid `ctrl+\` variants entirely — terminals map Ctrl+\ to SIGQUIT and will kill the foreground process.

### Session detection

The app decides between X11 and Wayland using `XDG_SESSION_TYPE` and `WAYLAND_DISPLAY`, with an automatic fallback: if the environment is inconclusive, it looks for a live `wayland-*` socket in `XDG_RUNTIME_DIR`. This means launching from a stale tmux/byobu shell (whose environment predates the current session) still picks Wayland correctly. At startup, client mode logs which backends were chosen:

```
Session: wayland; hotkey listener: WaylandHotkeyListener; clipboard: WaylandClipboard
```

### Clipboard and paste

Clipboard access prefers **xclip through the XWayland bridge**: X11 selections need no keyboard focus, whereas GNOME withholds the data-control protocol from `wl-clipboard`, whose fallback pops transient surfaces that steal focus mid-paste. Mutter mirrors the X11 and Wayland clipboards, so xclip reaches Wayland apps too. `wl-clipboard` remains the fallback when xclip or XWayland is unavailable.

Pasting injects a Ctrl+V chord via ydotool at human typing speed, with a safety release afterwards so no surface is left seeing a phantom held key. If any synthetic Ctrl+V misbehaves in your environment, set:

```toml
paste_method = "type"
```

which skips the clipboard entirely and types the text directly via ydotool — slower for long texts, but immune to paste quirks.

## Installation

Clone the repo and install with the Linux extras:

```bash
git clone <repo-url> transcribe
cd transcribe
uv sync --extra linux
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

### Using this machine as a network client (no GPU needed)

If this machine has no NVIDIA GPU (e.g. it is a Linux VM on an Apple Silicon Mac), it can run as a lightweight **client**: the hotkey and paste happen here, while a networked host records and transcribes. Skip the full install above and instead run:

```bash
uv sync --extra client-linux
./scripts/install_client.sh
```

No model, GPU, or `libportaudio2` required — the paste/notify packages (`xclip`/`xdotool`/`libnotify-bin` on X11; `xclip`/`wl-clipboard`/`ydotool`/`libnotify-bin` on Wayland) are still needed. See [NETWORK.md](NETWORK.md) for the full guide.

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

All settings live in `transcribe.toml` in the repo root (copy `transcribe.toml.example` to start) — hotkey, model, paste method, corrections, and notification switches. See the [Configuration section in the README](../README.md#configuration) for the full reference, including the TOML key-placement gotcha and per-event notification control. On Wayland, remember the [printable-chord caveat](#the-hotkey-listener-is-passive) when choosing a hotkey.

## Available models

| Model | Size | Speed | Accuracy | VRAM |
|---|---|---|---|---|
| `nvidia/parakeet-tdt-0.6b-v3` | 0.6B params | Fast | Good | ~2 GB |
| `nvidia/parakeet-rnnt-1.1b` | 1.1B params | Slower | Higher | ~4 GB |

Both are English-only models. The default (0.6B) is recommended for interactive use since transcription latency matters.

## Troubleshooting

**"PortAudio library not found"** — Install `libportaudio2`:
```bash
sudo apt install libportaudio2
```

**Hotkey not working (X11)** — Check you are running X11:
```bash
echo $XDG_SESSION_TYPE   # should print "x11"
```
If another application has already grabbed the same key combination, `XGrabKey` will silently fail. Try a different hotkey in `transcribe.toml`.

**Hotkey not working (Wayland)** — Ensure your user is in the `input` group:
```bash
groups   # should include "input"
```
If not, add yourself (`sudo usermod -aG input $USER`) and log out/in. Also check that `ydotoold` is running:
```bash
systemctl status ydotoold
```

**Hotkey types a character into the focused app (Wayland)** — expected with the passive listener; choose a chord with no printable output (e.g. `super+shift+;`). See [Wayland specifics](#wayland-specifics).

**Wrong backend selected when launching from tmux/byobu** — session detection falls back to the live `wayland-*` socket, so this should resolve itself; check the `Session: ...` startup log line to confirm.

**Model download hangs** — The first run downloads ~1.2 GB from NVIDIA NGC. Check your internet connection and firewall rules. The model is cached in `~/.cache/torch/NeMo/` after the first download.

**Service won't start** — Check logs:
```bash
journalctl --user -u transcribe -e
```
Common causes: missing `DISPLAY` environment variable (the service sets `DISPLAY=:0` by default), or missing system packages.
