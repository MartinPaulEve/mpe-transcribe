import tomllib
from pathlib import Path

DEFAULT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
DEFAULT_HOTKEY = "ctrl+shift+;"


def load_config() -> dict:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.exists():
        return {"model": DEFAULT_MODEL, "hotkey": DEFAULT_HOTKEY}
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    section = data.get("tool", {}).get("transcribe", {})
    return {
        "model": section.get("model", DEFAULT_MODEL),
        "hotkey": section.get("hotkey", DEFAULT_HOTKEY),
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
