import base64
import binascii
import os
import platform
import tomllib
from pathlib import Path

DEFAULT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
DEFAULT_HOTKEY = "ctrl+shift+;"

NETWORK_DEFAULTS = {
    "mode": "standalone",
    "bind_host": "0.0.0.0",
    "bind_port": 47800,
    "also_paste_locally": False,
    "host_hotkey": False,
    "subscriber_ttl": 30,
    "max_record_seconds": 300,
    "deliver_to": "initiator",
    "allowed_clients": None,
    "server_host": "127.0.0.1",
    "server_port": 47800,
    "renew_interval": 10,
    "client_label": "",
    "ack": True,
    "max_retries": 4,
    "retry_backoff_ms": 150,
    "max_datagram_bytes": 1200,
    "max_message_bytes": 65536,
    "key_env": "TRANSCRIBE_PSK",
    "key_file": None,
    "clock_skew": 30,
}


class ConfigError(Exception):
    """A configuration value is missing or invalid."""


def load_network_config(section: dict | None = None) -> dict:
    """Merge a [network] section over the defaults."""
    network = dict(NETWORK_DEFAULTS)
    if section:
        unknown = set(section) - set(NETWORK_DEFAULTS)
        if unknown:
            raise ConfigError(
                "unknown [network] keys: " + ", ".join(sorted(unknown))
            )
        network.update(section)
    if network["mode"] not in ("standalone", "host", "client"):
        raise ConfigError(
            f"invalid network mode: {network['mode']!r} "
            "(expected standalone, host, or client)"
        )
    if network["deliver_to"] not in ("initiator", "all"):
        raise ConfigError(
            f"invalid deliver_to: {network['deliver_to']!r} "
            "(expected initiator or all)"
        )
    return network


def _decode_psk(value: str, source: str) -> bytes:
    try:
        key = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConfigError(f"invalid base64 key from {source}: {exc}") from exc
    if len(key) != 32:
        raise ConfigError(
            f"key from {source} must be 32 bytes, got {len(key)}"
        )
    return key


def resolve_psk(network: dict, environ: dict | None = None) -> bytes:
    """Resolve the pre-shared key: env var first, then key_file.

    Raises ConfigError if no key is configured or the key is
    malformed. Never returns a default — networked modes must
    refuse to start without a real key.
    """
    if environ is None:
        environ = os.environ
    env_name = network.get("key_env") or "TRANSCRIBE_PSK"
    value = environ.get(env_name)
    if value:
        return _decode_psk(value, f"${env_name}")
    key_file = network.get("key_file")
    if key_file:
        path = Path(key_file).expanduser()
        try:
            content = path.read_text()
        except OSError as exc:
            raise ConfigError(
                f"cannot read key_file {key_file}: {exc}"
            ) from exc
        return _decode_psk(content, str(path))
    raise ConfigError(
        f"no pre-shared key configured: set ${env_name} or key_file "
        "(generate one with `transcribe keygen`)"
    )


DEFAULT_MODEL_MACOS = "mlx-community/whisper-large-v3-turbo"
DEFAULT_HOTKEY_MACOS = "super+shift+'"


def _default_model() -> str:
    if platform.system() == "Darwin":
        return DEFAULT_MODEL_MACOS
    return DEFAULT_MODEL


def _default_hotkey() -> str:
    if platform.system() == "Darwin":
        return DEFAULT_HOTKEY_MACOS
    return DEFAULT_HOTKEY


def _load_user_section(root: Path) -> dict:
    """Load the user config section.

    Prefers transcribe.toml (flat keys, no [tool.transcribe]
    wrapper); falls back to [tool.transcribe] in pyproject.toml
    for older setups. When transcribe.toml exists it replaces the
    pyproject section entirely — the two are never merged.
    """
    config_file = root / "transcribe.toml"
    if config_file.exists():
        with open(config_file, "rb") as f:
            return tomllib.load(f)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        return data.get("tool", {}).get("transcribe", {})
    return {}


_KNOWN_TOP_LEVEL_KEYS = frozenset(
    {
        "model",
        "hotkey",
        "paste_method",
        "replacements",
        "custom_terms",
        "notifications",
        "network",
    }
)

_KNOWN_SECTION_KEYS = {
    "custom_terms": frozenset({"terms", "threshold"}),
    "notifications": frozenset({"visual", "sound", "events"}),
}

NOTIFICATION_EVENTS = ("ready", "recording", "stopped", "pasted", "error")


def _reject_unknown_keys(section: dict) -> None:
    """Fail loudly on unknown or misplaced keys.

    In TOML a key written below a [section] header belongs to that
    section, so a misplaced top-level key (e.g. paste_method under
    [custom_terms]) would otherwise be silently ignored.
    """
    unknown = set(section) - _KNOWN_TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError("unknown config keys: " + ", ".join(sorted(unknown)))
    for name, known in _KNOWN_SECTION_KEYS.items():
        sub = section.get(name, {})
        if not isinstance(sub, dict):
            continue
        unknown = set(sub) - known
        if unknown:
            raise ConfigError(
                f"unknown [{name}] keys: "
                + ", ".join(sorted(unknown))
                + " (top-level keys must appear above the first "
                "[section] header)"
            )
    notifications = section.get("notifications")
    if isinstance(notifications, dict):
        events = notifications.get("events")
        if isinstance(events, dict):
            unknown = set(events) - set(NOTIFICATION_EVENTS)
            if unknown:
                raise ConfigError(
                    "unknown [notifications.events] keys: "
                    + ", ".join(sorted(unknown))
                )


def load_config(root: Path | None = None) -> dict:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    section = _load_user_section(root)
    _reject_unknown_keys(section)
    custom_terms_section = section.get("custom_terms", {})
    notifications = section.get("notifications", {})
    notification_events = notifications.get("events", {})
    paste_method = section.get("paste_method", "ctrl+v")
    if paste_method not in ("ctrl+v", "type"):
        raise ConfigError(
            f"invalid paste_method: {paste_method!r} (expected ctrl+v or type)"
        )
    return {
        "paste_method": paste_method,
        "model": section.get("model", _default_model()),
        "hotkey": section.get("hotkey", _default_hotkey()),
        "replacements": section.get("replacements", {}),
        "custom_terms": custom_terms_section.get("terms", []),
        "custom_terms_threshold": custom_terms_section.get("threshold", 0.8),
        "notifications": {
            "visual": bool(notifications.get("visual", True)),
            "sound": bool(notifications.get("sound", True)),
            "events": {
                name: bool(notification_events.get(name, True))
                for name in NOTIFICATION_EVENTS
            },
        },
        "network": load_network_config(section.get("network")),
    }


def parse_hotkey(hotkey_str: str) -> tuple[set[str], str]:
    """Parse 'ctrl+shift+;' into ({'ctrl', 'shift'}, ';')."""
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    modifiers = set()
    key = None
    modifier_names = {"ctrl", "shift", "alt", "super"}
    for part in parts:
        if part in modifier_names:
            modifiers.add(part)
        else:
            key = part
    if not key:
        raise ValueError(f"No key found in hotkey string: {hotkey_str!r}")
    if not modifiers:
        raise ValueError(
            f"No modifiers found in hotkey string: {hotkey_str!r}"
        )
    return modifiers, key


# macOS virtual keycodes (from Events.h / Carbon)
_MACOS_KEYCODES = {
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "f": 0x03,
    "h": 0x04,
    "g": 0x05,
    "z": 0x06,
    "x": 0x07,
    "c": 0x08,
    "v": 0x09,
    "b": 0x0B,
    "q": 0x0C,
    "w": 0x0D,
    "e": 0x0E,
    "r": 0x0F,
    "y": 0x10,
    "t": 0x11,
    "o": 0x1F,
    "u": 0x20,
    "i": 0x22,
    "p": 0x23,
    "l": 0x25,
    "j": 0x26,
    "k": 0x28,
    "n": 0x2D,
    "m": 0x2E,
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "5": 0x17,
    "6": 0x16,
    "7": 0x1A,
    "8": 0x1C,
    "9": 0x19,
    "0": 0x1D,
    "'": 0x27,
    ";": 0x29,
    "\\": 0x2A,
    ",": 0x2B,
    "/": 0x2C,
    ".": 0x2F,
    "`": 0x32,
    "-": 0x1B,
    "=": 0x18,
    "[": 0x21,
    "]": 0x1E,
    "space": 0x31,
    "return": 0x24,
    "tab": 0x30,
    "escape": 0x35,
}

# CGEventFlags for modifier keys
_MACOS_MODIFIER_FLAGS = {
    "super": 0x100000,  # kCGEventFlagMaskCommand
    "shift": 0x020000,  # kCGEventFlagMaskShift
    "ctrl": 0x040000,  # kCGEventFlagMaskControl
    "alt": 0x080000,  # kCGEventFlagMaskAlternate
}


def hotkey_to_cg_values(hotkey_str: str) -> tuple[int, int]:
    """Convert a hotkey string to (CGKeyCode, CGEventFlags).

    Used by the install script to bake hotkey values into the
    native launcher at compile time.
    """
    modifiers, key = parse_hotkey(hotkey_str)
    keycode = _MACOS_KEYCODES.get(key)
    if keycode is None:
        raise ValueError(f"No macOS keycode mapping for key: {key!r}")
    modflags = 0
    for mod in modifiers:
        flag = _MACOS_MODIFIER_FLAGS.get(mod)
        if flag is None:
            raise ValueError(f"Unknown modifier: {mod!r}")
        modflags |= flag
    return keycode, modflags
