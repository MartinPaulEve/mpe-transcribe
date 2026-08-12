from unittest.mock import patch

import pytest

from transcribe.config import (
    DEFAULT_HOTKEY,
    DEFAULT_HOTKEY_MACOS,
    DEFAULT_MODEL,
    DEFAULT_MODEL_MACOS,
    NETWORK_DEFAULTS,
    ConfigError,
    hotkey_to_cg_values,
    load_config,
    load_network_config,
    parse_hotkey,
    resolve_psk,
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
        assert config["replacements"] == {}
        assert config["custom_terms"] == []
        assert config["custom_terms_threshold"] == 0.8

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


class TestLoadNetworkConfig:
    def test_no_section_gives_standalone_defaults(self):
        network = load_network_config(None)
        assert network["mode"] == "standalone"
        assert network == NETWORK_DEFAULTS

    def test_empty_section_gives_defaults(self):
        assert load_network_config({}) == NETWORK_DEFAULTS

    def test_section_overrides_defaults(self):
        network = load_network_config(
            {
                "mode": "client",
                "server_host": "10.211.55.2",
                "server_port": 47801,
                "client_label": "nixos-vm",
            }
        )
        assert network["mode"] == "client"
        assert network["server_host"] == "10.211.55.2"
        assert network["server_port"] == 47801
        assert network["client_label"] == "nixos-vm"
        # untouched keys keep their defaults
        assert network["bind_port"] == 47800
        assert network["deliver_to"] == "initiator"

    def test_invalid_mode_raises(self):
        with pytest.raises(ConfigError, match="mode"):
            load_network_config({"mode": "p2p"})

    def test_invalid_deliver_to_raises(self):
        with pytest.raises(ConfigError, match="deliver_to"):
            load_network_config({"deliver_to": "nobody"})

    def test_unknown_keys_raise(self):
        with pytest.raises(ConfigError, match="unknown"):
            load_network_config({"srever_host": "10.0.0.1"})

    def test_load_config_includes_network(self):
        config = load_config()
        assert config["network"]["mode"] == "standalone"


class TestResolvePsk:
    KEY = b"\x01" * 32
    KEY_B64 = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="

    def _network(self, **overrides):
        network = dict(NETWORK_DEFAULTS)
        network.update(overrides)
        return network

    def test_resolves_from_env(self):
        network = self._network()
        key = resolve_psk(network, environ={"TRANSCRIBE_PSK": self.KEY_B64})
        assert key == self.KEY

    def test_resolves_from_custom_env_name(self):
        network = self._network(key_env="MY_PSK")
        key = resolve_psk(network, environ={"MY_PSK": self.KEY_B64})
        assert key == self.KEY

    def test_resolves_from_key_file(self, tmp_path):
        key_file = tmp_path / "psk.key"
        key_file.write_text(self.KEY_B64 + "\n")
        network = self._network(key_file=str(key_file))
        assert resolve_psk(network, environ={}) == self.KEY

    def test_env_wins_over_file(self, tmp_path):
        other = "AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI="
        key_file = tmp_path / "psk.key"
        key_file.write_text(other)
        network = self._network(key_file=str(key_file))
        key = resolve_psk(network, environ={"TRANSCRIBE_PSK": self.KEY_B64})
        assert key == self.KEY

    def test_no_key_raises(self):
        with pytest.raises(ConfigError, match="key"):
            resolve_psk(self._network(), environ={})

    def test_missing_key_file_raises(self, tmp_path):
        network = self._network(key_file=str(tmp_path / "absent.key"))
        with pytest.raises(ConfigError):
            resolve_psk(network, environ={})

    def test_invalid_base64_raises(self):
        with pytest.raises(ConfigError):
            resolve_psk(
                self._network(), environ={"TRANSCRIBE_PSK": "not-base64!!"}
            )

    def test_wrong_length_key_raises(self):
        short = "AQID"  # 3 bytes
        with pytest.raises(ConfigError, match="32"):
            resolve_psk(self._network(), environ={"TRANSCRIBE_PSK": short})


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
