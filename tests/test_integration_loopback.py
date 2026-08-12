"""End-to-end host<->client exchange over real loopback UDP.

No threads: datagrams are pumped between the two peers manually.
Recorder/transcriber are faked at the callback level; everything
below (session logic, AEAD, chunking, ACKs, sockets) is real.
"""

from transcribe.config import NETWORK_DEFAULTS
from transcribe.net.client import Client
from transcribe.net.host import Host
from transcribe.net.transport import UdpTransport

PSK = b"\x09" * 32


def pump(transport, peer, rounds=10):
    """Deliver queued datagrams from a socket to a peer object."""
    for _ in range(rounds):
        result = transport.recvfrom()
        if result is None:
            return
        peer.handle_datagram(*result)


class TestLoopbackRoundTrip:
    def test_full_session_round_trip(self):
        host_transport = UdpTransport(("127.0.0.1", 0), timeout=0.2)
        client_transport = UdpTransport(("127.0.0.1", 0), timeout=0.2)
        try:
            network = dict(NETWORK_DEFAULTS)
            network["server_host"] = "127.0.0.1"
            network["server_port"] = host_transport.local_port
            network["client_label"] = "test-vm"

            started = []
            host = Host(
                network,
                PSK,
                host_transport,
                on_start=lambda: started.append(True),
                on_stop=lambda: None,
            )
            states = []
            texts = []
            client = Client(
                network,
                PSK,
                client_transport,
                on_state=lambda body: states.append(body["state"]),
                on_text=texts.append,
            )

            client.start()  # REGISTER
            pump(host_transport, host)

            client.trigger()  # START
            pump(host_transport, host)
            assert host.state == "recording"
            assert host.initiator == "test-vm"
            assert started == [True]
            pump(client_transport, client)  # ACK + STATE
            assert client.view == "recording"

            client.trigger()  # STOP
            pump(host_transport, host)
            assert host.state == "transcribing"

            host.publish_text("héllo from the host ✓")
            host.finish_session()
            pump(client_transport, client)
            assert texts == ["héllo from the host ✓"]
            assert client.view == "idle"
            assert "recording" in states
            assert "transcribing" in states

            # the client ACKed the TEXT chunk: no retransmit pending
            pump(host_transport, host)
            host.tick()
        finally:
            host_transport.close()
            client_transport.close()
