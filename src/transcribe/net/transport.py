"""Thin UDP socket transport behind the sendto/recvfrom seam.

Everything above this module (Host, Client) is socket-free and
tested with fakes; this is the only place a real socket lives.
"""

import socket


class UdpTransport:
    """Connectionless UDP send/receive with a poll-friendly timeout."""

    def __init__(
        self,
        bind: tuple[str, int] | None = None,
        timeout: float = 0.2,
    ):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if bind is not None:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(bind)
        self._sock.settimeout(timeout)

    @property
    def local_port(self) -> int:
        return self._sock.getsockname()[1]

    def sendto(self, data: bytes, addr) -> None:
        self._sock.sendto(data, addr)

    def recvfrom(self, bufsize: int = 4096):
        """Return (data, addr) or None on timeout."""
        try:
            return self._sock.recvfrom(bufsize)
        except TimeoutError:
            return None

    def close(self) -> None:
        self._sock.close()
