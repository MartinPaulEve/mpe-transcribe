import pytest

from transcribe.config import (
    DEFAULT_HOTKEY,
    DEFAULT_MODEL,
    load_config,
    parse_hotkey,
)


class TestParseHotkey:
    def test_ctrl_shift_semicolon(self):
        mods, key = parse_hotkey("ctrl+shift+;")
        assert mods == {"ctrl", "shift"}
        assert key == ";"

    def test_alt_shift_space(self):
        mods, key = parse_hotkey("alt+shift+space")
        assert mods == {"alt", "shift"}
        assert key == "space"

    def test_super_ctrl_a(self):
        mods, key = parse_hotkey("super+ctrl+a")
        assert mods == {"super", "ctrl"}
        assert key == "a"

    def test_single_modifier(self):
        mods, key = parse_hotkey("ctrl+f12")
        assert mods == {"ctrl"}
        assert key == "f12"

    def test_case_insensitive(self):
        mods, key = parse_hotkey("Ctrl+Shift+;")
        assert mods == {"ctrl", "shift"}
        assert key == ";"

    def test_no_key_raises(self):
        with pytest.raises(ValueError, match="No key found"):
            parse_hotkey("ctrl+shift")

    def test_no_modifiers_raises(self):
        with pytest.raises(ValueError, match="No modifiers found"):
            parse_hotkey(";")


class TestLoadConfig:
    def test_returns_defaults_when_no_section(self):
        config = load_config()
        assert "model" in config
        assert "hotkey" in config

    def test_defaults_are_correct(self):
        assert DEFAULT_MODEL == "nvidia/parakeet-tdt-0.6b-v3"
        assert DEFAULT_HOTKEY == "ctrl+shift+;"
