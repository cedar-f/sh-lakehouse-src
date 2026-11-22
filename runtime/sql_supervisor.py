"""Restart only the Spark SQL process; no Docker socket or host privileges.

The authenticated runner writes one request to the shared workspace. Status is
tagged with the request ID so an old READY result cannot complete a new restart.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from config import RUNTIME

CONTROL = RUNTIME / 'sql-control'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    temporary.replace(path)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return {}


def probe_sql():
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name('health.py')), 'sql'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


class SQLSupervisor:
    def __init__(self, control=CONTROL, command=None, probe=probe_sql, timeout=600):
        self.control = control
        self.command = command or [sys.executable, str(Path(__file__).with_name('sql_server.py'))]
        self.probe = probe
        self.timeout = timeout
        self.process = None
        self.request_id = None
        self.started = 0
        self.state = 'STOPPED'

    def status(self, state, error=None):
        self.state = state
        value = {'id': self.request_id, 'state': state, 'updated': time.time(),
                 'pid': self.process.pid if self.process else None}
        if error:
            value['error'] = error
        write_json(self.control / 'status.json', value)

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=10)
        self.process = None

    def launch(self, request_id):
        self.request_id = request_id
        self.status('RESTARTING')
        self.stop()
        try:
            self.process = subprocess.Popen(self.command, start_new_session=True)
            self.started = time.monotonic()
            self.status('STARTING')
        except Exception as error:
            self.status('FAILED', str(error))

    def step(self):
        request = read_json(self.control / 'request.json')
        if request.get('id') and request['id'] != self.request_id:
            self.launch(request['id'])
        if self.process and self.process.poll() is not None and self.state != 'FAILED':
            self.status('FAILED', f'Spark SQL exited with code {self.process.returncode}; see SQL container logs')
        if self.state == 'STARTING':
            if self.probe() and self.process.poll() is None:
                self.status('READY')
            elif time.monotonic() - self.started > self.timeout:
                self.status('FAILED', 'Spark SQL did not become ready before the startup timeout; see SQL container logs')
                self.stop()

    def run(self):
        stopping = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stopping.set())
        self.launch(read_json(self.control / 'request.json').get('id'))
        try:
            while not stopping.is_set():
                self.step()
                stopping.wait(1)
        finally:
            self.stop()
            self.status('STOPPED')


if __name__ == '__main__':
    SQLSupervisor().run()
