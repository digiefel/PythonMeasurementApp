"""Process bridge for instrument sessions.

The main process talks to a dedicated worker interpreter over newline-delimited
JSON messages on stdin/stdout. The worker owns the vendor DLL-backed session
object; this avoids multiprocessing spawn importing the UI module.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Callable


def _make_envelope(cmd: str, payload: dict) -> dict:
    return {
        "cmd": cmd,
        "req_id": uuid.uuid4().hex,
        "payload": payload,
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_worker_python() -> Path:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    python_name = "python.exe" if os.name == "nt" else "python"
    return _project_root() / ".venv32" / scripts_dir / python_name


def _resolve_worker_python() -> str:
    configured = os.environ.get("PYMEASUREMENT_BRIDGE_WORKER_PYTHON")
    candidate = Path(configured).expanduser() if configured else _default_worker_python()
    candidate = candidate.resolve()
    if not candidate.is_file():
        if configured:
            raise FileNotFoundError(
                "PYMEASUREMENT_BRIDGE_WORKER_PYTHON does not exist: "
                f"{candidate}"
            )
        raise FileNotFoundError(
            "Bridge worker python not found at default path: "
            f"{candidate}. Create .venv32 and run the app from .venv."
        )
    return str(candidate)


def _assert_worker_is_32bit(worker_python: str) -> None:
    try:
        out = subprocess.check_output(
            [worker_python, "-c", "import struct; print(struct.calcsize('P') * 8)"],
            text=True,
            timeout=10,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to verify worker python bitness: {worker_python}") from exc

    bits = out.strip().splitlines()[0] if out.strip() else ""
    if bits != "32":
        raise RuntimeError(
            "Bridge worker python must be 32-bit, got "
            f"{bits or 'unknown'}-bit: {worker_python}"
        )


class RemoteWGFMUProxy:
    """Proxy for WGFMUSession in the bridge worker.

    Simple calls are routed via ``wgfmu_call`` through ``__getattr__``.
    ``read_chunk`` fetches a contiguous block of samples in one round-trip.
    ``poll`` combines get_status + get_measure_value_size for two channels
    into one round-trip.
    """

    def __init__(self, parent: "RemoteB1500Session") -> None:
        self._parent = parent

    def clear(self) -> None:
        self._parent._send_and_wait(
            "wgfmu_call",
            {"method": "clear", "args": [], "kwargs": {}},
            timeout_s=30.0,
        )

    def abort(self, timeout_s: float = 2.0):
        """Abort with a generous bridge timeout to cover the wait loop."""
        return self._parent._send_and_wait(
            "wgfmu_call",
            {"method": "abort", "args": [float(timeout_s)], "kwargs": {}},
            timeout_s=max(timeout_s + 5.0, 10.0),
        )

    def poll(self, channel_1: int, channel_2: int):
        """Single round-trip: get_status + get_measure_value_size for two channels.

        Returns (status, elapsed, total, measured_1, total_1, measured_2, total_2).
        """
        r = self._parent._send_and_wait(
            "wgfmu_poll",
            {"channel_1": int(channel_1), "channel_2": int(channel_2)},
            timeout_s=10.0,
        )
        return (
            r["status"], r["elapsed"], r["total"],
            r["measured_1"], r["total_1"],
            r["measured_2"], r["total_2"],
        )

    def read_chunk(
        self, channel_id: int, from_index: int, count: int
    ) -> list[tuple[float, float]]:
        """Fetch ``count`` samples starting at ``from_index`` in one round-trip.

        The caller is responsible for ensuring the requested range is available.
        Returns a list of (time, value) tuples.
        """
        result = self._parent._send_and_wait(
            "wgfmu_read_chunk",
            {"channel_id": int(channel_id), "from_index": int(from_index), "count": int(count)},
            timeout_s=60.0,
        )
        return list(zip(result["times"], result["values"]))

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _call(*args, **kwargs):
            return self._parent._send_and_wait(
                "wgfmu_call",
                {"method": name, "args": list(args), "kwargs": kwargs},
                timeout_s=30.0,
            )

        return _call


class RemoteB1500Session:
    """Proxy for a B1500 session running in a worker process."""

    def __init__(self, address: str):
        worker_python = _resolve_worker_python()
        _assert_worker_is_32bit(worker_python)

        worker_module = os.environ.get("PYMEASUREMENT_BRIDGE_WORKER_MODULE", "instrumentio.bridge_worker")
        cmd = [worker_python, "-u", "-m", worker_module]

        self._worker_python = worker_python
        self._process = subprocess.Popen(
            cmd,
            cwd=str(_project_root()),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None or self._process.stderr is None:
            raise RuntimeError("Bridge worker pipe setup failed.")

        self._rsp_queue: queue.Queue = queue.Queue(maxsize=512)
        self._write_lock = threading.Lock()
        self._stderr_lock = threading.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=200)
        self._wgfmu_proxy: RemoteWGFMUProxy | None = None

        self._stdout_thread = threading.Thread(target=self._stdout_reader, daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_reader, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

        try:
            self._send_and_wait("init_b1500", {"address": address}, timeout_s=10.0)
        except Exception:
            self.close()
            raise

    @property
    def wgfmu(self) -> RemoteWGFMUProxy:
        if self._wgfmu_proxy is None:
            self._wgfmu_proxy = RemoteWGFMUProxy(self)
        return self._wgfmu_proxy

    def bridge_info(self) -> dict:
        info = self._send_and_wait("bridge_info", {}, timeout_s=5.0)
        if not isinstance(info, dict):
            raise RuntimeError(f"Invalid bridge info response: {info!r}")
        info["configured_worker_python"] = self._worker_python
        return info

    def run_cmu_phase_compensation(self, channel: int, mode: int = 1) -> dict:
        """Phase compensation can legitimately exceed the generic RPC timeout."""
        return self._send_and_wait(
            "call",
            {
                "method": "run_cmu_phase_compensation",
                "args": [int(channel), int(mode)],
                "kwargs": {},
            },
            timeout_s=120.0,
        )

    def stream_cv_sweep(
        self,
        cmu_channel: int,
        cmu_mode: int,
        meas_range: float,
        expected_points: int,
        callback: Callable[[int, float, float, float, float, int, int], None],
        timeout_s: float = 120.0,
    ) -> None:
        envelope = _make_envelope(
            "stream_cv_sweep",
            {
                "cmu_channel": int(cmu_channel),
                "cmu_mode": int(cmu_mode),
                "meas_range": float(meas_range),
                "expected_points": int(expected_points),
            },
        )
        req_id = envelope["req_id"]
        self._send_envelope(envelope)

        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"No bridge response for stream_cv_sweep. {self._worker_diagnostics()}"
                )

            rsp = self._wait_for_response(req_id, "stream_cv_sweep", remaining)
            rsp_type = rsp.get("type")

            if rsp_type == "error":
                raise RuntimeError(rsp.get("payload", {}).get("message", "Bridge worker error"))

            if rsp_type == "event":
                payload = rsp.get("payload", {})
                callback(
                    int(payload["step"]),
                    float(payload["dc_bias_v"]),
                    float(payload["para1"]),
                    float(payload["para2"]),
                    float(payload["time_s"]),
                    int(payload["status1"]),
                    int(payload["status2"]),
                )
                continue

            if rsp_type == "done":
                return

            raise RuntimeError(f"Unexpected bridge response type for stream_cv_sweep: {rsp_type!r}")

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _call(*args, **kwargs):
            return self._send_and_wait(
                "call",
                {"method": name, "args": list(args), "kwargs": kwargs},
                timeout_s=30.0,
            )

        return _call

    def close(self):
        if getattr(self, "_process", None) is None:
            return
        process = self._process
        if process.poll() is None:
            try:
                self._send_and_wait("close", {}, timeout_s=5.0)
            except Exception:
                pass

        if process.poll() is None:
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)

        for stream_name in ("stdin", "stdout", "stderr"):
            stream = getattr(process, stream_name, None)
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    def _stdout_reader(self) -> None:
        assert self._process.stdout is not None
        for raw in self._process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                msg = {
                    "type": "error",
                    "req_id": None,
                    "payload": {"message": f"Invalid JSON from bridge worker: {line[:300]}"},
                }
            self._queue_response(msg)

        self._queue_response(
            {
                "type": "worker_exit",
                "req_id": None,
                "payload": {"exit_code": self._process.poll()},
            }
        )

    def _stderr_reader(self) -> None:
        assert self._process.stderr is not None
        for raw in self._process.stderr:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            with self._stderr_lock:
                self._stderr_lines.append(line)

    def _queue_response(self, msg: dict) -> None:
        try:
            self._rsp_queue.put_nowait(msg)
        except queue.Full:
            try:
                self._rsp_queue.get_nowait()
            except queue.Empty:
                pass
            self._rsp_queue.put_nowait(msg)

    def _stderr_tail(self, max_lines: int = 15) -> str:
        with self._stderr_lock:
            lines = list(self._stderr_lines)[-max_lines:]
        return "\n".join(lines)

    def _worker_diagnostics(self) -> str:
        exit_code = self._process.poll()
        state = "running" if exit_code is None else f"exited with code {exit_code}"
        msg = f"Bridge worker ({self._worker_python}) is {state}."
        tail = self._stderr_tail()
        if tail:
            msg += f"\nWorker stderr tail:\n{tail}"
        return msg

    def _send_envelope(self, envelope: dict) -> None:
        if self._process.poll() is not None:
            raise RuntimeError(self._worker_diagnostics())

        line = json.dumps(envelope, separators=(",", ":")) + "\n"
        with self._write_lock:
            if self._process.poll() is not None:
                raise RuntimeError(self._worker_diagnostics())
            assert self._process.stdin is not None
            try:
                self._process.stdin.write(line)
                self._process.stdin.flush()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed sending bridge command {envelope.get('cmd')!r}. {self._worker_diagnostics()}"
                ) from exc

    def _wait_for_response(self, req_id: str, cmd: str, timeout_s: float) -> dict:
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"No bridge response for {cmd}. {self._worker_diagnostics()}")
            try:
                rsp = self._rsp_queue.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if self._process.poll() is not None:
                    raise RuntimeError(
                        f"Bridge worker exited while waiting for {cmd}. {self._worker_diagnostics()}"
                    )
                continue

            rsp_type = rsp.get("type")
            if rsp_type == "worker_exit":
                raise RuntimeError(
                    f"Bridge worker exited while waiting for {cmd}. {self._worker_diagnostics()}"
                )

            rsp_req_id = rsp.get("req_id")
            if rsp_type == "error" and rsp_req_id is None:
                raise RuntimeError(rsp.get("payload", {}).get("message", "Bridge worker error"))

            if rsp_req_id != req_id:
                continue

            return rsp

    def _send_and_wait(self, cmd: str, payload: dict, timeout_s: float) -> object:
        envelope = _make_envelope(cmd, payload)
        req_id = envelope["req_id"]
        self._send_envelope(envelope)
        rsp = self._wait_for_response(req_id, cmd, timeout_s)

        rsp_type = rsp.get("type")
        if rsp_type == "error":
            raise RuntimeError(rsp.get("payload", {}).get("message", "Bridge worker error"))

        if rsp_type == "result":
            return rsp.get("payload", {}).get("value")

        if rsp_type == "ack":
            return rsp.get("payload", {})

        raise RuntimeError(f"Unexpected bridge response type for {cmd}: {rsp_type!r}")
