"""
PUND Fatigue Procedure - High cycle count pulsing with sparse measurements.

Sends up to 1e12 square cycles using WGFMU hardware repetition.
Optionally measures at N points (linear or log spaced) throughout the run.
TODO
"""
import time
import numpy as np
from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, WGFMUChannel, parameter, action
from instrumentio.codes import (
	WGFMU_FORCE_VOLTAGE_RANGE_AUTO,
	WGFMU_MEASURE_ENABLED_ENABLE,
	WGFMU_MEASURE_EVENT_DATA_AVERAGED,
	WGFMU_MEASURE_MODE_CURRENT,
	WGFMU_MEASURE_MODE_VOLTAGE,
	WGFMU_OPERATION_MODE_FASTIV,
	WGFMU_OPERATION_MODE_PG,
)
from instrumentio.constants import (
	WGFMU_MEASURE_VOLTAGE_RANGES,
	WGFMU_MEASURE_CURRENT_RANGES,
)


def _preview_sequence(ui):
	"""Preview this procedure's schedule using the current form settings."""
	from tkinter import messagebox
	try:
		settings = ui.collect_settings()
		cycle_count = float(settings['fatigue_count'])
		frequency = float(settings['fatigue_freq'])
		spacing = settings['read_spacing']
		if spacing == 'linear':
			read_count = int(float(settings['linear_read_count']))
			read_line = f"Linear Reads: {read_count} (plus cycle 0)"
		else:
			read_count = int(float(settings['reads_per_decade']))
			read_line = f"Reads per Decade: {read_count}"
		preview = PUNDFatigueProcedure.get_preview_info(cycle_count, frequency, spacing, read_count)
	except (TypeError, ValueError) as exc:
		messagebox.showerror("Invalid Parameters", f"Could not parse parameters: {exc}", parent=ui.root)
		return
	total_sec = preview['total_duration']
	if total_sec < 60:
		duration = f"{total_sec:.1f} s"
	elif total_sec < 3600:
		duration = f"{total_sec / 60:.1f} min"
	else:
		duration = f"{total_sec / 3600:.2f} h"
	lines = [
		f"Cycle Count: {cycle_count:.2e}", f"Frequency: {frequency:.0f} Hz",
		read_line, f"Decades: {preview['decades']:.1f}", "",
		f"Total Measurements: {preview['total_measurements']}",
		f"Estimated Duration: {duration}", "", "Measurement at cycles:",
	]
	cycles = preview['measure_cycles']
	if len(cycles) <= 20:
		lines.append("  " + ", ".join(str(c) for c in cycles))
	else:
		lines.extend([
			"  " + ", ".join(str(c) for c in cycles[:10]),
			f"  ... ({len(cycles) - 20} more)",
			"  " + ", ".join(str(c) for c in cycles[-10:]),
		])
	messagebox.showinfo("PUND Fatigue Preview", "\n".join(lines), parent=ui.root)


class PUNDFatigueProcedure(MeasurementProcedure):
	NAME = "PUNDFatigue"
	PARAMETERS = (
		parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
		parameter('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 101, WGFMUChannel),
		parameter('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 102, WGFMUChannel),
		parameter('v_pos', 'Vpos (V)', 1.0, float,
		          help='Peak voltage of the positive pulses, absolute (not added to Vbase).'),
		parameter('v_base', 'Vbase (V)', 0.0, float,
		          help='Voltage between pulses.'),
		parameter('v_neg', 'Vneg (V)', -1.0, float,
		          help='Peak voltage of the negative pulses, absolute (not added to Vbase).'),
        parameter('hold_base', 'Hold Base V continuously', True, bool), # hold baseline for the entire time?
		parameter('fatigue_freq', 'Fatigue Frequency (Hz)', 1e4, float,
		          help='Square: each level lasts 1/f. Triangle and PUND: sets the ramp speed; the tallest pulse lasts as long as at this frequency.'),
        parameter('fatigue_delay', 'Fatigue Cycle Delay (s)', 0.0, float), # wait time between fatigue pulses
		parameter('fatigue_count', 'Fatigue Cycle Count', 1e6, float), # total fatigue cycle count
		parameter('fatigue_pulse_type', 'Type of Fatigue Cycle', 'square',
            Choice((('square', 'Square'), ('triangle', 'Triangle'), ('pund', 'PUND')))),
        parameter('read_pulse_freq', 'Read Frequency (Hz)', 1e4, float,
                  help='Sets the ramp speed of the read pulses; the tallest pulse lasts as long as at this frequency.'),
        parameter('read_pulse_type', 'Type of Read Cycle', 'pund',
                  Choice((('pund', 'PUND'), ('pn', 'PN'), ('both', 'PN+PUND')))),
		parameter('read_spacing', 'Read Spacing', 'log',
		          Choice((('log', 'Log (per decade)'), ('linear', 'Linear')))),
		parameter('reads_per_decade', 'Read Cycles per Decade', 10, int,
		          help='One read before any fatigue, then reads at equal steps inside each decade: '
		               '10 gives cycles 0, 1, 2, ..., 10, 20, ..., 100, ...',
		          enabled_when=('read_spacing', 'log')),
		parameter('linear_read_count', 'Read Cycles in Total', 10, int,
		          help='One read before any fatigue, then this many at equal steps over the whole run: '
		               '10 over 1e6 cycles gives cycles 0, 1e5, 2e5, ..., 1e6.',
		          enabled_when=('read_spacing', 'linear')),
        parameter('meas_range_1', 'Meas Range Ch1 (V)', WGFMU_MEASURE_VOLTAGE_RANGES[0][0],
                  Choice(WGFMU_MEASURE_VOLTAGE_RANGES, int)),
        parameter('meas_range_2', 'Meas Range Ch2 (I)', WGFMU_MEASURE_CURRENT_RANGES[0][0],
                  Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
	)
	UI_ACTIONS = (
		action("Preview Sequence", _preview_sequence),
	)


	MIN_INTERVAL = 1e-8
	RESOLUTION = 1e-8
	STATUS_COMPLETED = 10000
	POST_COMPLETION_DRAIN_TIMEOUT_S = 30.0
	PUND_SIGNS = (-1, 1, 1, -1, -1)

	def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
		super().__init__(settings, output_root, output_relative, runner, fallback_root)
		self.fatigue_count_int = int(float(self.fatigue_count))
		# The tallest pulse height. Triangular pulses all ramp at the slew rate this height gets at the set frequency.
		self.vmax = max(abs(self.v_pos - self.v_base), abs(self.v_neg - self.v_base))
		self._validate_settings()

	def _validate_settings(self):
		if self.vmax == 0.0:
			raise ValueError("Vpos or Vneg must differ from Vbase.")
		if self.fatigue_freq <= 0:
			raise ValueError("fatigue_freq must be > 0")
		if self.read_pulse_freq <= 0:
			raise ValueError("read_pulse_freq must be > 0")
		if self.fatigue_delay < 0:
			raise ValueError("fatigue_delay must be >= 0")
		if self.fatigue_count_int < 1:
			raise ValueError("fatigue_count must be >= 1")
		if self.read_spacing not in ('log', 'linear'):
			raise ValueError(f"Invalid read_spacing: {self.read_spacing!r}")
		if self.reads_per_decade <= 0:
			raise ValueError("reads_per_decade must be > 0")
		if self.linear_read_count <= 0:
			raise ValueError("linear_read_count must be > 0")
		if self.fatigue_pulse_type not in ('square', 'triangle', 'pund'):
			raise ValueError(f"Invalid fatigue_pulse_type: {self.fatigue_pulse_type!r}")
		if self.read_pulse_type not in ('pund', 'pn', 'both'):
			raise ValueError(f"Invalid read_pulse_type: {self.read_pulse_type!r}")

	def _idle_voltage(self):
		return self.v_base if self.hold_base else 0.0

	def _append_square_level(self, vectors, level, duration):
		"""Append a fast transition to level followed by a constant hold."""
		if duration <= 0:
			return
		edge = min(self.MIN_INTERVAL, duration)
		vectors.append((edge, level))
		hold = duration - edge
		if hold > 0:
			vectors.append((hold, level))

	def _append_idle_hold(self, vectors, duration):
		if duration > 0:
			self._append_square_level(vectors, self._idle_voltage(), duration)

	def _build_square_fatigue_vectors(self):
		"""Square PN fatigue cycle: positive segment, negative segment, optional idle delay."""
		segment = 1.0 / self.fatigue_freq
		vectors = []
		self._append_square_level(vectors, self.v_pos, segment)
		self._append_square_level(vectors, self.v_neg, segment)
		self._append_idle_hold(vectors, self.fatigue_delay)
		return vectors

	def _build_triangle_fatigue_vectors(self):
		"""Triangular PN fatigue pulses, then optional idle delay."""
		vectors = self._build_triangular_pn_vectors(self.fatigue_freq)
		self._append_idle_hold(vectors, self.fatigue_delay)
		return vectors

	def _build_triangular_pulse_vectors(self, frequency, signs):
		"""Triangular PUND timing: ramp out, ramp back, base hold.

		The tallest pulse ramps for 0.4T each way; shorter pulses ramp at the same speed.
		"""
		T = 1.0 / frequency
		gap = 0.2 * T
		edge = 0.1 * T

		vectors = [(edge, self.v_base)]
		for sign in signs:
			level = self.v_pos if sign > 0 else self.v_neg
			ramp = 0.4 * T * abs(level - self.v_base) / self.vmax
			vectors += [
				(ramp, level),
				(ramp, self.v_base),
				(gap, self.v_base),
			]
		vectors[-1] = (edge, self._idle_voltage())
		return vectors

	def _build_triangular_pn_vectors(self, frequency):
		"""Triangular PN pulses with idle only before and after the PN pair.

		The tallest pulse ramps for 0.5T each way; shorter pulses ramp at the same speed.
		"""
		T = 1.0 / frequency
		edge = 0.1 * T
		vectors = [(edge, self.v_base)]
		for level in (self.v_pos, self.v_neg):
			ramp = 0.5 * T * abs(level - self.v_base) / self.vmax
			vectors.append((ramp, level))
			vectors.append((ramp, self.v_base))
		vectors.append((edge, self._idle_voltage()))
		return vectors

	def _build_fatigue_vectors(self):
		if self.fatigue_pulse_type == 'square':
			return self._build_square_fatigue_vectors()
		if self.fatigue_pulse_type == 'triangle':
			return self._build_triangle_fatigue_vectors()
		vectors = self._build_triangular_pulse_vectors(self.fatigue_freq, self.PUND_SIGNS)
		self._append_idle_hold(vectors, self.fatigue_delay)
		return vectors

	def _build_read_vectors(self):
		if self.read_pulse_type == 'pn':
			return self._build_triangular_pn_vectors(self.read_pulse_freq)
		if self.read_pulse_type == 'pund':
			return self._build_triangular_pulse_vectors(self.read_pulse_freq, self.PUND_SIGNS)

		vectors = []
		vectors.extend(self._build_triangular_pn_vectors(self.read_pulse_freq))
		self._append_idle_hold(vectors, 1.0 / self.read_pulse_freq)
		vectors.extend(self._build_triangular_pulse_vectors(self.read_pulse_freq, self.PUND_SIGNS))
		return vectors

	def _read_phase_spans(self):
		"""Return plotted read phases as (key, label, start_s, end_s)."""
		pn_duration = sum(dt for dt, _ in self._build_triangular_pn_vectors(self.read_pulse_freq))
		pund_duration = sum(
			dt for dt, _ in self._build_triangular_pulse_vectors(self.read_pulse_freq, self.PUND_SIGNS)
		)

		if self.read_pulse_type == 'pn':
			return [('pn', 'PN', 0.0, pn_duration)]
		if self.read_pulse_type == 'pund':
			return [('pund', 'PUND', 0.0, pund_duration)]

		gap_duration = 1.0 / self.read_pulse_freq
		pund_start = pn_duration + gap_duration
		return [
			('pn', 'PN', 0.0, pn_duration),
			('pund', 'PUND', pund_start, pund_start + pund_duration),
		]

	@staticmethod
	def _phase_for_time(read_time_s, phase_spans):
		for phase in phase_spans:
			_key, _label, start, end = phase
			if start <= read_time_s < end:
				return phase
		if phase_spans and read_time_s == phase_spans[-1][3]:
			return phase_spans[-1]
		return None

	@staticmethod
	def _phase_color(phase_key, intensity):
		shade = 0.45 + 0.55 * intensity
		if phase_key == 'pn':
			return (0.12 * shade, 0.47 * shade, 0.71 * shade)
		return (1.0 * shade, 0.5 * shade, 0.05 * shade)

	def _iv_vectors_for(self, vectors):
		# Channel 2 always stays at 0 V; all PG/base/fatigue/read voltage is applied only on channel 1.
		return [(dt, 0.0) for dt, _ in vectors]

	def _sample_interval(self):
		raw_interval = 1e-3 / self.read_pulse_freq
		sample_interval = max(raw_interval, self.MIN_INTERVAL)
		sample_interval = round(sample_interval / self.RESOLUTION) * self.RESOLUTION
		return max(sample_interval, self.MIN_INTERVAL)

	@staticmethod
	def _compute_read_cycles(cycle_count: int, spacing: str, read_count: int) -> list[int]:
		"""Return the cycles to read at: a read at cycle N comes after N fatigue cycles.

		Cycle 0 (before any fatigue) and the final cycle are always included.

		'log': each decade 10^d to 10^(d+1) gets read_count reads at the multiples of
		10^(d+1)/read_count from 10^d on, rounded to whole cycles: 2 gives 0, 5, 10, 50, 100, ...;
		10 gives 0, 1, 2, ..., 10, 20, ..., 100, ... The first decade has fewer reads when read_count > 10.

		'linear': read_count reads at equal steps of cycle_count/read_count, after the one at cycle 0:
		10 over 1e6 cycles gives 0, 1e5, 2e5, ..., 1e6.
		"""
		n = int(cycle_count)
		count = int(read_count)
		if count <= 0 or n < 1:
			return []
		cycles = {0, n}
		if spacing == 'linear':
			cycles.update(int(round(k * n / count)) for k in range(1, count + 1))
			return sorted(cycles)
		decade = 0
		while 10 ** decade < n:
			step = 10 ** (decade + 1) / count
			for k in range(1, count + 1):
				cycle = int(round(k * step))
				if 10 ** decade <= cycle <= n:
					cycles.add(cycle)
			decade += 1
		return sorted(cycles)

	def _read_cycles(self):
		read_count = self.linear_read_count if self.read_spacing == 'linear' else self.reads_per_decade
		return self._compute_read_cycles(self.fatigue_count_int, self.read_spacing, read_count)

	def _configure_wgfmu(self, wgfmu):
		wgfmu.clear()
		wgfmu.connect(self.channel_1)
		wgfmu.connect(self.channel_2)

		wgfmu.set_operation_mode(self.channel_1, WGFMU_OPERATION_MODE_PG)
		wgfmu.set_operation_mode(self.channel_2, WGFMU_OPERATION_MODE_FASTIV)
		wgfmu.set_force_voltage_range(self.channel_1, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)
		wgfmu.set_force_voltage_range(self.channel_2, WGFMU_FORCE_VOLTAGE_RANGE_AUTO)

		wgfmu.set_measure_mode(self.channel_1, WGFMU_MEASURE_MODE_VOLTAGE)
		wgfmu.set_measure_mode(self.channel_2, WGFMU_MEASURE_MODE_CURRENT)
		wgfmu.set_measure_voltage_range(self.channel_1, self.meas_range_1)
		wgfmu.set_measure_current_range(self.channel_2, self.meas_range_2)
		wgfmu.set_measure_enabled(self.channel_1, WGFMU_MEASURE_ENABLED_ENABLE)
		wgfmu.set_measure_enabled(self.channel_2, WGFMU_MEASURE_ENABLED_ENABLE)

	@staticmethod
	def _format_cycle_count(count):
		if count <= 1000:
			return str(int(count))
		mantissa, exponent = f"{count:.4e}".split('e')
		return f"{mantissa.rstrip('0').rstrip('.')}e{int(exponent)}"

	def _report_fatigue_progress(self, cycles_sent):
		self.report_progress(
			cycles_sent, self.fatigue_count_int, "Fatigue cycles sent",
			count_labels=(self._format_cycle_count(cycles_sent),
			              self._format_cycle_count(self.fatigue_count_int)),
		)

	@staticmethod
	def _add_vectors(wgfmu, pattern_name, vectors):
		for dt, voltage in vectors:
			if dt > 0:
				wgfmu.add_vector(pattern_name, dt, voltage)

	def _create_pattern_pair(self, wgfmu, pg_name, iv_name, initial_pg, pg_vectors, measure_points=None, sample_interval=None, measure_start=0.0):
		wgfmu.create_pattern(pg_name, initial_pg)
		self._add_vectors(wgfmu, pg_name, pg_vectors)

		wgfmu.create_pattern(iv_name, 0.0)
		self._add_vectors(wgfmu, iv_name, self._iv_vectors_for(pg_vectors))

		if measure_points is not None and sample_interval is not None:
			wgfmu.set_measure_event(
				pg_name,
				"meas",
				measure_start,
				measure_points,
				sample_interval,
				sample_interval,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)
			wgfmu.set_measure_event(
				iv_name,
				"meas",
				measure_start,
				measure_points,
				sample_interval,
				sample_interval,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)

	def _plot_sources(self, cycle_num, phase_key):
		return (
			f"V_{cycle_num}_{phase_key}",
			f"I_{cycle_num}_{phase_key}",
			f"IV_{cycle_num}_{phase_key}",
			f"QV_{cycle_num}_{phase_key}",
		)

	def _configure_plot(self, device, read_cycles, read_duration):
		max_cycles_to_plot = min(len(read_cycles), 50)
		step_plot = max(1, len(read_cycles) // max_cycles_to_plot)
		plot_indices = list(range(0, len(read_cycles), step_plot))
		if (len(read_cycles) - 1) not in plot_indices:
			plot_indices.append(len(read_cycles) - 1)

		max_cycle = read_cycles[-1] if read_cycles else 1
		log_max = np.log10(max(max_cycle, 1))
		elements = []
		iv_elements = []
		qv_elements = []
		source_map = {}
		phase_spans = self._read_phase_spans()

		for read_idx in plot_indices:
			cycle_num = read_cycles[read_idx]
			if self.read_spacing == 'linear':
				progress = cycle_num / max_cycle
			else:
				progress = np.log10(max(cycle_num, 1)) / max(log_max, 1)
			intensity = 0.2 + 0.7 * progress
			show = read_idx == 0 or read_idx == len(read_cycles) - 1
			label = f"cycle {cycle_num}"
			source_map[read_idx] = {}
			for phase_key, phase_label, _start, _end in phase_spans:
				color = self._phase_color(phase_key, intensity)
				v_source, i_source, iv_source, qv_source = self._plot_sources(cycle_num, phase_key)
				series_label = f"{phase_label} {label}"
				elements.append(Curve(v_source, color=color, yaxis=0,
				                      legend_label=f"V ({series_label})", show_in_legend=show))
				elements.append(Curve(i_source, color=color, yaxis=1,
				                      legend_label=f"I ({series_label})", show_in_legend=show))
				iv_elements.append(Curve(iv_source, color=color,
				                         legend_label=series_label, show_in_legend=show))
				qv_elements.append(Curve(qv_source, color=color,
				                         legend_label=series_label, show_in_legend=show))
				source_map[read_idx][phase_key] = (v_source, i_source, iv_source, qv_source)

		v_margin = max(self.vmax * 0.1, 0.1)
		y_min = min(0.0, self.v_pos, self.v_neg, self.v_base) - v_margin
		y_max = max(0.0, self.v_pos, self.v_neg, self.v_base) + v_margin

		self.runner.configure_plot(f'PUND Fatigue Overlay - {device.name}', [
			PlotDef("pund_fat", row=0, col=0, colspan=2,
			        xlabel="Time (s)",
			        ylabels=("Voltage (V)", "Current (uA)"),
			        xlim=(0, read_duration),
			        ylims=((y_min, y_max), None),
			        elements=elements),
			PlotDef("iv_loop", row=1, col=0,
			        xlabel="Voltage (V)",
			        ylabels=("Current (uA)",),
			        elements=iv_elements),
			PlotDef("qv_loop", row=1, col=1,
			        xlabel="Voltage (V)",
			        ylabels=("Charge (nC)",),
			        elements=qv_elements),
		], row_ratios=[2.0, 1.0])

		return source_map

	@staticmethod
	def get_preview_info(cycle_count: float, frequency: float, spacing: str, read_count: int) -> dict:
		read_cycles = PUNDFatigueProcedure._compute_read_cycles(int(cycle_count), spacing, int(read_count))
		return {
			'measure_cycles': read_cycles,
			'total_measurements': len(read_cycles),
			'pattern_duration': 2.0 / frequency if frequency > 0 else 0.0,
			'total_duration': cycle_count * (2.0 / frequency if frequency > 0 else 0.0),
			'decades': np.log10(max(int(cycle_count), 1)),
		}

	def measure(self, device):
		b1500 = self.b1500
		wgfmu = b1500.wgfmu
		self.check_stop(b1500)

		read_cycles = self._read_cycles()
		if not read_cycles:
			raise ValueError("No read cycles were generated.")

		fatigue_vectors = self._build_fatigue_vectors()
		read_vectors = self._build_read_vectors()
		fatigue_duration = sum(dt for dt, _ in fatigue_vectors)
		read_duration = sum(dt for dt, _ in read_vectors)
		settle_duration = 1.0 / self.fatigue_freq
		phase_spans = self._read_phase_spans()
		sample_interval = self._sample_interval()
		sample_points = max(1, int(round(read_duration / sample_interval)))
		expected_total = sample_points * len(read_cycles)
		source_map = self._configure_plot(device, read_cycles, read_duration)
		self._report_fatigue_progress(0)

		total_time = (
			(self.fatigue_count_int * fatigue_duration)
			+ (len(read_cycles) * settle_duration)
			+ (len(read_cycles) * read_duration)
		)
		self.log(f"Starting PUND Fatigue on {device.name}")
		self.log(
			f"  {self.fatigue_count_int:.2e} {self.fatigue_pulse_type} fatigue cycles, "
			f"Vpos={self.v_pos:g} V, Vbase={self.v_base:g} V, Vneg={self.v_neg:g} V, reads={len(read_cycles)}"
		)
		self.log(
			f"  Fatigue duration/cycle: {fatigue_duration:.6g} s, "
			f"read duration: {read_duration:.6g} s, sample interval: {sample_interval:.9g} s"
		)
		self.log(f"  Estimated waveform duration: {total_time:.1f} s")

		ts = self.get_run_timestamp()
		initial_pg = self._idle_voltage()

		try:
			self._configure_wgfmu(wgfmu)
			fat_pg = f"FAT_FAT_PG_{ts}"
			fat_iv = f"FAT_FAT_IV_{ts}"
			read_pg = f"FAT_READ_PG_{ts}"
			read_iv = f"FAT_READ_IV_{ts}"

			self._create_pattern_pair(wgfmu, fat_pg, fat_iv, initial_pg, fatigue_vectors)
			self._create_pattern_pair(
				wgfmu,
				read_pg,
				read_iv,
				initial_pg,
				[(settle_duration, initial_pg), *read_vectors],
				measure_points=sample_points,
				sample_interval=sample_interval,
				measure_start=settle_duration,
			)

			prev_cycle = 0
			for cycle_num in read_cycles:
				self.check_stop(b1500)
				fatigue_reps = cycle_num - prev_cycle
				if fatigue_reps > 0:
					wgfmu.add_sequence(self.channel_1, fat_pg, float(fatigue_reps))
					wgfmu.add_sequence(self.channel_2, fat_iv, float(fatigue_reps))
				wgfmu.add_sequence(self.channel_1, read_pg, 1.0)
				wgfmu.add_sequence(self.channel_2, read_iv, 1.0)
				prev_cycle = cycle_num

			remaining = self.fatigue_count_int - prev_cycle
			if remaining > 0:
				wgfmu.add_sequence(self.channel_1, fat_pg, float(remaining))
				wgfmu.add_sequence(self.channel_2, fat_iv, float(remaining))

			cleanup_pg = f"FAT_CLEANUP_PG_{ts}"
			cleanup_iv = f"FAT_CLEANUP_IV_{ts}"
			self._create_pattern_pair(wgfmu, cleanup_pg, cleanup_iv, initial_pg, [(1e-4, 0.0)])
			wgfmu.add_sequence(self.channel_1, cleanup_pg, 1.0)
			wgfmu.add_sequence(self.channel_2, cleanup_iv, 1.0)

			self.check_stop(b1500)
			wgfmu.execute()

			plotted_count = 0
			data_ch1 = []
			data_ch2 = []
			read_start_times_s: dict[int, float] = {}
			i_baseline_samples: dict[int, list] = {}
			i_baseline: dict[int, float] = {}
			q_accum: dict[tuple[int, str], float] = {}
			last_t_per_phase: dict[tuple[int, str], float] = {}
			last_progress_time = time.monotonic()

			while True:
				self.check_stop(b1500)
				status, _elapsed, _total = wgfmu.get_status()
				measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2, expected_total)

				if available > plotted_count:
					batches: dict[tuple[int, str], dict] = {}

					# One call per channel for all new samples; per-sample calls cannot keep up with closely spaced reads.
					samples_v = wgfmu.read_chunk(self.channel_1, plotted_count, available - plotted_count)
					samples_i = wgfmu.read_chunk(self.channel_2, plotted_count, available - plotted_count)
					for sample_index, ((t_v, voltage), (t_i, current)) in enumerate(zip(samples_v, samples_i), plotted_count):
						data_ch1.append((t_v, voltage))
						data_ch2.append((t_i, current))

						read_idx = sample_index // sample_points
						sample_in_read = sample_index % sample_points
						if sample_in_read == sample_points - 1:
							self._report_fatigue_progress(read_cycles[read_idx])
						timestamp = t_v if t_v is not None else t_i
						if timestamp is None:
							read_time_s = sample_in_read * sample_interval
						else:
							read_start_s = read_start_times_s.setdefault(read_idx, timestamp)
							read_time_s = max(0.0, timestamp - read_start_s)
						if read_idx >= len(read_cycles) or read_idx not in source_map:
							continue

						phase = self._phase_for_time(read_time_s, phase_spans)
						if phase is None:
							continue
						phase_key, _phase_label, _start, _end = phase
						if phase_key not in source_map[read_idx]:
							continue

						batch_key = (read_idx, phase_key)
						batch = batches.setdefault(batch_key, {'v': [], 'i': [], 'iv': [], 'qv': []})
						batch['v'].append((read_time_s, voltage))
						batch['i'].append((read_time_s, current * 1e6))

						if read_idx not in i_baseline:
							samples = i_baseline_samples.setdefault(read_idx, [])
							if len(samples) < 50:
								samples.append(current)
							if len(samples) == 50:
								i_baseline[read_idx] = float(np.mean(samples))

						if read_idx in i_baseline:
							current_adj = -(current - i_baseline[read_idx])
							batch['iv'].append((voltage, current_adj * 1e6))
							if batch_key not in q_accum:
								q_accum[batch_key] = 0.0
								last_t_per_phase[batch_key] = read_time_s
							else:
								dt = read_time_s - last_t_per_phase[batch_key]
								if dt > 0:
									q_accum[batch_key] += current_adj * dt
								last_t_per_phase[batch_key] = read_time_s
							batch['qv'].append((voltage, q_accum[batch_key] * 1e9))

					plot_batch = {}
					for (read_idx, phase_key), batch in batches.items():
						v_source, i_source, iv_source, qv_source = source_map[read_idx][phase_key]
						plot_batch[v_source] = batch['v']
						plot_batch[i_source] = batch['i']
						plot_batch[iv_source] = batch['iv']
						plot_batch[qv_source] = batch['qv']
					if plot_batch:
						self.runner.plot.append_batch(plot_batch)

					plotted_count = len(data_ch1)
					last_progress_time = time.monotonic()
					continue

				if status == self.STATUS_COMPLETED:
					if plotted_count >= expected_total:
						break
					if (time.monotonic() - last_progress_time) > self.POST_COMPLETION_DRAIN_TIMEOUT_S:
						self.log(
							"Warning: WGFMU completed before all read samples were available "
							f"({plotted_count}/{expected_total} samples)."
						)
						break

				time.sleep(0.05)

			all_rows = []
			for read_idx, cycle_num in enumerate(read_cycles):
				offset = read_idx * sample_points
				for i in range(sample_points):
					row_idx = offset + i
					if row_idx < len(data_ch1) and row_idx < len(data_ch2):
						t_v, voltage = data_ch1[row_idx]
						t_i, current = data_ch2[row_idx]
						timestamp = t_v if t_v is not None else t_i
						all_rows.append([cycle_num, timestamp, voltage, current])

			self.save_measurement_outputs(
				all_rows,
				"PUND_Fatigue",
				device,
				["Cycle", "Time_s", "Voltage_V", "Current_A"],
				save_plot=bool(all_rows),
			)

			self.log(
				f"PUND Fatigue complete: {self.fatigue_count_int:.2e} cycles, "
				f"{len(read_cycles)} reads, {len(all_rows)} samples"
			)

		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
