"""Main-process proxy for the DearPyGui plot viewer.

PlotBridge owns local DataSources, coalesces data deltas, and manages IPC
to the separate viewer process via bounded multiprocessing queues.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
import uuid
from typing import Sequence

import multiprocessing as mp

from plotting.elements import DataSource, PlotDef

logger = logging.getLogger(__name__)

_CMD_QUEUE_MAXSIZE = 512
_RSP_QUEUE_MAXSIZE = 256
_FLUSH_INTERVAL_S = 1.0 / 30.0
_WARN_THROTTLE_S = 5.0


def _make_envelope(cmd: str, payload: dict) -> dict:
    return {
        "cmd": cmd,
        "req_id": uuid.uuid4().hex,
        "ts_ns": time.monotonic_ns(),
        "payload": payload,
    }


class PlotBridge:
    """Procedure-facing plot API. Accessed as ``runner.plot``."""

    def __init__(self) -> None:
        ctx = mp.get_context("spawn")
        self._cmd_queue: mp.Queue = ctx.Queue(maxsize=_CMD_QUEUE_MAXSIZE)
        self._rsp_queue: mp.Queue = ctx.Queue(maxsize=_RSP_QUEUE_MAXSIZE)

        # Deferred import: keeps DearPyGui out of the main process import graph
        from plotting.viewer import viewer_main
        self._process = ctx.Process(
            target=viewer_main,
            args=(self._cmd_queue, self._rsp_queue),
            daemon=True,
        )
        self._process.start()

        self._sources: dict[str, DataSource] = {}
        self._pending: dict[str, list[tuple[float, float]]] = {}
        self._pending_lock = threading.Lock()

        self._flush_timer: threading.Timer | None = None
        self._flush_stop = threading.Event()
        self._last_warn_ts: float = 0.0

        self._schedule_flush()
        self._send_and_wait("ping", {}, timeout_s=5.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configure(self, title: str, plots: list[PlotDef]) -> None:
        """Define figure layout and visual elements. Blocks until viewer acks."""
        self._sources.clear()
        with self._pending_lock:
            self._pending.clear()

        for plot_def in plots:
            for elem in plot_def.elements:
                if hasattr(elem, "source") and elem.source not in self._sources:
                    self._sources[elem.source] = DataSource()

        self._send_and_wait("configure_figure", {"title": title, "plots": plots}, timeout_s=5.0)

    def append_point(self, source: str, x: float, y: float) -> None:
        """Append a single point to a named source."""
        ds = self._require_source(source)
        ds.append_point(x, y)
        with self._pending_lock:
            self._pending.setdefault(source, []).append((x, y))

    def append_many(self, source: str, xs: Sequence[float], ys: Sequence[float]) -> None:
        """Append an array of points to a named source."""
        ds = self._require_source(source)
        ds.append_many(xs, ys)
        pairs = list(zip(xs, ys))
        with self._pending_lock:
            self._pending.setdefault(source, []).extend(pairs)

    def append_batch(self, data: dict[str, list[tuple[float, float]]]) -> None:
        """Append points to multiple sources in one call."""
        for source, pairs in data.items():
            ds = self._require_source(source)
            ds.append_pairs(pairs)
        with self._pending_lock:
            for source, pairs in data.items():
                self._pending.setdefault(source, []).extend(pairs)

    def set_limits(
        self,
        plot_id: str,
        xlim: tuple[float, float] | None = None,
        ylims: dict[int, tuple[float, float]] | None = None,
    ) -> None:
        """Set axis limits dynamically."""
        self._send_fire_and_forget("set_axis_limits", {
            "plot_id": plot_id,
            "xlim": xlim,
            "ylims": ylims,
        })

    def save_png(
        self,
        filename: str | None,
        output_root: str,
        output_relative: str,
        fallback_root: str,
        timeout_s: float = 8.0,
    ) -> str | None:
        """Export figure as PNG. Blocks until viewer acks or timeout.

        Returns the saved path on success, None if filename is None.
        Raises RuntimeError on viewer error, TimeoutError if no ack in time.
        """
        if filename is None:
            return None

        self._flush_deltas()

        primary_dir = os.path.join(output_root, output_relative)
        primary_path = os.path.join(primary_dir, filename)
        try:
            os.makedirs(primary_dir, exist_ok=True)
            save_path = primary_path
        except OSError as e:
            fallback_dir = os.path.join(fallback_root, output_relative)
            os.makedirs(fallback_dir, exist_ok=True)
            save_path = os.path.join(fallback_dir, filename)
            logger.warning("Primary save dir failed (%s), using fallback: %s", e, save_path)

        self._send_and_wait("save_png", {"path": save_path}, timeout_s=timeout_s)
        return save_path

    def source(self, name: str) -> DataSource:
        """Return the local DataSource for post-processing (e.g. linear_fit)."""
        return self._require_source(name)

    def shutdown(self, timeout_s: float = 3.0) -> None:
        """Send quit and join the viewer process."""
        self._flush_stop.set()
        if self._flush_timer is not None:
            self._flush_timer.cancel()

        if self._process.is_alive():
            try:
                self._cmd_queue.put_nowait(_make_envelope("quit", {}))
            except queue.Full:
                pass
            self._process.join(timeout=timeout_s)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)

    # ------------------------------------------------------------------
    # Delta coalescing
    # ------------------------------------------------------------------

    def _schedule_flush(self) -> None:
        if self._flush_stop.is_set():
            return
        self._flush_timer = threading.Timer(_FLUSH_INTERVAL_S, self._on_flush_tick)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _on_flush_tick(self) -> None:
        self._flush_deltas()
        self._schedule_flush()

    def _flush_deltas(self) -> None:
        with self._pending_lock:
            if not self._pending:
                return
            batch = self._pending.copy()
            self._pending.clear()

        envelope = _make_envelope("append_batch", {"data": batch})
        try:
            self._cmd_queue.put_nowait(envelope)
        except queue.Full:
            now = time.monotonic()
            if now - self._last_warn_ts > _WARN_THROTTLE_S:
                logger.warning("cmd_queue full — deltas buffered for retry")
                self._last_warn_ts = now
            with self._pending_lock:
                for source, pairs in batch.items():
                    existing = self._pending.get(source, [])
                    self._pending[source] = pairs + existing

    # ------------------------------------------------------------------
    # IPC helpers
    # ------------------------------------------------------------------

    def _require_source(self, name: str) -> DataSource:
        ds = self._sources.get(name)
        if ds is None:
            raise KeyError(f"Unknown data source: {name!r}")
        return ds

    def _send_fire_and_forget(self, cmd: str, payload: dict) -> None:
        if not self._process.is_alive():
            return
        envelope = _make_envelope(cmd, payload)
        try:
            self._cmd_queue.put_nowait(envelope)
        except queue.Full:
            logger.warning("cmd_queue full — dropping %s command", cmd)

    def _send_and_wait(self, cmd: str, payload: dict, timeout_s: float = 5.0) -> dict:
        """Send a command and block until a matching ack/error arrives."""
        envelope = _make_envelope(cmd, payload)
        req_id = envelope["req_id"]

        try:
            self._cmd_queue.put(envelope, timeout=timeout_s)
        except queue.Full:
            raise TimeoutError(f"cmd_queue full — could not send {cmd} (req_id={req_id})")

        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"No ack for {cmd} within {timeout_s}s (req_id={req_id})")
            try:
                rsp = self._rsp_queue.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if not self._process.is_alive():
                    raise RuntimeError(f"Viewer process died while waiting for {cmd} ack")
                continue

            if rsp.get("req_id") != req_id:
                continue  # discard stale acks

            if rsp["type"] == "error":
                raise RuntimeError(
                    f"Viewer error on {cmd}: {rsp['payload'].get('message', rsp['payload'])}"
                )
            return rsp.get("payload", {})
