"""Keep PortAudio's view of the audio devices current.

sounddevice initialises PortAudio once, at import time, and
PortAudio snapshots the device list and the default devices at
that moment. Devices that appear later (a Bluetooth headset
connected after launch) are invisible until PortAudio is
re-initialised, so beeps and recordings silently stick to the
devices that existed at start-up.
"""

import logging

logger = logging.getLogger(__name__)


def refresh_devices() -> None:
    """Re-scan the audio devices so the defaults match the system's.

    Safe to call when sounddevice is not installed (client-mode
    installs) and never raises: a failure here must not stop a
    recording from starting.
    """
    # Lazy import: client-mode installs have no sounddevice.
    try:
        import sounddevice as sd
    except ImportError:
        return
    try:
        # Close any beep still sounding so PortAudio is not torn down
        # under an open stream. Callers hold the recorder closed.
        sd.stop()
        sd._terminate()
        sd._initialize()
    except Exception as exc:
        logger.warning("Audio device re-scan failed: %s", exc)
