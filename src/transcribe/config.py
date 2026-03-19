import platform
import tomllib
from pathlib import Path

DEFAULT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
DEFAULT_HOTKEY = "ctrl+shift+;"

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


def load_config() -> dict:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    model_default = _default_model()
    hotkey_default = _default_hotkey()
    if not pyproject.exists():
        return {"model": model_default, "hotkey": hotkey_default}
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    section = data.get("tool", {}).get("transcribe", {})
    return {
        "model": section.get("model", model_default),
        "hotkey": section.get("hotkey", hotkey_default),
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
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04,
    "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09,
    "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "o": 0x1F, "u": 0x20, "i": 0x22,
    "p": 0x23, "l": 0x25, "j": 0x26, "k": 0x28, "n": 0x2D,
    "m": 0x2E,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17,
    "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19, "0": 0x1D,
    "'": 0x27, ";": 0x29, "\\": 0x2A, ",": 0x2B, "/": 0x2C,
    ".": 0x2F, "`": 0x32, "-": 0x1B, "=": 0x18,
    "[": 0x21, "]": 0x1E,
    "space": 0x31, "return": 0x24, "tab": 0x30, "escape": 0x35,
}

# CGEventFlags for modifier keys
_MACOS_MODIFIER_FLAGS = {
    "super": 0x100000,  # kCGEventFlagMaskCommand
    "shift": 0x020000,  # kCGEventFlagMaskShift
    "ctrl":  0x040000,  # kCGEventFlagMaskControl
    "alt":   0x080000,  # kCGEventFlagMaskAlternate
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
