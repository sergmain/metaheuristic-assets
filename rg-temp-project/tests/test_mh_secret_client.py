# The loopback handshake against a real peer: a single-shot server on 127.0.0.1:0, written to
# VAULT-SECRET-HANDOFF-PROTOCOL.md, that sends the key only when the check-code it reads matches.
# Nothing is patched - the socket is the real network stack, small and disposable, the way tmp_path is
# the real filesystem.

import socket
import struct
import threading

import pytest

import mh_secret_client as sdk


class FakeProcessor:
    """The Processor's end of one handshake: read a framed check-code; on a mismatch close without a
    word; on a match send the framed key. With oversize_reply it announces a key frame larger than any
    client may accept."""

    def __init__(self, expected_code, key_bytes, oversize_reply=False):
        self.expected_code = expected_code
        self.key_bytes = key_bytes
        self.oversize_reply = oversize_reply
        self.server = socket.socket()
        self.server.bind(('127.0.0.1', 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.server.accept()
            with conn:
                conn.settimeout(2.0)
                length = struct.unpack('>I', self._recv_exactly(conn, 4))[0]
                code = self._recv_exactly(conn, length).decode('utf-8')
                if code != self.expected_code:
                    return
                if self.oversize_reply:
                    conn.sendall(struct.pack('>I', sdk.MAX_KEY_FRAME_BYTES + 1))
                    return
                conn.sendall(struct.pack('>I', len(self.key_bytes)))
                conn.sendall(self.key_bytes)
        except OSError:
            pass
        finally:
            self.server.close()

    @staticmethod
    def _recv_exactly(sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise OSError('EOF')
            buf.extend(chunk)
        return bytes(buf)

    def join(self):
        self.thread.join(2.0)


def test_exchange_returns_the_key_when_the_check_code_matches():
    proc = FakeProcessor('check-code-AAAA', b'admin:secret')

    key = sdk.exchange(proc.port, 'check-code-AAAA')
    proc.join()

    assert bytes(key) == b'admin:secret'
    assert isinstance(key, bytearray)          # mutable, so it can be zeroed


def test_exchange_fails_when_the_processor_rejects_the_check_code():
    proc = FakeProcessor('check-code-AAAA', b'never-sent')

    with pytest.raises(OSError, match='0667.060'):
        sdk.exchange(proc.port, 'check-code-BBBB')
    proc.join()


def test_exchange_refuses_an_oversized_key_frame():
    proc = FakeProcessor('anycode', b'never-sent', oversize_reply=True)

    with pytest.raises(OSError, match='0667.040'):
        sdk.exchange(proc.port, 'anycode')
    proc.join()


@pytest.mark.parametrize('params', [
    None,
    {},
    {'task': None},
    {'task': {'checkCode': 'abc'}},
    {'task': {'secretPort': 12345}},
    {'task': {'secretPort': 1, 'checkCode': '  '}},
])
def test_extract_secret_fields_is_no_handoff_unless_both_fields_are_there(params):
    assert sdk.extract_secret_fields(params) == (None, None)


def test_extract_secret_fields_returns_the_pair():
    assert sdk.extract_secret_fields({'task': {'secretPort': 12345, 'checkCode': 'abc'}}) == (12345, 'abc')


def test_zero_overwrites_every_byte():
    buf = bytearray(b'admin:secret')

    sdk.zero(buf)

    assert buf == bytearray(12)
