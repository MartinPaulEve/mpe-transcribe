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
