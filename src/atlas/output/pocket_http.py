"""Cancellable, bounded HTTP/1.1 WAV reader for ATLAS's local Pocket TTS.

The caller owns a TCP socket to 127.0.0.1, with no proxy or redirect support.
There is no contact with external TTS services and no voice-profile upload.
"""
from __future__ import annotations

import socket
import time
from urllib.parse import urlencode


class PocketHttpCancelled(Exception):
    """The owning speech request was interrupted."""


class PocketHttpError(Exception):
    """The local server returned an invalid or incomplete HTTP response."""


class _Reader:
    def __init__(self, sock, cancelled, *, timeout=90.0):
        self.sock = sock
        self.cancelled = cancelled
        self.buffer = bytearray()
        self.deadline = time.monotonic() + timeout

    def _check(self):
        if self.cancelled():
            raise PocketHttpCancelled()
        if time.monotonic() > self.deadline:
            raise TimeoutError("local TTS response deadline exceeded")

    def _receive(self):
        # No indefinite HTTPResponse.readline/read1: a 200ms socket poll also
        # works on Windows, where closing another thread's Winsock socket may
        # not immediately wake a blocked buffered reader.
        while True:
            self._check()
            try:
                fragment = self.sock.recv(8192)
            except socket.timeout:
                continue
            self._check()
            if not fragment:
                return False
            self.buffer.extend(fragment)
            return True

    def until(self, marker, limit):
        while True:
            self._check()
            end = self.buffer.find(marker)
            if end >= 0:
                if end > limit:
                    raise PocketHttpError("oversized header")
                result = bytes(self.buffer[:end])
                del self.buffer[:end + len(marker)]
                return result
            if len(self.buffer) > limit + len(marker):
                raise PocketHttpError("oversized header")
            if not self._receive():
                raise PocketHttpError("incomplete response")

    def exact(self, length):
        if length < 0:
            raise PocketHttpError("negative body size")
        while len(self.buffer) < length:
            self._check()
            if not self._receive():
                raise PocketHttpError("truncated body")
        self._check()
        result = bytes(self.buffer[:length])
        del self.buffer[:length]
        return result

    def to_close(self, max_bytes):
        result = bytearray()
        while True:
            self._check()
            if self.buffer:
                result.extend(self.buffer)
                self.buffer.clear()
                if len(result) > max_bytes:
                    raise PocketHttpError("body too large")
            if not self._receive():
                return bytes(result)


def read_local_wav(sock, *, cancelled, max_bytes):
    """Read finite or chunked WAV, with bounded polling during generation."""
    sock.settimeout(0.2)
    reader = _Reader(sock, cancelled)
    status_and_headers = reader.until(b"\r\n\r\n", 16384)
    lines = status_and_headers.split(b"\r\n")
    status_line = lines[0].split(b" ", 2)
    if (len(status_line) < 2 or
            status_line[0] not in (b"HTTP/1.1", b"HTTP/1.0") or
            status_line[1] != b"200"):
        raise PocketHttpError("unexpected local HTTP status")
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(b":")
        if not sep:
            raise PocketHttpError("malformed response header")
        name = name.strip().lower()
        if not name or name in headers:
            raise PocketHttpError("ambiguous response header")
        headers[name] = value.strip().lower()
    if headers.get(b"content-type", b"").split(b";", 1)[0].strip() != b"audio/wav":
        raise PocketHttpError("unexpected response content type")
    if (b"content-encoding" in headers and
            headers[b"content-encoding"] != b"identity"):
        raise PocketHttpError("encoded response not supported")

    transfer = headers.get(b"transfer-encoding")
    declared = headers.get(b"content-length")
    if transfer is not None:
        if transfer != b"chunked" or declared is not None:
            raise PocketHttpError("ambiguous chunk framing")
        result = bytearray()
        while True:
            size_text = reader.until(b"\r\n", 256).split(b";", 1)[0].strip()
            if not size_text or any(c not in b"0123456789abcdef" for c in size_text):
                raise PocketHttpError("invalid chunk size")
            chunk_size = int(size_text, 16)
            if chunk_size > max_bytes - len(result):
                raise PocketHttpError("body too large")
            if chunk_size == 0:
                while reader.until(b"\r\n", 16384):
                    pass
                reader._check()
                return bytes(result)
            result.extend(reader.exact(chunk_size))
            if reader.exact(2) != b"\r\n":
                raise PocketHttpError("invalid chunk terminator")
    if declared is not None:
        if not declared.isdigit():
            raise PocketHttpError("invalid content length")
        size = int(declared)
        if size > max_bytes:
            raise PocketHttpError("body too large")
        return reader.exact(size)
    # Without a length, the server must promise connection close.
    if status_line[0] != b"HTTP/1.0" and headers.get(b"connection") != b"close":
        raise PocketHttpError("unframed HTTP body")
    return reader.to_close(max_bytes)


def make_local_request(text):
    """Send *only* text on loopback; the private voice stays in the child."""
    body = urlencode({"text": text}).encode("utf-8")
    return (b"POST /tts HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"Connection: close\r\nContent-Length: "
            + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
