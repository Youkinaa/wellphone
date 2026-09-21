#!/usr/bin/env python3
"""Temporary scrcpy 4.1 two-socket probe, for the dedicated API 34 test AVD.

Creates one virtual display. Never captures display 0. Control API is limited to
finger gestures and directed Back/Enter. This is not a production session gate.
"""
import argparse
import json
import re
import secrets
import shlex
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path


def key_packet(action, keycode):
    if action not in (0, 1) or keycode not in (4, 66):
        raise ValueError('Probe keys are only BACK=4 and ENTER=66, down/up')
    return struct.pack('>BBiii', 0, action, keycode, 0, 0)


def touch_packet(action, x, y, width, height):
    if action not in (0, 1, 2):
        raise ValueError('Probe touch actions are down/up/move only')
    if not (0 < width <= 65535 and 0 < height <= 65535 and 0 <= x < width and 0 <= y < height):
        raise ValueError('Touch coordinate is outside the fixed capture size')
    # -2 is a generic finger; finger events have no mouse buttons.
    return struct.pack('>BBqiiHHHii', 2, action, -2, x, y, width, height,
                       0 if action == 1 else 65535, 0, 0)


class ScrcpyProbe:
    def __init__(self, *, adb, serial, server, output, size='720x1280/240',
                 save_video=False, encoder=None):
        if not re.fullmatch(r'[1-9]\d*x[1-9]\d*/[1-9]\d*', size):
            raise ValueError('size must be WIDTHxHEIGHT/DPI')
        self.adb_command = [str(adb), '-s', serial]
        self.server = Path(server).resolve(strict=True)
        self.output = Path(output)
        self.size, self.save_video, self.encoder = size, save_video, encoder
        self.scid = secrets.randbelow(0x7fffffff)
        self.remote = f'/data/local/tmp/wellphone-scrcpy-{self.scid:08x}.jar'
        self.port = self.process = self.video = self.control = None
        self.log_file = self.video_file = None
        self.display_id = self.width = self.height = None
        self.video_bytes = self.control_reply_bytes = 0
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.threads = []

    def adb(self, *args, check=True):
        return subprocess.run([*self.adb_command, *args], check=check,
                              capture_output=True, text=True, timeout=20)

    def start(self):
        self.output.mkdir(parents=True, exist_ok=False)
        self.log_file = (self.output / 'server.log').open('x', encoding='utf-8')
        try:
            self.adb('push', str(self.server), self.remote)
            self.port = int(self.adb('forward', 'tcp:0', f'localabstract:scrcpy_{self.scid:08x}').stdout.strip())
            options = [
                '4.1', f'scid={self.scid:08x}', 'tunnel_forward=true',
                'video=true', 'audio=false', 'control=true',
                f'new_display={self.size}', 'vd_destroy_content=true',
                'vd_system_decorations=false', 'clipboard_autosync=false',
                'power_on=false', 'power_off_on_close=false', 'stay_awake=false',
                'keep_active=false', 'cleanup=false', 'video_codec=h264',
                'video_bit_rate=2000000', 'max_fps=15',
                # Keep the forward handshake while disabling all video metadata.
                'raw_stream=true', 'send_dummy_byte=true', 'log_level=debug',
            ]
            if self.encoder:
                options.append(f'video_encoder={self.encoder}')
            command = shlex.join([f'CLASSPATH={self.remote}', 'app_process', '/',
                                  'com.genymobile.scrcpy.Server', *options])
            self.process = subprocess.Popen([*self.adb_command, 'shell', command],
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, bufsize=1)
            self._thread(self._read_log)
            deadline = time.monotonic() + 20
            last_error = None
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f'Server exited; inspect {self.output / "server.log"}')
                candidate = None
                try:
                    candidate = socket.create_connection(('127.0.0.1', self.port), timeout=1)
                    if candidate.recv(1) != b'\0':
                        raise ConnectionError('Forward closed before dummy-byte handshake')
                    self.video = candidate
                    break
                except (OSError, ConnectionError) as exc:
                    last_error = exc
                    if candidate:
                        candidate.close()
                    time.sleep(0.1)
            if self.video is None:
                raise RuntimeError(f'No video handshake: {last_error}')
            self.control = socket.create_connection(('127.0.0.1', self.port), timeout=5)
            self.control.settimeout(0.5)
            self.video.settimeout(0.5)
            if self.save_video:
                self.video_file = (self.output / 'secondary.h264').open('xb')
            self._thread(lambda: self._drain(self.video, True))
            self._thread(lambda: self._drain(self.control, False))
            if not self.ready.wait(max(0, deadline - time.monotonic())):
                raise RuntimeError(f'No new-display log; inspect {self.output / "server.log"}')
            if self.display_id <= 0:
                raise RuntimeError('Refusing non-secondary display')
            self._assert_running()
            self._write_status()
            return self
        except BaseException:
            self.close()
            raise

    def _thread(self, target):
        thread = threading.Thread(target=target, daemon=True)
        self.threads.append(thread)
        thread.start()

    def _read_log(self):
        for line in self.process.stdout:
            self.log_file.write(line)
            self.log_file.flush()
            match = re.search(r'New display: (\d+)x(\d+)/(\d+) \(id=(\d+)\)', line)
            if match:
                self.width, self.height, _, self.display_id = map(int, match.groups())
                self.ready.set()

    def _drain(self, sock, video):
        while not self.stop.is_set():
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    self.stop.set()
                    return
                if video:
                    self.video_bytes += len(chunk)
                    if self.video_file:
                        self.video_file.write(chunk)
                        self.video_file.flush()
                else:
                    self.control_reply_bytes += len(chunk)
            except socket.timeout:
                continue
            except OSError:
                self.stop.set()
                return

    def status(self):
        return dict(display_id=self.display_id, width=self.width, height=self.height,
                    video_bytes=self.video_bytes, control_reply_bytes=self.control_reply_bytes,
                    scid=f'{self.scid:08x}', port=self.port,
                    server_exit_code=self.process.poll() if self.process else None)

    def _write_status(self):
        (self.output / 'status.json').write_text(json.dumps(self.status(), indent=2) + '\n')

    def _assert_running(self):
        if (self.stop.is_set() or not self.ready.is_set() or not self.display_id
                or self.display_id <= 0 or self.process.poll() is not None):
            raise RuntimeError('Secondary display session is not ready/alive')

    def _send(self, packet):
        self._assert_running()
        self.control.sendall(packet)

    def key(self, keycode):
        self._send(key_packet(0, keycode))
        self._send(key_packet(1, keycode))

    def tap(self, x, y):
        self._send(touch_packet(0, x, y, self.width, self.height))
        time.sleep(0.05)
        self._send(touch_packet(1, x, y, self.width, self.height))

    def swipe(self, x1, y1, x2, y2, duration=0.4):
        if not 0.05 <= duration <= 5:
            raise ValueError('duration must be 0.05..5 seconds')
        # Validate both endpoints before sending the first event.
        start = touch_packet(0, x1, y1, self.width, self.height)
        end = touch_packet(1, x2, y2, self.width, self.height)
        self._send(start)
        steps = max(2, round(duration * 30))
        for i in range(1, steps + 1):
            time.sleep(duration / steps)
            x = round(x1 + (x2 - x1) * i / steps)
            y = round(y1 + (y2 - y1) * i / steps)
            self._send(touch_packet(2, x, y, self.width, self.height))
        self._send(end)

    def close(self):
        self.stop.set()
        for sock in (self.control, self.video):
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
        for thread in self.threads:
            thread.join(timeout=2)
        for stream in (self.video_file, self.log_file):
            if stream:
                stream.close()
        if self.port:
            self.adb('forward', '--remove', f'tcp:{self.port}', check=False)
        if self.process:
            self.adb('shell', 'rm', '-f', self.remote, check=False)
        if self.output.is_dir():
            self._write_status()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--server', required=True)
    parser.add_argument('--output', required=True, help='New directory for this probe run')
    parser.add_argument('--size', default='720x1280/240')
    parser.add_argument('--encoder')
    parser.add_argument('--save-video', action='store_true')
    parser.add_argument('--seconds', type=float, default=30)
    args = parser.parse_args()
    duration = args.seconds
    del args.seconds
    with ScrcpyProbe(**vars(args)) as probe:
        print(json.dumps(probe.status()), flush=True)
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            probe._assert_running()
            time.sleep(0.2)
        print(json.dumps(probe.status()), flush=True)


if __name__ == '__main__':
    main()
