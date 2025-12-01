import time
from typing import Callable


class TempTracker:
    """Lightweight helper to track temp samples and map them to normalized step space."""

    def __init__(self, log: Callable[[str], None] | None = None):
        self.log = log or (lambda msg: None)
        self.reset_run()

    def reset_run(self):
        self.step_starts = []
        self.step_durations = []
        self.step_measure_start = {}
        self.step_sample_counts = {}
        self.samples = []  # (ts, temp, step_idx)
        self.last_step_duration = None

    def step_started(self, idx: int):
        now = time.time()
        self.log(f"Temp step started idx={idx}")
        if self.step_starts:
            dur = now - self.step_starts[-1]
            self.step_durations.append(dur)
            self.last_step_duration = dur
        self.step_starts.append(now)
        self.step_measure_start.pop(idx, None)
        self.step_sample_counts[idx] = 0

    def phase_change(self, phase: str, idx: int):
        self.log(f"Temp phase {phase} idx={idx}")
        if phase == "measure_start":
            self.step_measure_start[idx] = time.time()
        elif phase == "measure_end" and idx < len(self.step_starts):
            now = time.time()
            dur = now - self.step_starts[idx]
            self.last_step_duration = dur
            while len(self.step_durations) < idx:
                self.step_durations.append(self.last_step_duration or 1.0)
            if len(self.step_durations) == idx:
                self.step_durations.append(dur)

    def _norm_x(self, ts: float, step_idx: int) -> float:
        if step_idx >= len(self.step_starts):
            return float(step_idx + 1)
        preds = self.step_durations if self.step_durations else []
        if step_idx < len(preds):
            dur = preds[step_idx]
        elif preds:
            dur = sum(preds) / len(preds)
        else:
            dur = self.last_step_duration or max(ts - self.step_starts[step_idx], 1.0)
        dur = max(dur, 1e-3)
        frac = min(max((ts - self.step_starts[step_idx]) / dur, 0.0), 0.99)
        return 1 + step_idx + frac

    def record_sample(self, ts: float, temp: float, step_idx: int):
        if step_idx >= len(self.step_starts):
            self.log(f"Dropping temp sample; step {step_idx} not started.")
            return None
        count = self.step_sample_counts.get(step_idx, 0)
        self.step_sample_counts[step_idx] = count + 1
        x_val = (1 + step_idx + 0.001) if count == 0 else self._norm_x(ts, step_idx)
        self.log(f"Temp sample mapped x={x_val:.3f} step={step_idx} n={count+1} temp={temp}")
        self.samples.append((ts, temp, step_idx))
        start = self.step_measure_start.get(step_idx)
        is_meas = start is not None and ts >= start
        return x_val, is_meas

    def iter_points(self):
        for ts, temp, step_idx in self.samples:
            if step_idx >= len(self.step_starts):
                continue
            start = self.step_measure_start.get(step_idx)
            is_meas = start is not None and ts >= start
            yield (self._norm_x(ts, step_idx), temp, is_meas, step_idx, ts)
