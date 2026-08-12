# Networked Mode (Host + Client)

Split transcription across the network: a **host** records and transcribes, while lightweight **clients** trigger transcriptions with their hotkey and paste the resulting text locally. Transport is connectionless UDP, encrypted and authenticated end-to-end with a pre-shared key.

## Why

The transcription engine only runs where the accelerator lives: macOS uses mlx-whisper on the Apple Silicon GPU, Linux uses NeMo Parakeet on an NVIDIA CUDA GPU. A Linux VM on an Apple Silicon Mac (e.g. Parallels) has neither — MLX is macOS-only and there is no GPU passthrough — so local transcription in the VM is impossible.

But if you work *inside* the VM, the trigger and the paste must happen there. Networked mode splits the app accordingly: the client presses a hotkey → asks the host to start/stop a recording → the host records **from its own microphone**, transcribes, and sends the text back → the client pastes it. Because the VM is a guest on the same Mac, the host's mic *is* your mic — **no audio ever crosses the network**.

A client needs none of the transcription stack — no NeMo, no MLX, no model, no audio libraries — only the hotkey and paste backends plus the network/crypto code.

## The three modes

| Mode | What runs | Selected by |
|---|---|---|
| `standalone` | Everything locally (the default; today's behaviour, unchanged) | default, or `--standalone` |
| `host` | Records + transcribes here; serves clients over UDP | `mode = "host"` or `--host` |
| `client` | Hotkey + paste only; a remote host transcribes | `mode = "client"` or `--client` |

Mode is set in `[tool.transcribe.network]` in `pyproject.toml`; the CLI flags override the config. Client mode also accepts `--server-host` and `--server-port` overrides.

## Quick start

### 1. Generate a shared key (once, on either machine)

```bash
uv run transcribe keygen
```

This prints a fresh base64-encoded 32-byte key. Host and clients must use the **same** key. Never put it in `pyproject.toml` (that file is committed to git) — supply it via the `TRANSCRIBE_PSK` environment variable or a `chmod 600` key file (see [Security model](#security-model)).

### 2. Configure the host (the Mac)

In the host's `pyproject.toml`:

```toml
[tool.transcribe.network]
mode = "host"
# key_file = "~/.config/transcribe/psk.key"   # or export TRANSCRIBE_PSK
```

Save the key:

```bash
mkdir -p ~/.config/transcribe
echo '<base64 key from keygen>' > ~/.config/transcribe/psk.key
chmod 600 ~/.config/transcribe/psk.key
```

Then run (a normal full install per [MAC.md](MAC.md) or [LINUX.md](LINUX.md) is required — the host needs the whole transcription stack):

```bash
uv run transcribe --host
```

With `mode = "host"` in the config, a plain `uv run transcribe` (or the existing installed service) also starts in host mode. For a service, prefer `key_file` over the environment variable — service environments often don't inherit your shell's exports.

### 3. Configure the client (the VM)

In the client's checkout of `pyproject.toml`:

```toml
[tool.transcribe.network]
mode = "client"
server_host = "10.211.55.2"    # the host as seen from the VM
client_label = "nixos-vm"      # optional, identifies this client
```

Install the light client-only dependency set and run:

```bash
uv sync --extra client-linux    # or client-macos
uv run --extra client-linux transcribe --client
```

The client still needs the platform paste/notify binaries (`xclip`, `xdotool`, `libnotify-bin` on X11; `wl-clipboard`, `ydotool` on Wayland) but **not** `libportaudio2`, a GPU, or any model.

### 4. Install the client as a service

```bash
./scripts/install_client.sh
```

This syncs the client-only extra (`client-linux` or `client-macos`), creates `~/.config/transcribe/env` (chmod 600) for you to put `TRANSCRIBE_PSK=<key>` in, and installs:

- **Linux:** a systemd user unit, `transcribe-client.service`, that starts with your graphical session and reads the key from `~/.config/transcribe/env`:

  ```bash
  systemctl --user start transcribe-client
  systemctl --user stop transcribe-client
  systemctl --user status transcribe-client
  journalctl --user -u transcribe-client -f
  ```

- **macOS:** a launchd agent, `~/Library/LaunchAgents/gd.eve.transcribe-client.plist`, which sources the same env file:

  ```bash
  launchctl unload ~/Library/LaunchAgents/gd.eve.transcribe-client.plist
  launchctl load ~/Library/LaunchAgents/gd.eve.transcribe-client.plist
  ```

To remove the service: `./scripts/uninstall_client.sh` (the key file in `~/.config/transcribe/env` is left in place).

### 5. Use it

Press the hotkey in the VM — the host starts recording (notification + ding on both ends), press again — the host transcribes and the text is pasted into the VM window you were typing in.

## Configuration reference

All keys live in `[tool.transcribe.network]` in `pyproject.toml`. Every key is optional; the defaults preserve standalone behaviour. Unknown keys are rejected at startup.

### Mode

| Key | Default | Meaning |
|---|---|---|
| `mode` | `"standalone"` | `"standalone"`, `"host"`, or `"client"` |

### Host

| Key | Default | Meaning |
|---|---|---|
| `bind_host` | `"0.0.0.0"` | Address the host's UDP socket binds to |
| `bind_port` | `47800` | UDP port the host listens on |
| `also_paste_locally` | `false` | Host also pastes the text into its own focused window |
| `host_hotkey` | `false` | The host user can trigger recordings locally with the hotkey too |
| `subscriber_ttl` | `30` | Seconds after which a silent client is pruned from the registry |
| `max_record_seconds` | `60` | Lost-STOP safeguard: auto-stop a recording after this long |
| `deliver_to` | `"initiator"` | `"initiator"` sends TEXT only to the client that started the session; `"all"` broadcasts it to every subscriber |
| `allowed_clients` | (unset) | Optional list of `client_label` values allowed to trigger; unset = any client with the key |

### Client

| Key | Default | Meaning |
|---|---|---|
| `server_host` | `"127.0.0.1"` | The host's address as seen from the client |
| `server_port` | `47800` | The host's UDP port |
| `renew_interval` | `10` | Heartbeat period in seconds (keep it below `subscriber_ttl`) |
| `client_label` | `""` | Label identifying this client (used by `allowed_clients` and shown as the session initiator); empty falls back to `"client"` |

### Reliability

| Key | Default | Meaning |
|---|---|---|
| `ack` | `true` | Reliable delivery (ACK + retransmit) for START, STOP, and TEXT |
| `max_retries` | `4` | Retransmissions before giving up on an unACKed datagram |
| `retry_backoff_ms` | `150` | Initial retransmit delay; doubles on each retry |
| `max_datagram_bytes` | `1200` | Cap on datagram size (avoids IP fragmentation); long texts are chunked |
| `max_message_bytes` | `65536` | Cap on a reassembled message; oversized messages are discarded |

### Security

| Key | Default | Meaning |
|---|---|---|
| `key_env` | `"TRANSCRIBE_PSK"` | Name of the environment variable holding the base64 32-byte key |
| `key_file` | (unset) | Path to a `chmod 600` file holding the base64 key; used only if the env var is not set |
| `clock_skew` | `30` | Freshness window in seconds: messages timestamped outside ±this are dropped |

### Example: host

```toml
[tool.transcribe.network]
mode = "host"
# bind_host = "0.0.0.0"
# bind_port = 47800
# also_paste_locally = false     # paste on the host too
# host_hotkey = false            # allow triggering from the host's own hotkey
# deliver_to = "initiator"       # or "all" to broadcast text to every client
# allowed_clients = ["nixos-vm"] # restrict who may trigger
# max_record_seconds = 60
key_file = "~/.config/transcribe/psk.key"
```

### Example: client

```toml
[tool.transcribe.network]
mode = "client"
server_host = "10.211.55.2"      # the host, as seen from this machine
# server_port = 47800
client_label = "nixos-vm"
# key_file = "~/.config/transcribe/psk.key"  # or TRANSCRIBE_PSK in the env
```

## Security model

A client pastes received text into whatever window is focused — possibly a terminal — and a forged START/STOP could drive the host's microphone. Both directions are therefore authenticated:

- **Pre-shared key.** One high-entropy 32-byte key per deployment, generated with `transcribe keygen`. Resolution order: the environment variable named by `key_env` (default `TRANSCRIBE_PSK`) first, then `key_file`. If neither yields a key, host and client modes **refuse to start** — there is no unauthenticated fallback. **Never store the key in `pyproject.toml`**; it is committed to version control.
- **AEAD encryption.** Every datagram body is encrypted and authenticated with ChaCha20-Poly1305, using a key derived from the PSK via HKDF-SHA256 (so the raw PSK is never used directly) and a fresh random 12-byte nonce per datagram. The frame header is bound as associated data, so it cannot be tampered with either. Any datagram that fails to decrypt is dropped silently — no error replies, no oracle.
- **Replay protection.** Bodies carry a timestamp and a random id. Anything timestamped outside ±`clock_skew` seconds of local time is dropped, and seen ids are cached (expiring after 2 × `clock_skew`) so a captured datagram cannot be replayed — a replayed START never re-triggers the mic, and a replayed TEXT never pastes twice.
- **Trigger control.** Set `allowed_clients` on the host to restrict which client labels may start/stop recordings. STARTs are additionally rate-limited (at most one per second), and the subscriber registry is capped.
- **Paste hygiene.** The client strips C0/C1 control characters (except newline and tab) from received text before pasting, and pastes via clipboard + Ctrl+V rather than synthesised keystrokes.

## Protocol overview

The wire protocol (`MPET`, version 1) frames every datagram as:

```
MAGIC "MPET" (4) | VERSION 0x01 (1) | TYPE (1) | NONCE (12) | CIPHERTEXT
```

Message types:

| Type | Name | Direction | Purpose |
|---|---|---|---|
| 0x01 | REGISTER | client → host | Subscribe; start heartbeating |
| 0x02 | RENEW | client → host | Heartbeat, keeps the subscription alive |
| 0x03 | UNREGISTER | client → host | Clean unsubscribe on shutdown |
| 0x04 | START | client → host | Begin a recording session |
| 0x05 | STOP | client → host | End the session → transcribe |
| 0x06 | STATE | host → clients | Session state (idle/recording/transcribing/error) |
| 0x07 | TEXT | host → client(s) | One chunk of a transcription |
| 0x08 | ACK | either | Acknowledge a reliably-sent message |
| 0x09 | AUDIO | client → host | Reserved for future client-side audio capture |

Session semantics (the host is authoritative and holds **one** session at a time):

- Commands are **explicit** — START and STOP, never a blind toggle — so retransmits and duplicates over lossy UDP are harmless. The client tracks the host's state from STATE broadcasts and sends the appropriate command; if its view is unknown it sends START and the host resolves it.
- **Idempotency:** a duplicate START for the live session is just re-ACKed; a START for a *different* session while busy is rejected (the host re-sends its current STATE so the newcomer syncs); a STOP for a stale session is ACKed but ignored.
- **Auto-stop:** if a STOP is lost, the host stops the recording itself after `max_record_seconds`, so a dropped datagram can never wedge the host in recording.
- Long transcriptions are split into chunks sized to `max_datagram_bytes`; the client reassembles, ACKs, deduplicates, and pastes exactly once. STATE messages are fire-and-forget (the next one supersedes a lost one); START, STOP, and TEXT are retransmitted with exponential backoff until ACKed or `max_retries` is exhausted.

## Operational notes

- **Finding the host address from a Parallels VM.** With Parallels shared networking the Mac is the VM's default gateway (conventionally `10.211.55.2`). From the VM:

  ```bash
  ip route show default    # the gateway is the Mac
  ```

  This address is stable across reboots. The host replies to whatever source address/port it saw on REGISTER/START, so return routing and NAT need no configuration, and the client's heartbeats keep any NAT/firewall mapping warm.

- **macOS firewall.** If the Mac's firewall is on, it may block inbound UDP on `bind_port` (47800). Allow incoming connections for the Python interpreter when prompted, or add it under **System Settings → Network → Firewall → Options**. The client initiates all traffic, so the client side rarely needs firewall changes.

- **Clock sync.** Replay protection requires host and client clocks to agree to within `clock_skew` (30 s by default). Both macOS and any normal Linux distro run NTP out of the box; if messages are silently dropped, check `timedatectl` in the VM.

- **Multiple clients.** All registered clients receive STATE broadcasts (so everyone's notifications stay in sync). TEXT delivery honours `deliver_to` — with the default `"initiator"` the text lands only where you were typing. The host is single-session: a second client triggering while a session is live is rejected until the host returns to idle.

- **Backward compatibility.** `standalone` is the default mode; existing installs see no change in behaviour whatsoever.

## Troubleshooting

**"no pre-shared key configured" at startup** — host and client modes refuse to run without a key. Generate one with `uv run transcribe keygen`, then either export it (`TRANSCRIBE_PSK=<key>`), put `TRANSCRIBE_PSK=<key>` in `~/.config/transcribe/env` (for the client service), or point `key_file` at a `chmod 600` file containing it.

**Hotkey pressed but nothing happens / nothing pastes** — all authentication failures are silent drops by design, so a key mismatch produces no errors. Check in order:

1. The **same** base64 key is configured on host and client.
2. `server_host`/`server_port` on the client actually point at the host (`ip route show default` from a Parallels VM), and the host logs show `Host mode: listening on 0.0.0.0:47800`.
3. The macOS firewall allows inbound UDP on the host's `bind_port`.
4. Clocks agree to within `clock_skew` (30 s) — stale messages are dropped.
5. Client logs: `journalctl --user -u transcribe-client -f` (Linux service) or run `uv run --extra client-linux transcribe --client` in a terminal.

**Worried about duplicate pastes?** Don't be: retransmitted TEXT chunks are deduplicated by message id, and a completed message is delivered to the paste backend exactly once. Similarly, a retried START cannot start a second recording — duplicates are idempotent.

**Trigger ignored while the host is busy** — the host holds one session at a time. A START from a second client (or a new session) while recording or transcribing is rejected; wait for the state to return to idle.

**Client pastes on the wrong machine** — with `deliver_to = "all"` every subscriber pastes the text. Use the default `"initiator"` so text goes only to the client that triggered the session; use `also_paste_locally = true` if the host should paste too.
