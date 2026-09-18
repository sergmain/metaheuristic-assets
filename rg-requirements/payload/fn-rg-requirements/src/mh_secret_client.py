# Client side of the Processor's loopback secret handoff.
#
# The same stdlib-only port that rg-temp-project carries - of the reference client
# java/call-cc-func/python/mh_secret_client.py in the doc-processing-angular repo. Each payload is copied onto a
# Processor on its own, so each carries its own copy. The wire format is VAULT-SECRET-HANDOFF-PROTOCOL.md:
# connect to 127.0.0.1:task.secretPort, send [4-byte big-endian length][checkCode], read [4-byte big-endian
# length][key], close.

import socket
import struct

# Hard cap on the key frame the Processor is allowed to send.
MAX_KEY_FRAME_BYTES = 65_536

# Connect / read timeout for the loopback handshake, in seconds. The Processor's accept() waits 10.
DEFAULT_CONNECT_TIMEOUT = 5.0


def extract_secret_fields(params):
    """(secretPort, checkCode) from a parsed params document, or (None, None) when there is no handoff."""
    if not params:
        return (None, None)
    task = params.get('task')
    if not task:
        return (None, None)
    port = task.get('secretPort')
    code = task.get('checkCode')
    if port is None or code is None or (isinstance(code, str) and not code.strip()):
        return (None, None)
    return (port, code)


def exchange(port, check_code, timeout=DEFAULT_CONNECT_TIMEOUT):
    """One handshake. Returns the key as a bytearray - mutable, so the caller can zero it."""
    code_bytes = check_code.encode('utf-8')
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(struct.pack('>I', len(code_bytes)))
        sock.sendall(code_bytes)
        length = struct.unpack('>I', _read_exactly(sock, 4))[0]
        if length > MAX_KEY_FRAME_BYTES:
            raise IOError('0667.040 invalid key frame length: ' + str(length))
        return _read_exactly(sock, length)


def _read_exactly(sock, n):
    """Exactly n bytes from sock, as a bytearray. A close before that means the Processor rejected the check-code."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise IOError('0667.060 unexpected EOF reading frame')
        buf.extend(chunk)
    return buf


def zero(buf):
    """Overwrite a key buffer in place."""
    for i in range(len(buf)):
        buf[i] = 0
