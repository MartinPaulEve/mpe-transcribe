"""Mock out system-level dependencies that may not be available in test env."""

import sys
from unittest.mock import MagicMock

# Mock sounddevice before any application code imports it
_mock_sd = MagicMock()
sys.modules["sounddevice"] = _mock_sd
sys.modules["_sounddevice"] = MagicMock()

# Mock Xlib modules with real X11 constant values so that bitmask
# arithmetic in hotkey.py works correctly at import time.
_mock_xlib = MagicMock()
_mock_xlib.X.ControlMask = 4
_mock_xlib.X.ShiftMask = 1
_mock_xlib.X.Mod1Mask = 8
_mock_xlib.X.Mod4Mask = 64
_mock_xlib.X.LockMask = 2
_mock_xlib.X.Mod2Mask = 16
_mock_xlib.X.GrabModeAsync = 1
_mock_xlib.X.KeyPress = 2
_mock_xlib.X.KeyPressMask = 1
_mock_xlib.X.NoSymbol = 0
_mock_xlib.X.NONE = 0
_mock_xlib.X.CurrentTime = 0
_mock_xlib.XK.string_to_keysym.return_value = 0
sys.modules["Xlib"] = _mock_xlib
sys.modules["Xlib.X"] = _mock_xlib.X
sys.modules["Xlib.XK"] = _mock_xlib.XK
sys.modules["Xlib.display"] = _mock_xlib.display
sys.modules["Xlib.ext"] = _mock_xlib.ext
sys.modules["Xlib.ext.record"] = _mock_xlib.ext.record

# Mock nemo modules
_mock_nemo = MagicMock()
sys.modules["nemo"] = _mock_nemo
sys.modules["nemo.collections"] = _mock_nemo.collections
sys.modules["nemo.collections.asr"] = _mock_nemo.collections.asr

# Mock soundfile
_mock_sf = MagicMock()
sys.modules["soundfile"] = _mock_sf
