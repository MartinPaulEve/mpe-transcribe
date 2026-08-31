import socket

import pytest

from transcribe.net.transport import UdpTransport


class TestUdpTransport:
    def test_second_bind_to_same_port_raises(self):
        first = UdpTransport(("127.0.0.1", 0), timeout=0.05)
        try:
            with pytest.raises(OSError):
                UdpTransport(("127.0.0.1", first.local_port), timeout=0.05)
        finally:
            first.close()

    def test_bound_socket_is_exclusive(self):
        # SO_REUSEADDR on macOS lets a second UDP host silently share
        # the port, with datagrams delivered unpredictably between
        # them; the bind must be exclusive so a duplicate instance
        # fails loudly instead.
        transport = UdpTransport(("127.0.0.1", 0), timeout=0.05)
        try:
            reuse = transport._sock.getsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR
            )
            assert reuse == 0
        finally:
            transport.close()

    def test_loopback_round_trip(self):
        receiver = UdpTransport(("127.0.0.1", 0), timeout=1.0)
        sender = UdpTransport(("127.0.0.1", 0), timeout=0.05)
        try:
            dest = ("127.0.0.1", receiver.local_port)
            sender.sendto(b"ping", dest)
            result = receiver.recvfrom()
            assert result is not None
            data, addr = result
            assert data == b"ping"
            assert addr[0] == "127.0.0.1"
            assert addr[1] == sender.local_port
        finally:
            receiver.close()
            sender.close()

    def test_recvfrom_returns_none_on_timeout(self):
        transport = UdpTransport(("127.0.0.1", 0), timeout=0.05)
        try:
            assert transport.recvfrom() is None
        finally:
            transport.close()

    def test_unbound_transport_can_send(self):
        receiver = UdpTransport(("127.0.0.1", 0), timeout=1.0)
        sender = UdpTransport(timeout=0.05)
        try:
            sender.sendto(b"hi", ("127.0.0.1", receiver.local_port))
            result = receiver.recvfrom()
            assert result is not None
            assert result[0] == b"hi"
        finally:
            receiver.close()
            sender.close()
