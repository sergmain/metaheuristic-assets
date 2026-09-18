# This payload's copy of the loopback handshake, against a real single-shot peer on 127.0.0.1:0.

import socket
import struct
import threading

import pytest

import mh_secret_client as sdk


def serve_once(expected_code, key_bytes):
    """The Processor's end of one handshake: the key only for the right check-code, a silent close otherwise."""
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)

    def recv_exactly(conn, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise OSError('EOF')
            buf.extend(chunk)
        return bytes(buf)

    def serve():
        try:
            conn, _ = server.accept()
            with conn:
                length = struct.unpack('>I', recv_exactly(conn, 4))[0]
                if recv_exactly(conn, length).decode('utf-8') == expected_code:
                    conn.sendall(struct.pack('>I', len(key_bytes)) + key_bytes)
        except OSError:
            pass
        finally:
            server.close()

    threading.Thread(target=serve, daemon=True).start()
    return server.getsockname()[1]


def test_exchange_returns_the_key_for_the_right_check_code():
    key = sdk.exchange(serve_once('code-A', b'admin:secret'), 'code-A')

    assert bytes(key) == b'admin:secret'
    assert isinstance(key, bytearray)


def test_exchange_fails_for_a_rejected_check_code():
    with pytest.raises(OSError, match='0667.060'):
        sdk.exchange(serve_once('code-A', b'never-sent'), 'code-B')
