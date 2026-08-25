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
    def test_returns_defaults_when_no_files(self, tmp_path):
        config = load_config(root=tmp_path)
        assert "model" in config
        assert "hotkey" in config
        assert config["replacements"] == {}
        assert config["custom_terms"] == []
        assert config["custom_terms_threshold"] == 0.8
        assert config["network"]["mode"] == "standalone"

    def test_reads_transcribe_toml(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            'model = "nvidia/parakeet-rnnt-1.1b"\nhotkey = "alt+shift+space"\n'
        )
        config = load_config(root=tmp_path)
        assert config["model"] == "nvidia/parakeet-rnnt-1.1b"
        assert config["hotkey"] == "alt+shift+space"

    def test_transcribe_toml_network_section(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[network]\n"
            'mode = "client"\n'
            'server_host = "10.211.55.2"\n'
            'client_label = "nixos-vm"\n'
        )
        config = load_config(root=tmp_path)
        assert config["network"]["mode"] == "client"
        assert config["network"]["server_host"] == "10.211.55.2"
        assert config["network"]["client_label"] == "nixos-vm"
        assert config["network"]["server_port"] == 47800

    def test_transcribe_toml_replacements_and_terms(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[replacements]\n"
            'comet = "commit"\n'
            "[custom_terms]\n"
            'terms = ["Birkbeck"]\n'
            "threshold = 0.9\n"
        )
        config = load_config(root=tmp_path)
        assert config["replacements"] == {"comet": "commit"}
        assert config["custom_terms"] == ["Birkbeck"]
        assert config["custom_terms_threshold"] == 0.9

    def test_falls_back_to_pyproject_tool_section(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.transcribe]\n"
            'hotkey = "ctrl+alt+t"\n'
            "[tool.transcribe.network]\n"
            'mode = "host"\n'
        )
        config = load_config(root=tmp_path)
        assert config["hotkey"] == "ctrl+alt+t"
        assert config["network"]["mode"] == "host"

    def test_notifications_default_all_on(self, tmp_path):
        config = load_config(root=tmp_path)
        assert config["notifications"]["visual"] is True
        assert config["notifications"]["sound"] is True

    def test_notifications_section_disables_channels(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[notifications]\nvisual = false\nsound = false\n"
        )
        config = load_config(root=tmp_path)
        assert config["notifications"]["visual"] is False
        assert config["notifications"]["sound"] is False

    def test_notifications_partial_section(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[notifications]\nsound = false\n"
        )
        config = load_config(root=tmp_path)
        assert config["notifications"]["visual"] is True
        assert config["notifications"]["sound"] is False

    def test_notifications_events_default_all_on(self, tmp_path):
        config = load_config(root=tmp_path)
        assert config["notifications"]["events"] == {
            "ready": True,
            "recording": True,
            "stopped": True,
            "pasted": True,
            "error": True,
        }

    def test_notifications_events_section_disables_events(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[notifications.events]\nrecording = false\npasted = false\n"
        )
        config = load_config(root=tmp_path)
        events = config["notifications"]["events"]
        assert events["recording"] is False
        assert events["pasted"] is False
        assert events["ready"] is True
        assert events["stopped"] is True
        assert events["error"] is True

    def test_notifications_events_compose_with_masters(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[notifications]\n"
            "sound = false\n"
            "[notifications.events]\n"
            "ready = false\n"
        )
        config = load_config(root=tmp_path)
        assert config["notifications"]["visual"] is True
        assert config["notifications"]["sound"] is False
        assert config["notifications"]["events"]["ready"] is False
        assert config["notifications"]["events"]["error"] is True

    def test_unknown_key_in_notifications_events_raises(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[notifications.events]\npasetd = false\n"
        )
        with pytest.raises(ConfigError, match="pasetd"):
            load_config(root=tmp_path)

    def test_paste_method_defaults_to_ctrl_v(self, tmp_path):
        config = load_config(root=tmp_path)
        assert config["paste_method"] == "ctrl+v"

    def test_paste_method_type_accepted(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text('paste_method = "type"\n')
        config = load_config(root=tmp_path)
        assert config["paste_method"] == "type"

    def test_paste_method_invalid_raises(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            'paste_method = "telepathy"\n'
        )
        with pytest.raises(ConfigError, match="paste_method"):
            load_config(root=tmp_path)

    def test_unknown_top_level_key_raises(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text('paste_metod = "type"\n')
        with pytest.raises(ConfigError, match="paste_metod"):
            load_config(root=tmp_path)

    def test_misplaced_key_in_custom_terms_raises(self, tmp_path):
        # A top-level key written below a [section] header lands in
        # that section; it must fail loudly, not silently no-op.
        (tmp_path / "transcribe.toml").write_text(
            '[custom_terms]\nterms = ["x"]\npaste_method = "type"\n'
        )
        with pytest.raises(ConfigError, match="paste_method"):
            load_config(root=tmp_path)

    def test_misplaced_key_in_notifications_raises(self, tmp_path):
        (tmp_path / "transcribe.toml").write_text(
            "[notifications]\nsound = false\nhotkey = false\n"
        )
        with pytest.raises(ConfigError, match="hotkey"):
            load_config(root=tmp_path)

    def test_transcribe_toml_wins_over_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.transcribe]\n"
            'hotkey = "ctrl+alt+t"\n'
            "[tool.transcribe.network]\n"
            'mode = "host"\n'
        )
        (tmp_path / "transcribe.toml").write_text('hotkey = "super+shift+z"\n')
        config = load_config(root=tmp_path)
        assert config["hotkey"] == "super+shift+z"
        # transcribe.toml replaces the pyproject section entirely
        assert config["network"]["mode"] == "standalone"

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

    def test_load_config_includes_network(self, tmp_path):
        config = load_config(root=tmp_path)
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
