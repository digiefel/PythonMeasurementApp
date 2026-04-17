"""Process bridge for instrument sessions.

The main process talks to a small worker over multiprocessing queues. The worker
owns the vendor DLL-backed session object; the proxy only forwards method calls
and returns structured results or explicit errors.
"""

from __future__ import annotations

import os
import multiprocessing as mp
import queue
import subprocess
import time
import traceback
import uuid
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


def _worker_main(cmd_queue: mp.Queue, rsp_queue: mp.Queue) -> None:
    session = None
    try:
        while True:
            msg = cmd_queue.get()
            cmd = msg["cmd"]
            req_id = msg["req_id"]
            payload = msg.get("payload", {})

            try:
                if cmd == "init_b1500":
                    from instrumentio.sessions import B1500Session

                    session = B1500Session(payload["address"])
                    rsp_queue.put_nowait({"type": "ack", "req_id": req_id, "payload": {}})
                    continue

                if cmd == "bridge_info":
                    rsp_queue.put_nowait({
                        "type": "result",
                        "req_id": req_id,
                        "payload": {
                            "value": {
                                "pid": os.getpid(),
                                "session_initialized": session is not None,
                            }
                        },
                    })
                    continue

                if cmd == "call":
                    if session is None:
                        raise RuntimeError("B1500 session is not initialized")
                    method_name = payload["method"]
                    args = payload.get("args", [])
                    kwargs = payload.get("kwargs", {})
                    result = getattr(session, method_name)(*args, **kwargs)
                    rsp_queue.put_nowait({"type": "result", "req_id": req_id, "payload": {"value": result}})
                    continue

                if cmd == "stream_cv_sweep":
                    if session is None:
                        raise RuntimeError("B1500 session is not initialized")

                    def _on_point(step, dc_bias_v, para1, para2, time_s, status1, status2):
                        rsp_queue.put_nowait({
                            "type": "event",
                            "req_id": req_id,
                            "payload": {
                                "step": int(step),
                                "dc_bias_v": float(dc_bias_v),
                                "para1": float(para1),
                                "para2": float(para2),
                                "time_s": float(time_s),
                                "status1": int(status1),
                                "status2": int(status2),
                            },
                        })

                    session.stream_cv_sweep(
                        payload["cmu_channel"],
                        payload["cmu_mode"],
                        payload["meas_range"],
                        payload["expected_points"],
                        _on_point,
                    )
                    rsp_queue.put_nowait({"type": "done", "req_id": req_id, "payload": {}})
                    continue

                if cmd == "close":
                    if session is not None:
                        session.close()
                        session = None
                    rsp_queue.put_nowait({"type": "ack", "req_id": req_id, "payload": {}})
                    break

                raise RuntimeError(f"Unknown bridge command: {cmd}")
            except Exception:
                rsp_queue.put_nowait({
                    "type": "error",
                    "req_id": req_id,
                    "payload": {"message": traceback.format_exc()},
                })
    finally:
        if session is not None:
            session.close()


class RemoteB1500Session:
    """Proxy for a B1500 session running in a worker process."""

    def __init__(self, address: str):
        worker_python = _resolve_worker_python()
        _assert_worker_is_32bit(worker_python)
        ctx = mp.get_context("spawn")
        ctx_set_executable = getattr(ctx, "set_executable", None)
        if callable(ctx_set_executable):
            ctx_set_executable(worker_python)
        else:
            mp.set_executable(worker_python)
        self._cmd_queue: mp.Queue = ctx.Queue(maxsize=64)
        self._rsp_queue: mp.Queue = ctx.Queue(maxsize=64)
        self._process = ctx.Process(target=_worker_main, args=(self._cmd_queue, self._rsp_queue), daemon=True)
        self._worker_python = worker_python
        self._process.start()
        self._send_and_wait("init_b1500", {"address": address}, timeout_s=10.0)

    @property
    def wgfmu(self):
        raise RuntimeError("WGFMU bridge proxy is not implemented in RemoteB1500Session yet.")

    def bridge_info(self) -> dict:
        info = self._send_and_wait("bridge_info", {}, timeout_s=5.0)
        if not isinstance(info, dict):
            raise RuntimeError(f"Invalid bridge info response: {info!r}")
        info["configured_worker_python"] = self._worker_python
        return info

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
        try:
            self._cmd_queue.put(envelope, timeout=timeout_s)
        except queue.Full as exc:
            raise TimeoutError("Bridge command queue full for stream_cv_sweep") from exc

        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("No bridge response for stream_cv_sweep")
            try:
                rsp = self._rsp_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("No bridge response for stream_cv_sweep") from exc

            if rsp.get("req_id") != req_id:
                continue

            rsp_type = rsp.get("type")
            if rsp_type == "error":
                raise RuntimeError(rsp["payload"]["message"])
            if rsp_type == "event":
                payload = rsp["payload"]
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
            return self._send_and_wait("call", {"method": name, "args": list(args), "kwargs": kwargs}, timeout_s=30.0)

        return _call

    def close(self):
        if getattr(self, "_process", None) is None:
            return
        try:
            self._send_and_wait("close", {}, timeout_s=10.0)
        finally:
            if self._process.is_alive():
                self._process.join(timeout=2.0)
                if self._process.is_alive():
                    self._process.terminate()
                    self._process.join(timeout=1.0)

    def _send_and_wait(self, cmd: str, payload: dict, timeout_s: float) -> object:
        envelope = _make_envelope(cmd, payload)
        req_id = envelope["req_id"]
        try:
            self._cmd_queue.put(envelope, timeout=timeout_s)
        except queue.Full as exc:
            raise TimeoutError(f"Bridge command queue full for {cmd}") from exc

        while True:
            try:
                rsp = self._rsp_queue.get(timeout=timeout_s)
            except queue.Empty as exc:
                raise TimeoutError(f"No bridge response for {cmd}") from exc

            if rsp.get("req_id") != req_id:
                continue

            if rsp["type"] == "error":
                raise RuntimeError(rsp["payload"]["message"])

            if rsp["type"] == "result":
                return rsp["payload"].get("value")

            if rsp["type"] == "ack":
                return rsp.get("payload", {})

            raise RuntimeError(f"Unexpected bridge response type for {cmd}: {rsp['type']!r}")