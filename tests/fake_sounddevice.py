"""A fake ``sounddevice`` module with PortAudio's device semantics.

It models the two behaviours that matter to the application:

* the default device is snapshotted at ``_initialize()`` and does
  not track later changes to the system default;
* ``_terminate()`` invalidates any stream still open, and nothing
  can be played or recorded until ``_initialize()`` runs again.
"""


class FakeStream:
    def __init__(self, sd, device):
        self._sd = sd
        self.device = device
        self.closed = False

    def start(self):
        pass

    def stop(self):
        pass

    def close(self, ignore_errors=True):
        self.closed = True
        self._sd.open_streams.discard(self)


class FakeSoundDevice:
    def __init__(self, system_default="speaker"):
        # What the operating system currently routes audio to.
        self.system_default = system_default
        # PortAudio's snapshot of that, taken at initialisation.
        self.default_device = system_default
        self.initialized = True
        self.open_streams = set()
        self.killed_streams = []
        self.played_on = []
        self.opened_on = []
        self.fail_on_initialize = None
        self._last = None

    def _initialize(self):
        if self.fail_on_initialize is not None:
            raise self.fail_on_initialize
        self.default_device = self.system_default
        self.initialized = True

    def _terminate(self):
        self.killed_streams.extend(self.open_streams)
        self.open_streams.clear()
        self.initialized = False

    def _require_initialized(self):
        if not self.initialized:
            raise RuntimeError("PortAudio not initialized")

    def play(self, data, samplerate=None, **kwargs):
        self._require_initialized()
        self.stop()
        stream = FakeStream(self, self.default_device)
        self.open_streams.add(stream)
        self._last = stream
        self.played_on.append(self.default_device)

    def stop(self, ignore_errors=True):
        if self._last is not None:
            self._last.close()
            self._last = None

    def InputStream(self, **kwargs):
        self._require_initialized()
        stream = FakeStream(self, self.default_device)
        self.open_streams.add(stream)
        self.opened_on.append(self.default_device)
        return stream
