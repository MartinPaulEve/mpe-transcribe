# Linux Setup

## System requirements

### Hardware

- **GPU:** NVIDIA GPU with CUDA support and at least 2 GB VRAM (for the default 0.6B model) or 4 GB VRAM (for the 1.1B model). Tested on RTX 5090.
- **Microphone:** Any PulseAudio/PipeWire-compatible input device.
- **RAM:** 8 GB minimum; 16 GB recommended. The Parakeet model and NeMo toolkit are memory-hungry during initial load.

### Software

- **OS:** Ubuntu 22.04+ (or any Linux distro with systemd)
- **Python:** 3.12+
- **NVIDIA driver:** 525+ with CUDA 11.8+ (PyTorch will pull its own CUDA runtime via pip)
- **uv:** 0.4+ (for dependency management)

### System packages — X11

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

### System packages — Wayland (experimental)

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
