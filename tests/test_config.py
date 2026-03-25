from unittest.mock import patch

import pytest

from transcribe.config import (
    DEFAULT_HOTKEY,
    DEFAULT_HOTKEY_MACOS,
    DEFAULT_MODEL,
    DEFAULT_MODEL_MACOS,
    hotkey_to_cg_values,
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

    def test_macos_defaults_are_correct(self):
        assert DEFAULT_MODEL_MACOS == ("mlx-community/whisper-large-v3-turbo")
        assert DEFAULT_HOTKEY_MACOS == "super+shift+'"

    @patch("transcribe.config.platform.system", return_value="Darwin")
    def test_macos_default_model(self, mock_system):
        from transcribe.config import _default_hotkey, _default_model

        assert _default_model() == DEFAULT_MODEL_MACOS
        assert _default_hotkey() == DEFAULT_HOTKEY_MACOS

    @patch("transcribe.config.platform.system", return_value="Linux")
    def test_linux_default_model(self, mock_system):
        from transcribe.config import _default_hotkey, _default_model

        assert _default_model() == DEFAULT_MODEL
        assert _default_hotkey() == DEFAULT_HOTKEY

    @patch("transcribe.config.platform.system", return_value="Windows")
    def test_windows_default_model(self, mock_system):
        from transcribe.config import _default_hotkey, _default_model

        assert _default_model() == DEFAULT_MODEL
        assert _default_hotkey() == DEFAULT_HOTKEY


class TestHotkeyToCgValues:
    def test_super_shift_quote(self):
        keycode, modflags = hotkey_to_cg_values("super+shift+'")
        assert keycode == 0x27  # kVK_ANSI_Quote
        assert modflags == 0x120000  # Cmd+Shift

    def test_ctrl_shift_semicolon(self):
        keycode, modflags = hotkey_to_cg_values("ctrl+shift+;")
        assert keycode == 0x29  # kVK_ANSI_Semicolon
        assert modflags == 0x060000  # Ctrl+Shift

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="No macOS keycode"):
            hotkey_to_cg_values("ctrl+shift+f12")
