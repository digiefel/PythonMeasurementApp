import time
from typing import Callable, List, Optional, Tuple


class TempTracker:
    """Helper to track temperature samples on a time axis and maintain rolling estimates."""

    def __init__(self, log: Callable[[str], None] | None = None):
        self.log = log or (lambda msg: None)
        # Defaults
        self.default_warmup_per_deg = 2.0   # seconds per deg C guess
        self.default_measure_per_dev = 10.0 # seconds per device guess
        self.min_warmup_s = 5.0
        self.min_measure_s = 3.0
        self.reset_run()

    def reset_run(self, device_count: int = 1):
        self.device_count = max(int(device_count or 1), 1)
        self.run_start_ts: Optional[float] = None
        self.wait_after_s = 0.0
        self.planned_temps: List[float] = []
        self.step_meta: List[dict] = []  # [{start_ts, measure_start_ts, measure_end_ts, device_count}]
        self.samples: List[Tuple[float, float, int, bool]] = []  # (ts, temp, step_idx, is_meas)
        self.setpoints: List[Tuple[float, float, int]] = []  # (ts, temp, step_idx)
        self.warmup_per_deg_est = self.default_warmup_per_deg
        self.measure_per_device_est = self.default_measure_per_dev
        self.last_actual_temp: Optional[float] = None
        self.devices_done = {}  # step_idx -> completed device count
        self._warmup_samples = 0
        self._measure_samples = 0

    # --- Run lifecycle ---
    def start_run(self, planned_temps, wait_after_s: float, device_count: int = 1):
        """Reset and seed the tracker for a new run."""
        self.reset_run(device_count=device_count)
        self.planned_temps = list(planned_temps or [])
        self.wait_after_s = max(wait_after_s or 0.0, 0.0)

    def _ensure_step(self, idx: int) -> dict:
        while len(self.step_meta) <= idx:
            self.step_meta.append({})
        meta = self.step_meta[idx]
        meta.setdefault("device_count", self.device_count)
        return meta

    def step_started(self, idx: int):
        now = time.time()
        self.log(f"Temp step started idx={idx}")
        if self.run_start_ts is None:
            self.run_start_ts = now
        meta = self._ensure_step(idx)
        meta["start_ts"] = now
        meta.pop("measure_start_ts", None)
        meta.pop("measure_end_ts", None)

    def phase_change(self, phase: str, idx: int):
        self.log(f"Temp phase {phase} idx={idx}")
        meta = self._ensure_step(idx)
        if phase == "measure_start":
            meta["measure_start_ts"] = time.time()
            self._update_warmup_estimate(idx)
        elif phase == "measure_end":
            meta["measure_end_ts"] = time.time()
            self._update_measure_estimate(idx)

    # --- Recording ---
    def _record_setpoint(self, ts: float, temp: float, step_idx: int):
        self.setpoints.append((ts, temp, step_idx))

    def record_sample(self, ts: float, temp: float, step_idx: int, source: str = "poll"):
        """Record a temperature sample or setpoint event."""
        if self.run_start_ts is None:
            return None
        meta = self._ensure_step(step_idx)
        if meta.get("start_ts") is None:
            return None
        is_meas = meta.get("measure_start_ts") is not None and ts >= meta["measure_start_ts"]
        if source == "setpoint":
            self._record_setpoint(ts, temp, step_idx)
        self.last_actual_temp = temp
        self.samples.append((ts, temp, step_idx, is_meas))
        return ts - self.run_start_ts

    def device_finished(self, ts: float, step_idx: int, completed_devices: int, total_devices: int):
        """Update per-device estimate as each device finishes."""
        meta = self._ensure_step(step_idx)
        meta["device_count"] = max(int(total_devices or 1), 1)
        if meta.get("measure_start_ts") is None:
            return
        elapsed = max(ts - meta["measure_start_ts"], 0.0)
        per_device = elapsed / max(int(completed_devices or 1), 1)
        self.measure_per_device_est = (self.measure_per_device_est * self._measure_samples + per_device) / (self._measure_samples + 1)
        self._measure_samples += 1
        self.devices_done[step_idx] = completed_devices
        self.log(f"[meas_obs_partial] idx={step_idx} elapsed={elapsed:.1f}s devices={completed_devices}/{total_devices} per_dev={per_device:.3f}s avg={self.measure_per_device_est:.3f} n={self._measure_samples}")

    def _update_warmup_estimate(self, idx: int):
        meta = self._ensure_step(idx)
        start = meta.get("start_ts")
        meas_start = meta.get("measure_start_ts")
        if start is None or meas_start is None:
            return
        duration_total = max(meas_start - start, 0.0)
        target = self.planned_temps[idx] if idx < len(self.planned_temps) else None
        prev_target = None
        if idx > 0 and (idx - 1) < len(self.planned_temps):
            prev_target = self.planned_temps[idx - 1]
        elif self.setpoints:
            prev_target = self.setpoints[-1][1]
        delta = abs((target or 0.0) - (prev_target if prev_target is not None else 0.0)) if target is not None else None
        if delta is None or delta < 0.25:
            delta = 1.0  # avoid divide by zero and tiny swings
        ramp_only = max(duration_total - self.wait_after_s, 0.0)
        per_deg = ramp_only / max(delta, 1e-3)
        self.warmup_per_deg_est = (self.warmup_per_deg_est * self._warmup_samples + per_deg) / (self._warmup_samples + 1)
        self._warmup_samples += 1

    def _update_measure_estimate(self, idx: int):
        meta = self._ensure_step(idx)
        start = meta.get("measure_start_ts")
        end = meta.get("measure_end_ts")
        if start is None or end is None:
            return
        total = max(end - start, 0.0)
        device_count = meta.get("device_count") or self.device_count
        per_device = total / max(int(device_count), 1)
        self.measure_per_device_est = (self.measure_per_device_est * self._measure_samples + per_device) / (self._measure_samples + 1)
        self._measure_samples += 1
        self.log(f"[meas_obs] idx={idx} total={total:.1f}s per_dev={per_device:.3f}s avg={self.measure_per_device_est:.3f} n={self._measure_samples}")

    def _estimate_warmup(self, idx: int, prev_temp: Optional[float], target_temp: Optional[float], meta: dict) -> float:
        if meta.get("start_ts") is not None and meta.get("measure_start_ts") is not None:
            return max(meta["measure_start_ts"] - meta["start_ts"], 0.0)
        delta = None
        if target_temp is not None:
            base_prev = prev_temp
            if base_prev is None and idx > 0 and (idx - 1) < len(self.planned_temps):
                base_prev = self.planned_temps[idx - 1]
            if base_prev is not None:
                delta = abs(target_temp - base_prev)
        delta = delta if delta is not None else 1.0
        if self._warmup_samples == 0:
            est_per_deg = (self.wait_after_s * 2.0) / max(delta, 1e-3)  # aim for warmup=2*wait when no history
        else:
            est_per_deg = self.warmup_per_deg_est
        warmup_core = max(est_per_deg * delta, self.min_warmup_s)
        return warmup_core + self.wait_after_s

    def _estimate_measure(self, meta: dict) -> float:
        if meta.get("measure_start_ts") is not None and meta.get("measure_end_ts") is not None:
            return max(meta["measure_end_ts"] - meta["measure_start_ts"], 0.0)
        device_count = meta.get("device_count") or self.device_count
        est = self.measure_per_device_est * max(int(device_count), 1)
        return max(est, self.min_measure_s)

    # --- Public series accessors ---
    def actual_series(self) -> Tuple[Tuple[List[float], List[float]], Tuple[List[float], List[float]]]:
        """Return ((wait_x, wait_y), (meas_x, meas_y)) in seconds relative to run start."""
        if self.run_start_ts is None:
            return ([], []), ([], [])
        wait_x, wait_y, meas_x, meas_y = [], [], [], []
        for ts, temp, _, is_meas in self.samples:
            t_rel = ts - self.run_start_ts
            if is_meas:
                meas_x.append(t_rel)
                meas_y.append(temp)
            else:
                wait_x.append(t_rel)
                wait_y.append(temp)
        return (wait_x, wait_y), (meas_x, meas_y)

    def setpoint_series(self) -> Tuple[List[float], List[float]]:
        """Return step-style setpoint series aligned to run start."""
        if self.run_start_ts is None or not self.setpoints:
            return [], []
        pts = sorted(self.setpoints, key=lambda p: p[0])
        xs: List[float] = []
        ys: List[float] = []
        first_rel = max(pts[0][0] - self.run_start_ts, 0.0)
        first_temp = pts[0][1]
        xs.extend([0.0, first_rel])
        ys.extend([first_temp, first_temp])
        last_temp = first_temp
        for ts, temp, _ in pts[1:]:
            rel = max(ts - self.run_start_ts, 0.0)
            xs.extend([rel, rel])
            ys.extend([last_temp, temp])
            last_temp = temp
        tail_rel = max((self.samples[-1][0] - self.run_start_ts) if self.samples else pts[-1][0] - self.run_start_ts, 0.0)
        xs.append(tail_rel)
        ys.append(last_temp)
        return xs, ys

    def predicted_schedule(self) -> Tuple[List[float], List[float]]:
        """Return a step-function prediction for the full temperature plan."""
        if self.run_start_ts is None or not self.planned_temps:
            return [], []
        xs: List[float] = []
        ys: List[float] = []
        time_cursor = 0.0
        prev_temp: Optional[float] = None
        for idx, target in enumerate(self.planned_temps):
            meta = self._ensure_step(idx)
            start_rel = meta.get("start_ts")
            start_rel = max(start_rel - self.run_start_ts, 0.0) if start_rel else time_cursor
            start_rel = max(start_rel, time_cursor)
            warmup = self._estimate_warmup(idx, prev_temp, target, meta)
            meas = self._estimate_measure(meta)
            finish_rel = start_rel + warmup + meas

            initial_temp = prev_temp if prev_temp is not None else target
            if not xs:
                xs.extend([0.0, start_rel])
                ys.extend([initial_temp, initial_temp])
            else:
                xs.append(start_rel)
                ys.append(initial_temp)

            xs.extend([start_rel, finish_rel])
            ys.extend([target, target])
            time_cursor = finish_rel
            prev_temp = target
        return xs, ys
