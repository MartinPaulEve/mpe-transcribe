from pathlib import Path
from unittest.mock import MagicMock, patch

from transcribe.device_check import check_default_input_device


class TestCheckDefaultInputDevice:
    """Tests for Linux USB audio device health check."""

    @patch("transcribe.device_check.platform.system", return_value="Darwin")
    def test_skips_on_macos(self, mock_system):
        ok, msg = check_default_input_device()
        assert ok is True
        assert msg == ""

    @patch("transcribe.device_check.platform.system", return_value="Windows")
    def test_skips_on_windows(self, mock_system):
        ok, msg = check_default_input_device()
        assert ok is True
        assert msg == ""

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    def test_ok_when_pactl_not_available(self, mock_run, mock_system):
        mock_run.side_effect = FileNotFoundError("pactl not found")
        ok, msg = check_default_input_device()
        assert ok is True

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    def test_ok_when_pactl_fails(self, mock_run, mock_system):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        ok, msg = check_default_input_device()
        assert ok is True

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    @patch("transcribe.device_check.Path.resolve")
    @patch("transcribe.device_check.Path.exists")
    def test_ok_when_device_is_not_usb(
        self, mock_exists, mock_resolve, mock_run, mock_system
    ):
        # pactl returns a source name
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="alsa_input.pci-0000_00_1f.3.analog-stereo\n",
        )
        # /sys/class/sound/card0/device exists
        mock_exists.return_value = True
        # resolves to a PCI path (not USB)
        mock_resolve.return_value = Path(
            "/sys/devices/pci0000:00/0000:00:1f.3"
        )
        ok, msg = check_default_input_device()
        assert ok is True

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    @patch("transcribe.device_check._get_alsa_card_number")
    @patch("transcribe.device_check._get_usb_device_status")
    def test_ok_when_usb_device_active(
        self, mock_status, mock_card, mock_run, mock_system
    ):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="alsa_input.usb-MyMic-00.analog-stereo\n",
        )
        mock_card.return_value = "2"
        mock_status.return_value = "active"
        ok, msg = check_default_input_device()
        assert ok is True
        assert msg == ""

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    @patch("transcribe.device_check._get_alsa_card_number")
    @patch("transcribe.device_check._get_usb_device_status")
    def test_fails_when_usb_device_in_error(
        self, mock_status, mock_card, mock_run, mock_system
    ):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="alsa_input.usb-MyMic-00.analog-stereo\n",
        )
        mock_card.return_value = "2"
        mock_status.return_value = "error"
        ok, msg = check_default_input_device()
        assert ok is False
        assert "error" in msg.lower()
        assert "usb" in msg.lower() or "device" in msg.lower()

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    @patch("transcribe.device_check._get_alsa_card_number")
    @patch("transcribe.device_check._get_usb_device_status")
    def test_ok_when_usb_device_suspended(
        self, mock_status, mock_card, mock_run, mock_system
    ):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="alsa_input.usb-MyMic-00.analog-stereo\n",
        )
        mock_card.return_value = "2"
        mock_status.return_value = "suspended"
        ok, msg = check_default_input_device()
        assert ok is True

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    @patch("transcribe.device_check._get_alsa_card_number")
    def test_ok_when_card_number_not_found(
        self, mock_card, mock_run, mock_system
    ):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="alsa_input.usb-MyMic-00.analog-stereo\n",
        )
        mock_card.return_value = None
        ok, msg = check_default_input_device()
        assert ok is True

    @patch("transcribe.device_check.platform.system", return_value="Linux")
    @patch("transcribe.device_check.subprocess.run")
    @patch("transcribe.device_check._get_alsa_card_number")
    @patch("transcribe.device_check._get_usb_device_status")
    def test_ok_when_status_unreadable(
        self, mock_status, mock_card, mock_run, mock_system
    ):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="alsa_input.usb-MyMic-00.analog-stereo\n",
        )
        mock_card.return_value = "2"
        mock_status.return_value = None
        ok, msg = check_default_input_device()
        assert ok is True


class TestGetAlsaCardNumber:
    @patch("transcribe.device_check.subprocess.run")
    def test_extracts_card_number(self, mock_run):
        from transcribe.device_check import _get_alsa_card_number

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "Source #59\n"
                "\tName: alsa_input.usb-M-Audio_M-Track_2X2M"
                "-00.iec958-stereo\n"
                "\tDescription: M-Track 2X2M\n"
                '\t\talsa.card = "1"\n'
                '\t\talsa.card_name = "M-Track 2X2M"\n'
            ),
        )
        result = _get_alsa_card_number(
            "alsa_input.usb-M-Audio_M-Track_2X2M-00.iec958-stereo"
        )
        assert result == "1"

    @patch("transcribe.device_check.subprocess.run")
    def test_returns_none_when_not_found(self, mock_run):
        from transcribe.device_check import _get_alsa_card_number

        mock_run.return_value = MagicMock(
            returncode=0, stdout="no matching source\n"
        )
        result = _get_alsa_card_number("nonexistent_source")
        assert result is None

    @patch("transcribe.device_check.subprocess.run")
    def test_returns_none_on_pactl_failure(self, mock_run):
        from transcribe.device_check import _get_alsa_card_number

        mock_run.side_effect = FileNotFoundError
        result = _get_alsa_card_number("anything")
        assert result is None


class TestGetUsbDeviceStatus:
    def test_returns_status_for_usb_device(self):
        from transcribe.device_check import _get_usb_device_status

        with (
            patch(
                "transcribe.device_check.Path.exists",
                return_value=True,
            ),
            patch(
                "transcribe.device_check.Path.resolve",
                return_value=Path(
                    "/sys/devices/pci0000:00/0000:00:08.1"
                    "/0000:79:00.4/usb9/9-2/9-2:1.0"
                ),
            ),
            patch(
                "transcribe.device_check.Path.read_text",
                return_value="error\n",
            ),
        ):
            result = _get_usb_device_status("1")
            assert result == "error"

    def test_returns_none_for_non_usb_device(self):
        from transcribe.device_check import _get_usb_device_status

        with (
            patch(
                "transcribe.device_check.Path.exists",
                return_value=True,
            ),
            patch(
                "transcribe.device_check.Path.resolve",
                return_value=Path("/sys/devices/pci0000:00/0000:00:1f.3"),
            ),
        ):
            result = _get_usb_device_status("0")
            assert result is None

    def test_returns_none_when_sysfs_path_missing(self):
        from transcribe.device_check import _get_usb_device_status

        with patch(
            "transcribe.device_check.Path.exists",
            return_value=False,
        ):
            result = _get_usb_device_status("99")
            assert result is None
