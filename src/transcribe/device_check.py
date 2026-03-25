import logging
import platform
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_alsa_card_number(source_name: str) -> str | None:
    """Get the ALSA card number for a PulseAudio/PipeWire source.

    Runs ``pactl list sources`` and searches for the source by name,
    then extracts the ``alsa.card`` property value.
    """
    try:
        result = subprocess.run(
            ["pactl", "list", "sources"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    # Find the block for this source and extract alsa.card
    in_source = False
    for line in result.stdout.splitlines():
        if f"Name: {source_name}" in line:
            in_source = True
            continue
        if in_source:
            # A new source block starts with "Source #"
            if line.strip().startswith("Source #"):
                break
            match = re.search(r'alsa\.card\s*=\s*"(\d+)"', line)
            if match:
                return match.group(1)
    return None


def _get_usb_device_status(card_number: str) -> str | None:
    """Check the USB runtime power status for an ALSA card.

    Follows ``/sys/class/sound/cardN/device`` to find the
    underlying hardware device. If the device is on a USB bus,
    reads the USB device's ``power/runtime_status``.

    Returns the status string (e.g. ``"active"``, ``"error"``,
    ``"suspended"``) or ``None`` if the device is not USB or
    the sysfs path cannot be read.
    """
    device_link = Path(f"/sys/class/sound/card{card_number}/device")
    if not device_link.exists():
        return None
    real_path = device_link.resolve()
    # Check if this is a USB device by looking for "usb" in the
    # resolved sysfs path
    if "/usb" not in str(real_path):
        return None
    # The real_path points to the USB interface (e.g. 9-2:1.0).
    # The USB device status is on the parent (e.g. 9-2).
    status_path = real_path.parent / "power" / "runtime_status"
    try:
        return status_path.read_text().strip()
    except OSError:
        return None


def check_default_input_device() -> tuple[bool, str]:
    """Check whether the default input device is healthy.

    On Linux, queries PulseAudio/PipeWire for the default source,
    finds the underlying USB device (if any), and checks its
    ``power/runtime_status`` in sysfs.

    Returns ``(True, "")`` if the device looks OK or if the check
    is not applicable (non-Linux, non-USB device, tools unavailable).
    Returns ``(False, message)`` if the device is in an error state.
    """
    if platform.system() != "Linux":
        return True, ""

    # Get default source name
    try:
        result = subprocess.run(
            ["pactl", "get-default-source"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        logger.debug("pactl not available, skipping device check")
        return True, ""
    if result.returncode != 0:
        return True, ""
    source_name = result.stdout.strip()
    if not source_name:
        return True, ""

    card_number = _get_alsa_card_number(source_name)
    if card_number is None:
        return True, ""

    status = _get_usb_device_status(card_number)
    if status is None:
        return True, ""

    if status == "error":
        msg = (
            f"USB audio device (ALSA card {card_number}) is in "
            f"error state. Try unplugging and reconnecting the "
            f"device."
        )
        logger.error(msg)
        return False, msg

    return True, ""
