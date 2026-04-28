"""B1500 bridge worker process.

Runs under a dedicated 32-bit Python interpreter and communicates with the
parent process using newline-delimited JSON messages on stdin/stdout.
"""

from __future__ import annotations

import json
import os
import sys
import traceback


def _emit(message: dict) -> None:
    line = json.dumps(message, separators=(",", ":"))
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        raise SystemExit(0)


def _emit_error(req_id: str | None, message: str) -> None:
    _emit({"type": "error", "req_id": req_id, "payload": {"message": message}})


def main() -> None:
    session = None
    try:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue

            req_id = None
            try:
                msg = json.loads(line)
                cmd = msg["cmd"]
                req_id = msg.get("req_id")
                payload = msg.get("payload", {})

                if cmd == "init_b1500":
                    from instrumentio.sessions import B1500Session

                    if session is not None:
                        session.close()
                    session = B1500Session(payload["address"])
                    _emit({"type": "ack", "req_id": req_id, "payload": {}})
                    continue

                if cmd == "bridge_info":
                    _emit(
                        {
                            "type": "result",
                            "req_id": req_id,
                            "payload": {
                                "value": {
                                    "pid": os.getpid(),
                                    "python_executable": sys.executable,
                                    "session_initialized": session is not None,
                                }
                            },
                        }
                    )
                    continue

                if cmd == "call":
                    if session is None:
                        raise RuntimeError("B1500 session is not initialized")
                    method_name = payload["method"]
                    args = payload.get("args", [])
                    kwargs = payload.get("kwargs", {})
                    result = getattr(session, method_name)(*args, **kwargs)
                    _emit({"type": "result", "req_id": req_id, "payload": {"value": result}})
                    continue

                if cmd == "stream_cv_sweep":
                    if session is None:
                        raise RuntimeError("B1500 session is not initialized")

                    def _on_point(step, dc_bias_v, para1, para2, time_s, status1, status2):
                        _emit(
                            {
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
                            }
                        )

                    session.stream_cv_sweep(
                        payload["cmu_channel"],
                        payload["cmu_mode"],
                        payload["meas_range"],
                        payload["expected_points"],
                        _on_point,
                    )
                    _emit({"type": "done", "req_id": req_id, "payload": {}})
                    continue

                if cmd == "wgfmu_call":
                    if session is None:
                        raise RuntimeError("B1500 session is not initialized")
                    method_name = payload["method"]
                    args = payload.get("args", [])
                    kwargs = payload.get("kwargs", {})
                    result = getattr(session.wgfmu, method_name)(*args, **kwargs)
                    _emit({"type": "result", "req_id": req_id, "payload": {"value": result}})
                    continue

                if cmd == "wgfmu_poll":
                    if session is None:
                        raise RuntimeError("B1500 session is not initialized")
                    ch1 = int(payload["channel_1"])
                    ch2 = int(payload["channel_2"])
                    status, elapsed, total, measured_1, total_1, measured_2, total_2 = session.wgfmu.poll(ch1, ch2)
                    _emit({
                        "type": "result",
                        "req_id": req_id,
                        "payload": {"value": {
                            "status": int(status),
                            "elapsed": float(elapsed),
                            "total": float(total),
                            "measured_1": int(measured_1),
                            "total_1": int(total_1),
                            "measured_2": int(measured_2),
                            "total_2": int(total_2),
                        }},
                    })
                    continue

                if cmd == "wgfmu_read_chunk":
                    if session is None:
                        raise RuntimeError("B1500 session is not initialized")
                    channel_id = int(payload["channel_id"])
                    from_index = int(payload["from_index"])
                    count = int(payload["count"])
                    to_index = from_index + count
                    times = []
                    values = []
                    for idx in range(from_index, to_index):
                        t, v = session.wgfmu.get_measure_value(channel_id, idx)
                        times.append(t)
                        values.append(v)
                    _emit({
                        "type": "result",
                        "req_id": req_id,
                        "payload": {"value": {"times": times, "values": values}},
                    })
                    continue

                if cmd == "close":
                    if session is not None:
                        session.close()
                        session = None
                    _emit({"type": "ack", "req_id": req_id, "payload": {}})
                    break

                raise RuntimeError(f"Unknown bridge command: {cmd}")
            except Exception:
                _emit_error(req_id, traceback.format_exc())
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
