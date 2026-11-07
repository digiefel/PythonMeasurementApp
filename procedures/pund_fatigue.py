"""
PUND Fatigue Procedure - High cycle count pulsing with sparse measurements.

Sends up to 1e12 fatigue cycles using WGFMU hardware repetition, all in one WGFMU
run. At each read cycle (linear or log spaced, always including cycle 0 and the
last cycle) it reads the device at every read frequency, in the order typed:
PN, PUND, or PN then PUND. Each read starts after one read period at the idle voltage.

Every read is saved as its own CSV as soon as it is measured:
``<base>_PN_<frequency>Hz_c<cycle>.csv`` and ``<base>_PUND_<frequency>Hz_c<cycle>.csv``,
for example ``<base>_PUND_10kHz_c100.csv``.

The live plot has, per read frequency, a voltage and current vs time plot over the
full width, and below those an I-V and a Q-V plot per frequency. PN reads are blue,
PUND reads orange, darker for early cycles and brighter for later ones.
"""
import time
import numpy as np
from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, ValueList, WGFMUChannel, parameter, action
from si_utils import format_si_compact, parse_si_list
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

HEADERS = ["Cycle", "Time_s", "Voltage_V", "Current_A"]
# The current offset of a read is the mean of its first samples, taken at Vbase before the first pulse.
BASELINE_POINTS = 50


def _preview_sequence(ui):
	"""Preview this procedure's schedule using the current form settings."""
	from tkinter import messagebox
	try:
		# Built only to check the settings and lay out the run; it touches no instrument.
		proc = PUNDFatigueProcedure(ui.collect_settings(), '', '', None)
	except (TypeError, ValueError) as exc:
		messagebox.showerror("Invalid Parameters", f"Could not parse parameters: {exc}", parent=ui.root)
		return
	if proc.read_spacing == 'linear':
		read_line = f"Linear Reads: {proc.linear_read_count} (plus cycle 0)"
	else:
		read_line = f"Reads per Decade: {proc.reads_per_decade}"
	cycles = proc._read_cycles()
	# One measurement (and file) per read cycle, read frequency and read type.
	measurements = len(cycles) * len(proc.read_frequencies) * len(proc.READ_KINDS[proc.read_pulse_type])
	# The reads take milliseconds; the fatigue cycles set the duration.
	total_sec = proc.fatigue_count_int * sum(dt for dt, _ in proc._build_fatigue_vectors())
	if total_sec < 60:
		duration = f"{total_sec:.1f} s"
	elif total_sec < 3600:
		duration = f"{total_sec / 60:.1f} min"
	else:
		duration = f"{total_sec / 3600:.2f} h"
	lines = [
		f"Cycle Count: {proc.fatigue_count_int:.2e}", f"Frequency: {proc.fatigue_freq:.0f} Hz",
		read_line, f"Decades: {np.log10(proc.fatigue_count_int):.1f}", "",
		f"Total Measurements: {measurements}",
		f"Estimated Duration: {duration}", "", "Measurement at cycles:",
	]
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
        parameter('read_pulse_freq', 'Read Frequencies (Hz)', '1e4', ValueList,
                  help='Comma-separated, e.g. "1k, 10k". Every read cycle reads at each frequency, in the order typed. '
                       'Sets the ramp speed of the read pulses; the tallest pulse lasts as long as at this frequency.'),
        parameter('read_pulse_type', 'Type of Read Cycle', 'pund',
                  Choice((('pund', 'PUND'), ('pn', 'PN'), ('both', 'PN+PUND')))),
        parameter('pund_gap', 'PUND Gap (periods)', 0.2, float,
                  help='Time at Vbase between the triangles of a PUND, as a fraction of its period '
                       '(read or fatigue). 0 puts the triangles back to back.'),
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
	READ_KINDS = {'pn': ('PN',), 'pund': ('PUND',), 'both': ('PN', 'PUND')}

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
		try:
			self.read_frequencies = parse_si_list(str(self.read_pulse_freq))
		except ValueError:
			raise ValueError(f"Read Frequencies must be comma-separated numbers, got {self.read_pulse_freq!r}") from None
		if not self.read_frequencies or min(self.read_frequencies) <= 0:
			raise ValueError("Read Frequencies needs at least one frequency, all > 0")
		if len(set(self.read_frequencies)) < len(self.read_frequencies):
			raise ValueError("Read Frequencies lists a frequency twice; each one gets its own files")
		if self.pund_gap < 0:
			raise ValueError("pund_gap must be >= 0")
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
		"""Triangular PUND timing: ramp out, ramp back, base hold of pund_gap periods.

		The tallest pulse ramps for 0.4T each way; shorter pulses ramp at the same speed.
		"""
		T = 1.0 / frequency
		gap = self.pund_gap * T
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

	def _build_read_kind_vectors(self, frequency, kind):
		if kind == 'PN':
			return self._build_triangular_pn_vectors(frequency)
		return self._build_triangular_pulse_vectors(frequency, self.PUND_SIGNS)

	def _build_read_vectors(self, frequency):
		"""One read as a single waveform, as FORCFatigue and FTJFatigue run it: PN and/or PUND,
		with one period at the idle voltage in between."""
		vectors = []
		for kind in self.READ_KINDS[self.read_pulse_type]:
			if vectors:
				self._append_idle_hold(vectors, 1.0 / frequency)
			vectors.extend(self._build_read_kind_vectors(frequency, kind))
		return vectors

	@staticmethod
	def _phase_color(phase_key, intensity):
		shade = 0.45 + 0.55 * intensity
		if phase_key == 'pn':
			return (0.12 * shade, 0.47 * shade, 0.71 * shade)
		return (1.0 * shade, 0.5 * shade, 0.05 * shade)

	def _iv_vectors_for(self, vectors):
		# Channel 2 always stays at 0 V; all PG/base/fatigue/read voltage is applied only on channel 1.
		return [(dt, 0.0) for dt, _ in vectors]

	def _sample_interval(self, frequency):
		raw_interval = 1e-3 / frequency
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

	@staticmethod
	def _progress_timeline(reads, fatigue_duration):
		"""Waveform time and fatigue cycles sent, at the start and end of every read.

		reads: (cycle, duration_s) of every read, in run order. np.interp over the result
		turns the WGFMU's elapsed time into cycles sent: they grow during fatigue and hold during reads.
		"""
		times, cycles = [0.0], [0]
		t, prev_cycle = 0.0, 0
		for cycle, duration in reads:
			t += (cycle - prev_cycle) * fatigue_duration
			times += [t, t + duration]
			cycles += [cycle, cycle]
			t += duration
			prev_cycle = cycle
		return np.array(times), np.array(cycles)

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

	def _configure_plot(self, device, reads, plotted, time_spans):
		"""Per frequency: V and I vs time over the full width, then a row with I-V and Q-V.

		Read r of `reads` draws into sources V_r, I_r, IV_r and QV_r.
		"""
		read_cycles = sorted({cycle for cycle, _, _ in reads})
		max_cycle = max(read_cycles[-1], 1)
		log_max = np.log10(max_cycle)
		panels = {(frequency, panel): [] for frequency in self.read_frequencies for panel in ('time', 'iv', 'qv')}
		for read_idx in sorted(plotted):
			cycle, frequency, kind = reads[read_idx]
			if self.read_spacing == 'linear':
				progress = cycle / max_cycle
			else:
				progress = np.log10(max(cycle, 1)) / max(log_max, 1)
			color = self._phase_color(kind.lower(), 0.2 + 0.7 * progress)
			show = cycle in (read_cycles[0], read_cycles[-1])
			label = f"{kind} cycle {cycle}"
			panels[frequency, 'time'] += [
				Curve(f"V_{read_idx}", color=color, yaxis=0, legend_label=f"V ({label})", show_in_legend=show),
				Curve(f"I_{read_idx}", color=color, yaxis=1, legend_label=f"I ({label})", show_in_legend=show),
			]
			panels[frequency, 'iv'].append(Curve(f"IV_{read_idx}", color=color, legend_label=label, show_in_legend=show))
			panels[frequency, 'qv'].append(Curve(f"QV_{read_idx}", color=color, legend_label=label, show_in_legend=show))

		v_margin = max(self.vmax * 0.1, 0.1)
		y_min = min(0.0, self.v_pos, self.v_neg, self.v_base) - v_margin
		y_max = max(0.0, self.v_pos, self.v_neg, self.v_base) + v_margin
		count = len(self.read_frequencies)
		plots = []
		for row, frequency in enumerate(self.read_frequencies):
			name = f"{format_si_compact(frequency)}Hz"
			plots += [
				PlotDef(f"time_{row}", row=row, col=0, colspan=2, title=name,
				        xlabel="Time (s)", ylabels=("Voltage (V)", "Current (uA)"),
				        xlim=(0, time_spans[frequency]), ylims=((y_min, y_max), None),
				        elements=panels[frequency, 'time']),
				PlotDef(f"iv_{row}", row=count + row, col=0, title=f"{name} I-V",
				        xlabel="Voltage (V)", ylabels=("Current (uA)",), elements=panels[frequency, 'iv']),
				PlotDef(f"qv_{row}", row=count + row, col=1, title=f"{name} Q-V",
				        xlabel="Voltage (V)", ylabels=("Charge (nC)",), elements=panels[frequency, 'qv']),
			]
		self.runner.configure_plot(f'PUND Fatigue Overlay - {device.name}', plots,
		                           row_ratios=[2.0] * count + [1.0] * count)

	def measure(self, device):
		b1500 = self.b1500
		wgfmu = b1500.wgfmu
		self.check_stop(b1500)

		read_cycles = self._read_cycles()
		if not read_cycles:
			raise ValueError("No read cycles were generated.")
		kinds = self.READ_KINDS[self.read_pulse_type]
		# Every read as (cycle, frequency, 'PN' or 'PUND'), in the order the WGFMU runs them.
		reads = [(cycle, frequency, kind)
		         for cycle in read_cycles for frequency in self.read_frequencies for kind in kinds]

		initial_pg = self._idle_voltage()
		fatigue_vectors = self._build_fatigue_vectors()
		fatigue_duration = sum(dt for dt, _ in fatigue_vectors)
		# Per (frequency, kind): waveform, sample interval, samples per read, and where the read
		# starts on the time plot (PUND after PN and its lead, as the waveform runs).
		read_types = {}
		time_spans = {}
		for frequency in self.read_frequencies:
			start = 0.0
			for kind in kinds:
				vectors = self._build_read_kind_vectors(frequency, kind)
				duration = sum(dt for dt, _ in vectors)
				interval = self._sample_interval(frequency)
				read_types[frequency, kind] = (vectors, interval, max(1, int(round(duration / interval))), start)
				start += duration + 1.0 / frequency
			time_spans[frequency] = start - 1.0 / frequency
		read_ends = np.cumsum([read_types[frequency, kind][2] for _, frequency, kind in reads])
		expected_total = int(read_ends[-1])

		# Plot at most about 50 read cycles, spread over the run, always including the last one.
		plot_cycles = set(read_cycles[::max(1, len(read_cycles) // 50)]) | {read_cycles[-1]}
		plotted = {i for i, (cycle, _, _) in enumerate(reads) if cycle in plot_cycles}
		self._configure_plot(device, reads, plotted, time_spans)
		self._report_fatigue_progress(0)

		# Each read pattern is one read period at the idle voltage, then the read.
		timeline = self._progress_timeline(
			[(cycle, 1.0 / frequency + sum(dt for dt, _ in read_types[frequency, kind][0]))
			 for cycle, frequency, kind in reads],
			fatigue_duration)
		self.log(f"Starting PUND Fatigue on {device.name}")
		self.log(
			f"  {self.fatigue_count_int:.2e} {self.fatigue_pulse_type} fatigue cycles, "
			f"Vpos={self.v_pos:g} V, Vbase={self.v_base:g} V, Vneg={self.v_neg:g} V, "
			f"{len(read_cycles)} read cycles x {len(self.read_frequencies)} frequencies x {'+'.join(kinds)}"
		)
		self.log(f"  Fatigue duration/cycle: {fatigue_duration:.6g} s")
		self.log(f"  Estimated waveform duration: {timeline[0][-1]:.1f} s")

		ts = self.get_run_timestamp()
		base = self.format_filename("PUND_Fatigue", device.name)
		names = {frequency: f"{format_si_compact(frequency)}Hz" for frequency in self.read_frequencies}
		try:
			self._configure_wgfmu(wgfmu)
			fat_pg = f"FAT_FAT_PG_{ts}"
			fat_iv = f"FAT_FAT_IV_{ts}"
			self._create_pattern_pair(wgfmu, fat_pg, fat_iv, initial_pg, fatigue_vectors)
			# One pattern pair per frequency and kind; each starts with one read period at the idle voltage.
			patterns = {}
			for f_idx, frequency in enumerate(self.read_frequencies):
				for kind in kinds:
					vectors, interval, points, _ = read_types[frequency, kind]
					lead = 1.0 / frequency
					patterns[frequency, kind] = (f"FAT_{kind}{f_idx}_PG_{ts}", f"FAT_{kind}{f_idx}_IV_{ts}")
					self._create_pattern_pair(wgfmu, *patterns[frequency, kind], initial_pg,
					                          [(lead, initial_pg), *vectors],
					                          measure_points=points, sample_interval=interval, measure_start=lead)

			prev_cycle = 0
			for cycle, frequency, kind in reads:
				if cycle > prev_cycle:
					wgfmu.add_sequence(self.channel_1, fat_pg, float(cycle - prev_cycle))
					wgfmu.add_sequence(self.channel_2, fat_iv, float(cycle - prev_cycle))
				wgfmu.add_sequence(self.channel_1, patterns[frequency, kind][0], 1.0)
				wgfmu.add_sequence(self.channel_2, patterns[frequency, kind][1], 1.0)
				prev_cycle = cycle
			# The last read cycle is always the final fatigue cycle, so nothing is left to send.

			cleanup_pg = f"FAT_CLEANUP_PG_{ts}"
			cleanup_iv = f"FAT_CLEANUP_IV_{ts}"
			self._create_pattern_pair(wgfmu, cleanup_pg, cleanup_iv, initial_pg, [(1e-4, 0.0)])
			wgfmu.add_sequence(self.channel_1, cleanup_pg, 1.0)
			wgfmu.add_sequence(self.channel_2, cleanup_iv, 1.0)

			self.check_stop(b1500)
			wgfmu.execute()

			times, voltages, currents = [], [], []  # every sample of the run, in order
			done = 0  # reads already saved (and plotted, if chosen)
			while True:
				self.check_stop(b1500)
				status, elapsed, _ = wgfmu.get_status()
				self._report_fatigue_progress(int(np.interp(elapsed, *timeline)))
				measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2, expected_total)

				if available > len(times):
					# One call per channel for all new samples; per-sample calls cannot keep up with closely spaced reads.
					start = len(times)
					samples_v = wgfmu.read_chunk(self.channel_1, start, available - start)
					samples_i = wgfmu.read_chunk(self.channel_2, start, available - start)
					for (t, v), (_, cur) in zip(samples_v, samples_i):
						times.append(t)
						voltages.append(v)
						currents.append(cur)

					# Save and plot every read that is now complete.
					while done < len(reads) and read_ends[done] <= len(times):
						cycle, frequency, kind = reads[done]
						_, interval, points, plot_start = read_types[frequency, kind]
						span = slice(int(read_ends[done]) - points, int(read_ends[done]))
						self.save_data([[cycle, t, v, cur] for t, v, cur in zip(times[span], voltages[span], currents[span])],
						               f"{base}_{kind}_{names[frequency]}_c{cycle}.csv", HEADERS, add_timestamp=False)
						if done in plotted:
							v, cur = np.array(voltages[span]), np.array(currents[span])
							t_plot = plot_start + np.arange(len(v)) * interval
							# Switching current: offset removed and negated, as channel 2 sits on the 0 V side.
							i_switch = -(cur - cur[:BASELINE_POINTS].mean())
							charge = np.cumsum(i_switch[BASELINE_POINTS:]) * interval
							self.runner.plot.append_batch({
								f"V_{done}": list(zip(t_plot, v)),
								f"I_{done}": list(zip(t_plot, cur * 1e6)),
								f"IV_{done}": list(zip(v[BASELINE_POINTS:], i_switch[BASELINE_POINTS:] * 1e6)),
								f"QV_{done}": list(zip(v[BASELINE_POINTS:], charge * 1e9)),
							})
						done += 1

				# Status was read before fetching, so a completed run has no samples left to read.
				if status == self.STATUS_COMPLETED:
					break
				time.sleep(0.05)
			# The elapsed time is an estimate, so it may stop short of the full count.
			self._report_fatigue_progress(self.fatigue_count_int)

			if done:
				self.save_plot_png(f"{base}_plot.png")
			if done < len(reads):
				self.log(f"Warning: only {done} of {len(reads)} reads were measured ({len(times)}/{expected_total} samples).")
			self.log(
				f"PUND Fatigue complete: {self.fatigue_count_int:.2e} cycles, "
				f"{done} reads saved as separate files, {len(times)} samples"
			)

		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
