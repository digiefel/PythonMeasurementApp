import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import FuncFormatter

from temp_tracker import TempTracker


class TemperatureUI:
    """Encapsulates the temperature panel UI and live temp tracking."""

    def __init__(self, root: tk.Tk, runner, log: Callable[[str], None]):
        self.root = root
        self.runner = runner
        self.log = log
        # Runner callbacks
        self.runner.temp_step_started_cb = lambda idx: self._post(self._on_step_start, idx)
        self.runner.temp_phase_cb = lambda phase, idx: self._post(self._on_phase_change, phase, idx)
        self.runner.temp_sample_cb = lambda ts, temp, step_idx, source: self._post(self._record_sample, ts, temp, step_idx, source)
        self.runner.temp_device_done_cb = lambda ts, step_idx, done, total: self._post(self._on_device_done, ts, step_idx, done, total)

        # UI state
        self.enabled_var = tk.BooleanVar(value=False)
        self.mode_var = tk.StringVar(value="Setpoint")
        self.setpoint_var = tk.StringVar()
        self.sweep_var = tk.StringVar()
        self.wait_var = tk.StringVar(value="0")
        self.value_var = tk.StringVar(value="--")
        self.setpoint_display_var = tk.StringVar(value="--")

        # Tracking
        self.temp_tracker = TempTracker(self.log)
        self._poll_job = None
        self._run_active = False

        # Widgets (set in build_panel)
        self.profile_fig: Optional[Figure] = None
        self.profile_ax = None
        self.profile_canvas = None
        self.profile_widget = None
        self.mode_cb = None
        self.setpoint_entry = None
        self.sweep_entry = None
        self.wait_entry = None
        self.set_button = None
        self.setpoint_entry_label = None
        self.sweep_entry_label = None

    # --- UI construction ---
    def build_panel(self, parent_frame: ttk.Frame):
        temp_enable_cb = ttk.Checkbutton(parent_frame, text="Temperature", variable=self.enabled_var, command=self._toggle_controls)
        temp_frame = ttk.LabelFrame(parent_frame, labelwidget=temp_enable_cb)
        temp_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=6)
        temp_frame.grid_columnconfigure(0, weight=1)
        temp_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(temp_frame, text="Mode").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.mode_cb = ttk.Combobox(temp_frame, textvariable=self.mode_var, values=["Setpoint", "Sweep"], state="readonly")
        self.mode_cb.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        self.mode_cb.bind('<<ComboboxSelected>>', lambda e=None: self._toggle_controls())
        self.setpoint_entry_label = ttk.Label(temp_frame, text="Setpoint (C)")
        self.setpoint_entry_label.grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.setpoint_entry = ttk.Entry(temp_frame, textvariable=self.setpoint_var)
        self.setpoint_entry.grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        self.sweep_entry_label = ttk.Label(temp_frame, text="Sweep list (C)")
        self.sweep_entry_label.grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.sweep_entry = ttk.Entry(temp_frame, textvariable=self.sweep_var)
        self.sweep_entry.grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        ttk.Label(temp_frame, text="Wait after stable (s)").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.wait_entry = ttk.Entry(temp_frame, textvariable=self.wait_var)
        self.wait_entry.grid(row=3, column=1, sticky="ew", padx=2, pady=2)
        self.set_button = ttk.Button(temp_frame, text="Set Temperature", command=self._set_temperature_now)
        self.set_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 2))
        temp_row = ttk.Frame(temp_frame)
        temp_row.grid(row=6, column=0, columnspan=2, sticky="ew", padx=2, pady=(2, 0))
        for c in range(4):
            temp_row.grid_columnconfigure(c, weight=1)
        ttk.Label(temp_row, text="Temp:").grid(row=0, column=0, sticky="w", padx=2)
        self.temp_value_label = ttk.Label(temp_row, textvariable=self.value_var)
        self.temp_value_label.grid(row=0, column=1, sticky="w", padx=2)
        ttk.Label(temp_row, text="Setpoint:").grid(row=0, column=2, sticky="e", padx=2)
        ttk.Label(temp_row, textvariable=self.setpoint_display_var).grid(row=0, column=3, sticky="e", padx=2)

        # Mini profile plot
        self.profile_fig = Figure(figsize=(2.0, 0.8), dpi=100, layout='compressed')
        self.profile_ax = self.profile_fig.add_subplot(111)
        self.profile_ax.tick_params(axis='both', labelsize=7)
        self.profile_ax.spines["top"].set_visible(False)
        self.profile_ax.spines["right"].set_visible(False)
        self.profile_canvas = FigureCanvasTkAgg(self.profile_fig, master=temp_frame)
        self.profile_widget = self.profile_canvas.get_tk_widget()
        self.profile_widget.grid(row=7, column=0, columnspan=2, sticky="ew", padx=2, pady=(2, 2))
        self.profile_fig.patch.set_alpha(0)
        self.profile_ax.set_facecolor("none")
        self.profile_widget.configure(bg=self.root.cget('bg'), highlightthickness=0)

        # trace sweep field for live preview
        self.sweep_var.trace_add('write', lambda *_: self._update_sweep_plot())
        self._toggle_controls()
        self._update_sweep_plot()
        return temp_frame

    # --- Run lifecycle ---
    def collect_run_inputs(self) -> Optional[tuple]:
        enabled = self.enabled_var.get()
        mode = self.mode_var.get()
        if mode not in ("Setpoint", "Sweep"):
            mode = "Setpoint"
            self.mode_var.set(mode)
        try:
            wait_after = float(self.wait_var.get() or 0.0)
        except ValueError:
            messagebox.showerror("Invalid temperature wait", "Wait after stabilization must be a number.")
            return None
        temps = []
        if enabled:
            try:
                if mode == "Setpoint":
                    temps = [float(self.setpoint_var.get())]
                else:
                    temps = [float(tok.strip()) for tok in self.sweep_var.get().split(',') if tok.strip()]
                if not temps:
                    raise ValueError("No temperatures provided")
            except Exception:
                messagebox.showerror("Invalid temperature values", "Provide numeric temperature values in °C.")
                return None
        return enabled, temps, wait_after, mode

    def start_run(self, planned_temps, wait_after_s: float, device_count: int = 1):
        self._run_active = True
        self.temp_tracker.start_run(planned_temps, wait_after_s, device_count=device_count)
        self.log("Temp run active: polling + logging enabled.")
        self._start_polling(self._safe_poll_interval())

    def stop_run(self):
        self._run_active = False
        self._stop_polling()

    def apply_last_selection(self, last_sel: dict):
        if 'temperature_enabled' in last_sel:
            self.enabled_var.set(bool(last_sel.get('temperature_enabled')))
        if 'temperature_mode' in last_sel:
            mode_val = last_sel.get('temperature_mode', 'Setpoint')
            if mode_val not in ("Setpoint", "Sweep"):
                mode_val = "Setpoint"
            self.mode_var.set(mode_val)
        if 'temperature_setpoint_c' in last_sel:
            self.setpoint_var.set(str(last_sel.get('temperature_setpoint_c', '')))
        if 'temperature_sweep_c' in last_sel:
            self.sweep_var.set(str(last_sel.get('temperature_sweep_c', '')))
        if 'temperature_wait_after_s' in last_sel:
            self.wait_var.set(str(last_sel.get('temperature_wait_after_s', 0.0)))
        self._update_setpoint_display()
        self._toggle_controls()

    def build_last_selection_fragment(self) -> dict:
        return {
            'temperature_enabled': self.enabled_var.get(),
            'temperature_mode': self.mode_var.get(),
            'temperature_setpoint_c': self.setpoint_var.get(),
            'temperature_sweep_c': self.sweep_var.get(),
            'temperature_wait_after_s': self.wait_var.get(),
        }

    # --- Internal helpers ---
    def _post(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    def _toggle_controls(self):
        enabled = self.enabled_var.get()
        mode = self.mode_var.get()
        if mode not in ("Setpoint", "Sweep"):
            mode = "Setpoint"
            self.mode_var.set(mode)
        mode_state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.mode_cb.configure(state=mode_state)
        if mode == "Setpoint":
            self.setpoint_entry_label.grid()
            self.setpoint_entry.grid()
            self.sweep_entry_label.grid_remove()
            self.sweep_entry.grid_remove()
            self.setpoint_entry.configure(state=entry_state)
            self.sweep_entry.configure(state="disabled")
        else:
            self.sweep_entry_label.grid()
            self.sweep_entry.grid()
            self.sweep_entry.configure(state=entry_state)
            self.setpoint_entry_label.grid_remove()
            self.setpoint_entry.grid_remove()
            self.setpoint_entry.configure(state="disabled")
        self.wait_entry.configure(state=entry_state)
        self.set_button.configure(state="normal" if enabled else "disabled")
        if enabled:
            self._start_polling(self._safe_poll_interval())
            self._update_sweep_plot()
        else:
            self._stop_polling()

    def _set_temperature_now(self):
        mode = self.mode_var.get()
        if mode not in ("Setpoint", "Sweep"):
            mode = "Setpoint"
            self.mode_var.set(mode)
        try:
            if mode == "Setpoint":
                target = float(self.setpoint_var.get())
            else:
                sweep_vals = [float(tok.strip()) for tok in self.sweep_var.get().split(',') if tok.strip() != ""]
                if not sweep_vals:
                    raise ValueError("No sweep temperatures")
                target = sweep_vals[0]
        except Exception as exc:
            messagebox.showerror("Temperature", f"Invalid temperature value: {exc}")
            return
        self.runner.prober_set_temp(target)
        self.log(f"Temperature set to {target:.1f} C")
        if self.enabled_var.get():
            poll = self._safe_poll_interval()
            if poll > 0:
                self._start_polling(poll)
        self._update_setpoint_display()

    def _start_polling(self, poll_interval_s: float):
        self._stop_polling()
        interval_ms = max(int(poll_interval_s * 1000), 250)

        def poll():
            temp = self.runner.prober_get_temp()
            state = self.runner.get_thermo_state()
            setpoint = self.runner.get_temp_setpoint()
            if temp is None:
                self.value_var.set("N/A")
                color = "red"
            else:
                self.value_var.set(f"{temp:.1f} C")
                if state == "heating":
                    color = "orange"
                elif state == "cooling":
                    color = "blue"
                elif state == "controlling":
                    color = "green"
                elif state == "error" or state == "uncontrolled":
                    color = "red"
                else:
                    color = "black"
            self.temp_value_label.configure(foreground=color)
            self.setpoint_display_var.set("--" if setpoint is None else f"{setpoint:.1f} C")
            self._poll_job = self.root.after(interval_ms, poll)

        poll()

    def _stop_polling(self):
        if self._poll_job:
            self.root.after_cancel(self._poll_job)
            self._poll_job = None
        self.value_var.set("--")
        self.setpoint_display_var.set("--")

    def _on_step_start(self, idx: int):
        self.temp_tracker.step_started(idx)

    def _on_phase_change(self, phase: str, idx: int):
        self.temp_tracker.phase_change(phase, idx)

    def _record_sample(self, ts: float, temp: float, step_idx: int, source: str):
        if not self._run_active:
            return
        self.temp_tracker.record_sample(ts, temp, step_idx, source)
        self._update_sweep_plot()

    def _on_device_done(self, ts: float, step_idx: int, done: int, total: int):
        if not self._run_active:
            return
        self.temp_tracker.device_finished(ts, step_idx, done, total)
        self._update_sweep_plot()

    def _safe_poll_interval(self) -> float:
        return 2.0

    def _planned_temps(self):
        try:
            return [float(tok.strip()) for tok in self.sweep_var.get().split(",") if tok.strip()]
        except Exception:
            return []

    def _update_setpoint_display(self):
        self.setpoint_display_var.set("--")

    def _update_sweep_plot(self):
        if not self.enabled_var.get():
            self.profile_widget.grid_remove()
            return
        if not self._run_active or self.temp_tracker.run_start_ts is None:
            self._render_step_preview()
            return
        self._render_time_plot()

    def _render_step_preview(self):
        """Pre-run preview on step index for sweep mode."""
        mode = self.mode_var.get()
        try:
            vals = [float(tok.strip()) for tok in self.sweep_var.get().split(",") if tok.strip()]
            vals.append(vals[-1])
        except Exception:
            vals = []
        if mode != "Sweep":
            self.profile_widget.grid_remove()
            return
        ax = self.profile_ax
        ax.clear()
        xs = list(range(1, len(vals) + 1))
        ax.set_xticks(xs[:-1])
        ax.set_yticks(list(set(vals)))
        ax.step(xs, vals, linewidth=1, color='k', where='post')

        self.profile_canvas.draw_idle()
        self.profile_widget.grid(row=7, column=0, columnspan=2, sticky="ew", padx=2, pady=(2, 2))

    def _render_time_plot(self):
        """During a run, plot against time with actuals, setpoints, and predicted schedule."""
        ax = self.profile_ax
        ax.clear()
        ax.grid(True, linestyle="--", alpha=0.3)
        points = self.temp_tracker.ordered_points()
        sp_x, sp_y = self.temp_tracker.setpoint_series()
        pred_x, pred_y = self.temp_tracker.predicted_schedule()

        to_minutes = lambda arr: [x / 60.0 for x in arr]
        sp_x = to_minutes(sp_x)
        pred_x = to_minutes(pred_x)
        fmt = lambda x, _: (f"{int(x)}m" if x>=1 else "") + (f"{60*(x%1):.0f}s" if (x%1)>0 else "")
        ax.xaxis.set_major_formatter(FuncFormatter(fmt))

        # Build continuous red/green lines with NaN breaks when state switches
        red_x, red_y, green_x, green_y = [], [], [], []
        for t_rel, temp, is_meas in points:
            t_min = t_rel / 60.0
            if is_meas:
                red_x.append(float('nan')); red_y.append(float('nan'))
                green_x.append(t_min); green_y.append(temp)
            else:
                green_x.append(float('nan')); green_y.append(float('nan'))
                red_x.append(t_min); red_y.append(temp)

        if pred_x and pred_y:
            ax.step(pred_x, pred_y, where="post", color="gray", linestyle="--", linewidth=1)
        if sp_x and sp_y:
            ax.step(sp_x, sp_y, where="post", color="black", linewidth=1)
        if red_x:
            ax.plot(red_x, red_y, color="red", linewidth=1)
        if green_x:
            ax.plot(green_x, green_y, color="green", linewidth=1)

        max_x = 0.0
        for seq in (pred_x, red_x, green_x, sp_x):
            if seq:
                max_x = max(max_x, max(seq))
        ax.set_xlim(left=0.0, right=max(max_x * 1.05, 1.0))
        self.profile_canvas.draw_idle()
        self.profile_widget.grid(row=7, column=0, columnspan=2, sticky="ew", padx=2, pady=(2, 2))
