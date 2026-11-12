"""Owned loopback and synthetic PCM regressions, without a private voice."""

import io
import struct
import sys
import threading
import wave
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from atlas.output.tts import PocketTTS, SpeechRequest

pytestmark = pytest.mark.unit


def pcm_wav():
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x01\x00" * 2400)
    return data.getvalue()


@contextmanager
def loopback_engine(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    engine = PocketTTS()
    engine._port = server.server_port
    engine._server = SimpleNamespace(poll=lambda: None)
    try:
        yield engine
    finally:
        engine.interrupt()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.mark.parametrize('response_kind', ['valid', 'short-body', 'oversized', 'wrong-type'])
def test_loopback_posts_only_text_and_ignores_proxy(
        owned_loopback_network, monkeypatch, response_kind):
    calls = []
    payload = pcm_wav()

    class Handler(QuietHandler):
        def do_POST(self):
            calls.append((self.path, self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain' if response_kind == 'wrong-type'
                             else 'audio/wav')
            self.send_header('Content-Length', str(len(payload) +
                                                 (2 if response_kind == 'short-body' else 0)))
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

    monkeypatch.setenv('HTTP_PROXY', 'http://192.0.2.1:9')
    monkeypatch.setenv('ALL_PROXY', 'http://192.0.2.1:9')
    monkeypatch.setenv('NO_PROXY', '')
    with loopback_engine(Handler) as engine:
        engine.voice_profile = 'private-profile-not-for-http.safetensors'
        if response_kind == 'oversized':
            engine.MAX_WAV_BYTES = len(payload) - 1
        assert engine._request_audio('Bonjour ATLAS') == (
            payload if response_kind == 'valid' else None
        )
    assert calls == [('/tts', b'text=Bonjour+ATLAS')]


def test_redirect_cannot_forward_response_text(owned_loopback_network):
    redirected = []

    class Handler(QuietHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(307)
            self.send_header('Location', '/leak')
            self.send_header('Content-Length', '0')
            self.end_headers()
            if self.path == '/leak':
                redirected.append(True)

    with loopback_engine(Handler) as engine:
        assert engine._request_audio('Private response text') is None
    assert not redirected


@pytest.mark.parametrize('stage', ['headers', 'body'])
@pytest.mark.parametrize('action', ['interrupt', 'stop'])
def test_cancel_stalled_transfer_releases_worker_promptly(
        owned_loopback_network, stage, action):
    entered = threading.Event()
    release = threading.Event()

    class Handler(QuietHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            if stage == 'body':
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Content-Length', '10000')
                self.end_headers()
                self.wfile.write(b'RIFF')
                self.wfile.flush()
            entered.set()
            release.wait(5)
            self.close_connection = True

    outcomes = []
    playback = []
    finished = threading.Event()
    def terminal(outcome):
        outcomes.append(outcome)
        finished.set()
    with loopback_engine(Handler) as engine:
        engine.set_playback_callbacks(
            lambda *args: playback.append('started'),
            lambda *args: playback.append('finished'),
        )
        # Use the real shared worker without starting a model process.
        request = SpeechRequest('Bonjour', terminal_callback=terminal)
        engine._q.put(request)
        worker = threading.Thread(target=engine._run, daemon=True)
        engine._thread = worker
        worker.start()
        try:
            assert entered.wait(2)
            if action == 'stop':
                # The loopback fixture has no subprocess to terminate.
                engine._server = None
                engine.stop()
            else:
                engine.interrupt()
            assert finished.wait(1), 'HTTP cancellation remained blocked'
            # Shared speech ownership marks active work interrupted on stop;
            # queued work is cancelled separately.
            assert outcomes == ['interrupted']
            assert not playback
        finally:
            release.set()
            engine._stop.set()
            engine._q.put(None)
            engine.interrupt()
            worker.join(timeout=2)
        assert not worker.is_alive()


@pytest.mark.parametrize('declared_size', ['truncated', 'official-stream'])
def test_wav_length_validation_handles_official_stream_header(monkeypatch, declared_size):
    import sounddevice
    import atlas.output.lip_sync as lip_sync

    payload = bytearray(pcm_wav())
    frames = 1_000_000_000 if declared_size == 'official-stream' else 4800
    struct.pack_into('<I', payload, 4, 36 + frames * 2)
    struct.pack_into('<I', payload, 40, frames * 2)
    engine = PocketTTS()
    monkeypatch.setattr(engine, '_request_audio', lambda text: bytes(payload))
    played = []

    class Stream:
        def start(self):
            played.append('start')
        def write(self, samples):
            played.append(bytes(samples))
        def stop(self):
            pass
        def close(self):
            pass

    monkeypatch.setattr(sounddevice, 'RawOutputStream', lambda **kwargs: Stream())
    monkeypatch.setattr(lip_sync, 'publish_envelope', lambda *a, **kw: None)
    monkeypatch.setattr(lip_sync, 'clear_envelope', lambda: None)
    durations = []
    request = SpeechRequest('Bonjour', duration_callback=durations.append)
    try:
        assert engine._speak_once(request) is (declared_size == 'official-stream')
        assert durations == ([0.1] if declared_size == 'official-stream' else [])
        assert bool(played) is (declared_size == 'official-stream')
    finally:
        request._finish('completed' if played else 'failed')


def test_stop_then_restart_prepares_a_fresh_server(tmp_path, monkeypatch):
    import atlas.output.tts as speech
    import requests

    binary = tmp_path / 'engine'
    profile = tmp_path / 'synthetic.safetensors'
    binary.write_bytes(b'stub')
    profile.write_bytes(b'synthetic')
    processes = []

    class Process:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, timeout):
            return 0

    def launch(*args, **kwargs):
        process = Process()
        processes.append(process)
        return process

    class Session:
        def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: {'status': 'healthy'})
        def close(self):
            pass

    monkeypatch.setattr(speech.subprocess, 'Popen', launch)
    monkeypatch.setattr(requests, 'Session', Session)
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    try:
        engine.start()
        assert engine._thread and engine._thread.is_alive()
        engine.stop()
        assert processes[0].stopped
        engine.start()
        assert engine.enabled
        assert engine._thread and engine._thread.is_alive()
        assert len(processes) == 2
    finally:
        engine.stop()
    assert all(process.stopped for process in processes)


def test_interrupt_keeps_server_available_for_next_utterance(
        owned_loopback_network, monkeypatch):
    import sounddevice
    from atlas.activity import AtlasState, get_atlas_state
    import atlas.output.lip_sync as lip_sync

    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    payload = pcm_wav()

    class Handler(QuietHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if body == b'text=first':
                entered.set()
                release.wait(5)
                self.close_connection = True
                return
            self.send_response(200)
            self.send_header('Content-Type', 'audio/wav')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    manager = get_atlas_state()
    manager.set_state(AtlasState.IDLE)
    events = []
    pcm = []

    class Stream:
        def start(self):
            assert manager.state == AtlasState.SPEAKING
        def write(self, data):
            pcm.append(bytes(data))
        def stop(self):
            pass
        def close(self):
            events.append('closed')

    monkeypatch.setattr(sounddevice, 'RawOutputStream', lambda **kw: Stream())
    monkeypatch.setattr(lip_sync, 'publish_envelope', lambda *a, **kw: None)
    monkeypatch.setattr(lip_sync, 'clear_envelope', lambda: None)
    with loopback_engine(Handler) as engine:
        server = engine._server
        engine.set_playback_callbacks(
            lambda request, duration: events.append(('started', request.text, duration)),
            lambda request, outcome: events.append(('ended', request.text, outcome)),
        )
        first = SpeechRequest('first', terminal_callback=lambda outcome: (
            events.append(('first', outcome)), finished.set(),
        ))
        second_done = threading.Event()
        second = SpeechRequest('second',
                               completion_callback=lambda: events.append('completed'),
                               terminal_callback=lambda outcome: (
                                   events.append(('second', outcome)), second_done.set(),
                               ))
        engine._q.put(first)
        worker = threading.Thread(target=engine._run, daemon=True)
        engine._thread = worker
        worker.start()
        try:
            assert entered.wait(2)
            assert not engine.is_speaking()
            assert manager.state == AtlasState.IDLE
            engine.interrupt()
            assert finished.wait(1)
            assert engine._server is server
            engine._q.put(second)
            assert second_done.wait(2)
            assert b''.join(pcm) == payload[44:]
            assert events == [
                ('first', 'interrupted'), ('started', 'second', 0.1),
                'closed', ('ended', 'second', 'completed'), 'completed',
                ('second', 'completed'),
            ]
            assert not engine.is_speaking()
            assert manager.state == AtlasState.IDLE
        finally:
            release.set()
            engine._server = None
            engine.stop()
        assert not worker.is_alive()


def test_concurrent_startup_owns_only_one_child(tmp_path, monkeypatch):
    import requests
    import atlas.output.tts as speech

    binary = tmp_path / 'engine'
    profile = tmp_path / 'synthetic.safetensors'
    binary.write_bytes(b'stub')
    profile.write_bytes(b'synthetic')
    processes = []
    health_entered = threading.Event()
    release = threading.Event()
    duplicate = threading.Event()

    class Process:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, timeout):
            return 0

    def launch(*args, **kwargs):
        process = Process()
        processes.append(process)
        if len(processes) > 1:
            duplicate.set()
        return process

    class Session:
        def get(self, *args, **kwargs):
            health_entered.set()
            assert release.wait(2)
            return SimpleNamespace(status_code=200, json=lambda: {'status': 'healthy'})
        def close(self):
            pass

    monkeypatch.setattr(speech.subprocess, 'Popen', launch)
    monkeypatch.setattr(requests, 'Session', Session)
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    threads = [threading.Thread(target=engine.start) for _ in range(2)]
    try:
        threads[0].start()
        assert health_entered.wait(1)
        threads[1].start()
        duplicate.wait(0.1)
        release.set()
        for thread in threads:
            thread.join(timeout=2)
            assert not thread.is_alive()
        assert len(processes) == 1
    finally:
        release.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=2)
        engine.stop()
    assert all(process.stopped for process in processes)


def test_unresponsive_owned_child_is_killed_and_reaped():
    import subprocess

    calls = []
    class Process:
        def poll(self):
            return None
        def terminate(self):
            calls.append('terminate')
        def wait(self, timeout):
            calls.append(('wait', timeout))
            if timeout == 2:
                raise subprocess.TimeoutExpired('synthetic child', timeout)
            return 0
        def kill(self):
            calls.append('kill')

    engine = PocketTTS()
    engine._server = Process()
    engine._port = 1234
    engine.stop()
    assert calls == ['terminate', ('wait', 2), 'kill', ('wait', 1)]
    assert engine._server is None
    assert engine._port is None


@pytest.mark.parametrize('boundary', ['prepare-entry', 'health-response'])
def test_stop_during_startup_cannot_adopt_cancelled_generation(
        tmp_path, monkeypatch, boundary):
    import requests
    import atlas.output.tts as speech

    binary = tmp_path / 'engine'
    profile = tmp_path / 'synthetic.safetensors'
    binary.write_bytes(b'stub')
    profile.write_bytes(b'synthetic')
    entered = threading.Event()
    release = threading.Event()
    processes = []

    class Process:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, timeout):
            return 0

    def launch(*args, **kwargs):
        process = Process()
        processes.append(process)
        return process

    def pause():
        entered.set()
        assert release.wait(2)

    class Session:
        def get(self, *args, **kwargs):
            if boundary == 'health-response':
                pause()
            return SimpleNamespace(status_code=200, json=lambda: {'status': 'healthy'})
        def close(self):
            pass

    monkeypatch.setattr(speech.subprocess, 'Popen', launch)
    monkeypatch.setattr(requests, 'Session', Session)
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    prepare = engine._prepare_speech
    def delayed_prepare():
        if boundary == 'prepare-entry':
            pause()
        return prepare()
    monkeypatch.setattr(engine, '_prepare_speech', delayed_prepare)
    startup = threading.Thread(target=engine.start)
    shutdown = threading.Thread(target=engine.stop)
    try:
        startup.start()
        assert entered.wait(1)
        shutdown.start()
        assert engine._stop.wait(1)
        release.set()
        startup.join(timeout=2)
        shutdown.join(timeout=2)
        assert not startup.is_alive()
        assert not shutdown.is_alive()
        assert engine._thread is None
        assert engine._server is None
        assert len(processes) == (0 if boundary == 'prepare-entry' else 1)
        assert all(process.stopped for process in processes)
    finally:
        release.set()
        startup.join(timeout=2)
        if shutdown.ident is not None:
            shutdown.join(timeout=2)
        engine.stop()


def test_owned_subprocess_starts_stops_and_restarts(tmp_path, monkeypatch):
    """Exercise native process ownership with a synthetic HTTP child, not a model."""
    from pathlib import Path
    import atlas.output.tts as speech

    profile = tmp_path / 'synthetic.safetensors'
    profile.write_bytes(b'no voice data')
    real_popen = speech.subprocess.Popen
    children = []
    child_code = '''
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        data = b'{"status":"healthy"}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
'''
    def launch(args, **kwargs):
        port = args[args.index('--port') + 1]
        child = real_popen([sys.executable, '-u', '-c', child_code, port], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(speech.subprocess, 'Popen', launch)
    engine = PocketTTS(binary_path=str(Path(sys.executable).resolve()),
                       voice_profile=str(profile))
    try:
        for _ in range(2):
            engine.start()
            assert engine.enabled
            assert engine._thread and engine._thread.is_alive()
            assert engine._server.poll() is None
            engine.stop()
            assert children[-1].poll() is not None
            assert engine._server is None
    finally:
        engine.stop()
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)
    assert len(children) == 2
