# Windows Setup

## System requirements

### Hardware

- **GPU:** NVIDIA GPU with CUDA support and at least 2 GB VRAM (for the default 0.6B model) or 4 GB VRAM (for the 1.1B model).
- **Microphone:** Any Windows-compatible input device.
- **RAM:** 8 GB minimum; 16 GB recommended. The Parakeet model and NeMo toolkit are memory-hungry during initial load.

### Software

- **OS:** Windows 10 or Windows 11
- **Python:** 3.12+
- **NVIDIA driver:** 525+ with CUDA 11.8+
- **CUDA Toolkit:** 11.8+ (download from [NVIDIA CUDA Toolkit](https://developer.nvidia.com/cuda-downloads))
- **uv:** 0.4+ (for dependency management)

## Installation

### 1. Install Python and uv

Download Python 3.12+ from [python.org](https://www.python.org/downloads/windows/) and ensure it's added to your PATH.

Install uv (see the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/)):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone and install

```powershell
git clone <repo-url> transcribe
cd transcribe
uv sync --extra windows
```

### 3. Verify CUDA

```powershell
uv run python -c "import torch; print(torch.cuda.is_available())"
```

This should print `True`. If not, verify your NVIDIA drivers and CUDA toolkit installation.

## Running

```powershell
uv run transcribe
```

The first run will download the Parakeet model (~1.5 GB). Subsequent runs use the cached model.

### Default hotkey

**Ctrl+Shift+;** (semicolon)

Press to start recording, press again to stop. The transcribed text is pasted into the active application via Ctrl+V, and your previous clipboard contents are restored afterwards.

## Configuration

All settings live in `transcribe.toml` in the repo root (copy `transcribe.toml.example` to start):

```toml
model = "nvidia/parakeet-tdt-0.6b-v3"   # default; or "nvidia/parakeet-rnnt-1.1b" for higher accuracy
hotkey = "ctrl+shift+;"                  # default
```

See the [Configuration section in the README](../README.md#configuration) for the full reference — corrections, per-event notification control, and the TOML key-placement gotcha.

## Voice recognition corrections

Define `[replacements]` and `[custom_terms]` in `transcribe.toml` — see the [README](../README.md#voice-recognition-corrections) for full details.

## Model choices

| Model | VRAM | Speed | Accuracy |
|---|---|---|---|
| `nvidia/parakeet-tdt-0.6b-v3` (default) | ~2 GB | Fast | Good |
| `nvidia/parakeet-rnnt-1.1b` | ~4 GB | Slower | Higher |

## Networked mode

The host/client split described in [NETWORK.md](NETWORK.md) is aimed at Linux and macOS: the client-only extras (`client-linux`, `client-macos`) and the client service installer do not cover Windows. A Windows machine with the full `windows` extra installed runs standalone.

## Troubleshooting

### "CUDA not available"

1. Ensure you have an NVIDIA GPU
2. Install/update NVIDIA drivers (525+)
3. Install the [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads)
4. Verify with: `nvidia-smi`

### Hotkey not working

- Some applications running as Administrator may not receive hotkey events from a non-elevated process. Try running `uv run transcribe` from an elevated prompt.
- Check that no other application has claimed the same hotkey combination.

### No audio input

- Check Windows Settings > Privacy > Microphone and ensure microphone access is enabled for desktop apps.
- Verify your microphone is set as the default input device in Sound Settings.

### Paste not working in some applications

- The app simulates Ctrl+V via `SendInput`. Some applications (especially those running with elevated privileges) may not accept simulated input from a non-elevated process.

### NeMo installation issues

If `nemo_toolkit[asr]` fails to install on Windows, some of its native dependencies (e.g., `pynini`, `kaldi-native-fbank`) may not have pre-built Windows wheels. Options:

1. Install from conda-forge where available
2. Use WSL2 with the Linux installation path instead
