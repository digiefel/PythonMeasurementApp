"""Transparent, single-flight calls to the instrument's native Python process.

A failed or cancelled connection is never reused. Calls are not retried.
Callbacks use acknowledgements, so no measurement events need to be dropped.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from .protocol import InstrumentCancelled, InstrumentError, CONNECT_TIMEOUT_S, STOP_TIMEOUT_S
from .emergency import PROCESS_TIMEOUT_S
from .ownership import InstrumentLease

logger = logging.getLogger(__name__)


def _worker_command():
    root = Path(__file__).resolve().parent.parent
    default = root / ".venv32" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = Path(os.environ.get("PYMEASUREMENT_BRIDGE_WORKER_PYTHON", default)).expanduser().resolve()
    if not python.is_file():
        raise FileNotFoundError(f"Instrument interpreter not found: {python}")
    module = os.environ.get("PYMEASUREMENT_BRIDGE_WORKER_MODULE", "instrumentio.bridge_worker")
    return [str(python), "-u", "-m", module]


class _Proxy:
    def __init__(self, connection, target=""):
        self._connection = connection
        self._target = target

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            timeout = kwargs.pop("_timeout_s", self._connection.timeout_s)
            callbacks = []

            def pack(value):
                if not callable(value):
                    return value
                callbacks.append(value)
                return {"__callback__": len(callbacks) - 1}

            return self._connection._request(
                ["call", self._target, name, [pack(value) for value in args],
                 {key: pack(value) for key, value in kwargs.items()}],
                callbacks, timeout,
            )

        return call


class RemoteB1500Session(_Proxy):
    # The operator decides when to stop a measurement, not the transport.
    DEFAULT_TIMEOUT_S = None
    STOP_TIMEOUT_S = STOP_TIMEOUT_S

    def __init__(self, address, *, timeout_s=DEFAULT_TIMEOUT_S, connect_timeout_s=CONNECT_TIMEOUT_S, cancel_events=()):
        super().__init__(self)
        self.address = address
        self.timeout_s = timeout_s
        self._cancel_events = cancel_events
        self.wgfmu = _Proxy(self, "wgfmu")
        self._calls = threading.RLock()
        self._closing = threading.Lock()
        self._stopping = threading.Event()
        self._active = False
        self._failure = None
        self._terminal = None
        self._closed = False
        self._shutdown_error = None
        self._cancel_requested = False
        self._wgfmu_used = False
        self._outgoing = queue.SimpleQueue()
        self._incoming = queue.SimpleQueue()
        self._threads = []
        self._process = None
        self._lease = None
        try:
            self._lease = InstrumentLease(address)
            command = _worker_command()
            self._worker_python = command[0]
            self._process = subprocess.Popen(
                command, cwd=str(Path(__file__).resolve().parent.parent),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", bufsize=1,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for target in (self._write, self._read, self._read_stderr):
                thread = threading.Thread(target=target, daemon=True)
                self._threads.append(thread)
                thread.start()
            self._info = self._request(["connect", address], [], connect_timeout_s)
        except BaseException as exc:
            logger.exception("Instrument connection failed at %s", address)
            try:
                self.close()
            except InstrumentError:
                logger.exception("Instrument connection cleanup failed")
            if isinstance(exc, (InstrumentCancelled, KeyboardInterrupt, SystemExit)):
                raise
            raise InstrumentError("Could not connect to the instrument. See the application log for details.") from None

    @property
    def is_open(self):
        return not self._stopping.is_set() and self._failure is None and self._process.poll() is None

    def bridge_info(self):
        """Developer diagnostics; not part of the user interface."""
        self._check_open()
        return dict(self._info, configured_worker_python=self._info["python_executable"])

    def exclusive(self):
        """Keep a sequence of calls together; cancellation remains independent."""
        return self._calls

    def stream_cv_sweep(self, cmu_channel, cmu_mode, meas_range, expected_points, callback, timeout_s=None):
        # Preserve the existing public timeout argument; execution is generic.
        return super().__getattr__("stream_cv_sweep")(
            cmu_channel, cmu_mode, meas_range, expected_points, callback, _timeout_s=timeout_s,
        )

    def _check_open(self):
        if self._failure is not None:
            raise self._failure
        if self._stopping.is_set():
            raise InstrumentCancelled("Measurement stopped.")
        if any(event.is_set() for event in self._cancel_events):
            raise InstrumentCancelled("Measurement stopped.")
        if self._process.poll() is not None:
            raise InstrumentError("Instrument connection was lost.")

    def _read(self):
        try:
            for line in self._process.stdout:
                message = json.loads(line)
                sizes = {"result": 2, "callback": 4, "error": 3, "stopped": 1}
                if not isinstance(message, list) or not message or not isinstance(message[0], str) or len(message) != sizes.get(message[0]):
                    raise ValueError(f"Invalid instrument response: {message!r}")
                if message[0] in ("error", "stopped"):
                    self._terminal = message
                    if message[0] == "error":
                        self._failure = InstrumentError(message[1])
                        logger.error("Instrument failure: %s", message[2])
                    self._stopping.set()
                self._incoming.put(message)
        except Exception:
            logger.exception("Instrument transport failed")
        finally:
            if self._terminal is None:
                self._failure = InstrumentError("Instrument connection was lost; output state could not be confirmed.")
                self._incoming.put(["error", str(self._failure), "Unexpected EOF or invalid protocol"])

    def _read_stderr(self):
        for line in self._process.stderr:
            logger.error("Instrument diagnostic: %s", line.rstrip())

    def _write(self):
        try:
            while (message := self._outgoing.get()) is not None:
                self._process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
                self._process.stdin.flush()
        except Exception:
            logger.exception("Instrument transport write failed")
            self._incoming.put(["error", "Instrument connection was lost.", "Command write failed"])

    def _request(self, message, callbacks, timeout):
        # Validate locally before any command can reach the instrument.
        json.dumps(message)
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("Instrument timeout must be finite and positive")
        interval = math.inf if timeout is None else timeout
        deadline = time.monotonic() + interval
        while not self._calls.acquire(timeout=0.05):
            self._check_open()
            if time.monotonic() >= deadline:
                raise InstrumentError("Instrument is busy.")
        try:
            self._check_open()
            if self._active:
                raise InstrumentError("Instrument calls are not allowed inside a data callback.")
            self._active = True
            try:
                if message[:2] == ["call", "wgfmu"]:
                    self._wgfmu_used = True
                self._outgoing.put(message)
                deadline = time.monotonic() + interval
                while True:
                    self._check_open()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise InstrumentError("Instrument did not respond in time.")
                    try:
                        reply = self._incoming.get(timeout=min(remaining, 0.05))
                    except queue.Empty:
                        continue
                    kind = reply[0]
                    if kind == "result":
                        if self._stopping.is_set():
                            raise InstrumentCancelled("Measurement stopped.")
                        return reply[1]
                    if kind == "callback":
                        self._check_open()
                        if not isinstance(reply[1], int) or not 0 <= reply[1] < len(callbacks) or not isinstance(reply[2], list) or not isinstance(reply[3], dict):
                            raise InstrumentError("Instrument returned invalid callback data.")
                        result = callbacks[reply[1]](*reply[2], **reply[3])
                        # Callback return values follow the same serialization rules.
                        json.dumps(result)
                        self._outgoing.put(["return", result])
                        deadline = time.monotonic() + interval
                    elif kind == "stopped":
                        raise InstrumentCancelled("Measurement stopped.")
                    else:
                        raise InstrumentError(reply[1])
            except BaseException as exc:
                if not isinstance(exc, InstrumentCancelled):
                    logger.exception("Instrument request ended: %s", message[:3])
                self.close()
                if self._shutdown_error is not None:
                    raise self._shutdown_error
                if self._cancel_requested or any(event.is_set() for event in self._cancel_events):
                    raise InstrumentCancelled("Measurement stopped.") from exc
                raise
            finally:
                self._active = False
        finally:
            self._calls.release()

    def cancel(self):
        """Stop independently of the call lock, including blocked native calls."""
        self._cancel_requested = True
        self.close()
        if self._shutdown_error is not None:
            raise self._shutdown_error

    def _emergency_shutdown(self):
        """The old process must be dead before resetting through a new session."""
        if self._process.poll() is None:
            raise InstrumentError("Instrument process could not be stopped.")
        command = [self._worker_python, "-u", "-m", "instrumentio.emergency", self.address]
        if self._wgfmu_used:
            command.append("--wgfmu")
        result = subprocess.run(
            command, cwd=str(Path(__file__).resolve().parent.parent),
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=PROCESS_TIMEOUT_S,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError(f"Emergency shutdown failed ({result.returncode}): {result.stderr}")
        logger.info("Instrument emergency reset completed at %s", self.address)

    def close(self):
        self._stopping.set()
        with self._closing:
            try:
                self._close_process()
            finally:
                if self._lease is not None and (self._process is None or self._process.poll() is not None):
                    self._lease.close()

    def _close_process(self):
        if self._closed or self._process is None:
            return
        self._outgoing.put(["cancel"])
        try:
            try:
                # Let a returning call finish its cleanup, but do not wait five
                # seconds before reaching hardware when acquisition is blocked.
                grace = min(self.STOP_TIMEOUT_S, 1.0) if self._active else self.STOP_TIMEOUT_S
                self._process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                logger.error("Instrument executor unresponsive; terminating pid=%s", self._process.pid)
                self._process.kill()
                self._process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            logger.exception("Could not terminate the instrument process")
            self._shutdown_error = self._failure = InstrumentError(
                "Instrument shutdown failed; output state could not be confirmed."
            )
            raise self._shutdown_error from None
        finally:
            self._outgoing.put(None)
            for thread in self._threads:
                thread.join(timeout=1)
            if not any(thread.is_alive() for thread in self._threads):
                for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
                    try:
                        stream.close()
                    except OSError:
                        logger.debug("Closing an already broken instrument pipe", exc_info=True)
            else:
                logger.error("Instrument I/O threads did not exit; leaving their streams to their owners")
            self._closed = self._process.poll() is not None
        if self._terminal is None or self._terminal[0] == "error":
            try:
                self._emergency_shutdown()
            except Exception:
                logger.exception("Instrument emergency shutdown failed at %s", self.address)
                self._shutdown_error = self._failure = InstrumentError(
                    "Instrument shutdown failed; output state could not be confirmed."
                )
                raise self._shutdown_error from None
