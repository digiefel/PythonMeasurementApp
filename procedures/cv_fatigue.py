"""
CV Fatigue Procedure - PUND reads during fatigue, with a C-V sweep at chosen cycles.

The fatigue and PUND read schedule of FORCFatigue, with a CMU C-V sweep where
FORCFatigue runs a FORC. The fatigue cycles use Fatigue Vpos and Vneg; the PUND
reads use Read Vpos and Vneg. Between pulses everything rests at 0 V. A C-V
sweep (at every C-V frequency) runs on the pristine device at cycle 0 and after
each fatigue cycle count listed in "C-V at Cycles". Cycle 0 also gets a PUND
read. Where a cycle has both, the C-V comes first, so the cycle-0 C-V sees a
pristine device.

This needs the SCUU outputs cabled into the From-SMU inputs of the two channels'
RSUs: an RSU connects that input to the probe whenever its WGFMU channel is idle.
So the WGFMU runs in blocks, from one C-V to the next; after each block its
channels are switched off and the CMU measures through the same RSUs. Choose
channel 1 (the pulse channel) as the RSU that CMU-H reaches and channel 2 as the
CMU-L one, so a positive pulse and a positive C-V bias point the same way. The
software cannot see the cabling, so it does not check this.

The run uses the CMU calibration the instrument holds: the calibration section
calibrates at the C-V frequencies, and the CSV headers name what was in use
(cmu_correction).

Every read is saved as its own CSV as soon as it is measured:
``<base>_c<cycle>_PUND.csv`` and ``<base>_c<cycle>_CV.csv``.

The live plot shows the Q-V curve of every PUND read, coloured by cycle, and below
it one C-V panel per frequency. Z-Theta modes plot Cp; other modes plot their
first parameter.
"""
import time
from dataclasses import replace
import numpy as np
from plotting import PlotDef, Curve
from procedures.base import Choice, ValueList, parameter
from procedures.pund_fatigue import PUNDFatigueProcedure
from procedures._cmu import (
	CMUCalibration,
	CV_SWEEP_TYPES,
	freq_label,
	parse_cmu_frequencies,
	report_cmu_status,
	resolve_cmu_channel,
	run_cv_sweep,
	validate_cv_sweep,
	z_theta_pairs,
)
from instrumentio.codes import B1500_AUTO_RANGE, B1500_CH_ALL, B1500_CMUM_Z_TDEG, B1500_CMUM_Z_TRAD
from instrumentio.constants import (
	B1500_CMU_CHANNELS,
	B1500_CMU_INTEGRATION_MODES,
	B1500_CMU_MEASUREMENT_MODES,
	B1500_CMU_SWEEP_RANGES,
)
from instrumentio.descriptors import format_cmu_component_label, get_cmu_mode_components

# PUND Q-V: the current offset is the mean of the first samples, as in PUNDFatigue.
PUND_BASELINE_POINTS = 50
PUND_HEADERS = ["Cycle", "Time_s", "Voltage_V", "Current_A"]
# The RSU's From-SMU input takes at most ±25 V (B1530A Guide 1-8).
MAX_CV_BIAS = 25.0
CV_SECTION = "C-V timing and calibration"

_PUND_FATIGUE_PARAMETERS = {p.key: p for p in PUNDFatigueProcedure.PARAMETERS}


class CVFatigueProcedure(CMUCalibration, PUNDFatigueProcedure):
	NAME = "CVFatigue"
	PARAMETERS = (
		_PUND_FATIGUE_PARAMETERS['gpib_address'],
		replace(_PUND_FATIGUE_PARAMETERS['channel_1'],
		        help="Pulse channel. Its RSU must be the one cabled to CMU-H (through the SCUU), "
		             "so pulses and C-V bias share a sign."),
		replace(_PUND_FATIGUE_PARAMETERS['channel_2'],
		        help="Current channel. Its RSU must be the one cabled to CMU-L (through the SCUU)."),
		replace(_PUND_FATIGUE_PARAMETERS['v_pos'], label='Fatigue Vpos (V)',
		        help='Peak voltage of the positive fatigue pulses.'),
		replace(_PUND_FATIGUE_PARAMETERS['v_neg'], label='Fatigue Vneg (V)',
		        help='Peak voltage of the negative fatigue pulses.'),
		*(_PUND_FATIGUE_PARAMETERS[key] for key in
		  ('fatigue_freq', 'fatigue_delay', 'fatigue_count', 'fatigue_pulse_type')),
		parameter('read_v_pos', 'Read Vpos (V)', 1.0, float, help='P and U level of the PUND reads.'),
		parameter('read_v_neg', 'Read Vneg (V)', -1.0, float, help='Preset, N and D level of the PUND reads.'),
		*(_PUND_FATIGUE_PARAMETERS[key] for key in
		  ('read_pulse_freq', 'read_pulse_type', 'read_delay', 'pund_gap',
		   'read_spacing', 'reads_per_decade', 'linear_read_count', 'meas_range_1', 'current_ranges')),
		parameter('cv_cycles', 'C-V at Cycles', '1e2, 1e4, 1e6', str,
		          help="Comma-separated fatigue cycle counts that get a C-V sweep, besides the pristine one "
		               "at cycle 0. Each must be between 1 and the fatigue cycle count."),
		parameter('cmu_channel', 'CMU Channel', -1, Choice(B1500_CMU_CHANNELS, int)),
		parameter('sweep_type', 'C-V Sweep Type', 'butterfly', Choice(CV_SWEEP_TYPES, str)),
		parameter('cmu_mode', 'C-V Meas Output', B1500_CMUM_Z_TDEG, Choice(B1500_CMU_MEASUREMENT_MODES, int),
		          help="What the CMU returns. Z-Theta modes plot Cp, calculated from Z and Theta."),
		parameter('start_bias', 'C-V Start Bias (V)', 2.0, float, help="Butterfly: Vmax."),
		parameter('stop_bias', 'C-V Stop Bias (V)', -2.0, float, help="Butterfly: Vmin."),
		parameter('points', 'C-V Points', 101, int),
		parameter('frequencies', 'C-V Frequencies', '100k', ValueList,
		          help="Comma-separated, SI prefixes accepted, e.g. '10k, 100k, 1M'. One sweep per frequency, "
		               "1 kHz to 5 MHz. The calibration buttons calibrate at these."),
		parameter('ac_level_mv', 'AC Level (mV)', 30.0, float, help='AC excitation on top of the swept DC bias.'),
		parameter('measurement_range', 'MFCMU Meas Range', B1500_AUTO_RANGE, Choice(B1500_CMU_SWEEP_RANGES, float),
		          section=CV_SECTION),
		parameter('integration_mode', 'Integration Mode', 0, Choice(B1500_CMU_INTEGRATION_MODES, int),
		          section=CV_SECTION),
		parameter('integration_value', 'Integration Coefficient (N)', 1, int, section=CV_SECTION,
		          help="Auto: the CMU averages N times the number of samples the B1500 picks itself, N from 1 to 1023. "
		               "PLC: averaging lasts N power line cycles, 20 ms each at 50 Hz, N from 1 to 100."),
		parameter('hold_time', 'C-V Hold Time (s)', 0.0, float, section=CV_SECTION),
		parameter('delay_time', 'C-V Delay Time (s)', 0.0, float, section=CV_SECTION),
		parameter('second_delay', 'C-V Step Delay (s)', 0.0, float, section=CV_SECTION),
		parameter('require_cmu_calibration', 'Require Calibration', False, bool, section=CV_SECTION),
	)
	UI_ACTIONS = (*PUNDFatigueProcedure.UI_ACTIONS, *CMUCalibration.UI_ACTIONS)
	# Everything rests at 0 V between pulses, as in FORCFatigue.
	v_base = 0.0
	hold_base = False
	# TODO: the inherited "Preview Sequence" shows the PUND reads only, not the C-V sweeps.
	# TODO: the inherited Read Delay field is not used yet; reads here still start after one read period.

	@classmethod
	def cmu_calibration_frequencies(cls, settings):
		return parse_cmu_frequencies(settings.get('frequencies', '100k'))

	def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
		super().__init__(settings, output_root, output_relative, runner, fallback_root)
		self.cmu_calibration = settings.get("cmu_calibration", {}) or {}
		if runner is not None:
			self.cmu_channel = resolve_cmu_channel(self.settings, self.cmu_channel, self.log)
			self.settings['cmu_channel'] = self.cmu_channel

	def _read_levels(self):
		return self.read_v_pos, self.read_v_neg

	def _validate_settings(self):
		super()._validate_settings()
		# TODO: read at every frequency once the fatigue procedures are rewritten as a chain.
		if len(self.read_frequencies) > 1:
			raise ValueError("CVFatigue reads at one PUND frequency only; give a single read frequency.")
		if self.channel_1 == self.channel_2:
			raise ValueError("WGFMU channels 1 and 2 must differ.")
		self.cv_frequencies = parse_cmu_frequencies(self.frequencies)
		validate_cv_sweep(self.sweep_type, self.start_bias, self.stop_bias, self.points)
		if max(abs(self.start_bias), abs(self.stop_bias)) > MAX_CV_BIAS:
			raise ValueError(f"C-V bias is limited to ±{MAX_CV_BIAS:g} V by the RSU's From-SMU input.")
		if not 0.0 <= self.ac_level_mv <= 250.0:
			raise ValueError("AC Level must be between 0 and 250 mV.")
		if self.integration_value < 1:
			raise ValueError("Integration Coefficient must be >= 1.")
		try:
			self.cv_cycle_list = sorted({int(float(c)) for c in str(self.cv_cycles).split(',') if c.strip()})
		except ValueError:
			raise ValueError(f"C-V at Cycles must be comma-separated numbers, got {self.cv_cycles!r}") from None
		outside = [c for c in self.cv_cycle_list if not 1 <= c <= self.fatigue_count_int]
		if outside:
			raise ValueError(f"C-V cycles {outside} are outside 1 to {self.fatigue_count_int} (the fatigue cycle count)")

	def _reads(self):
		"""Every read as (cycle, 'CV' or 'PUND'), in run order: the C-V before the PUND read of its cycle."""
		cv_cycles = {0, *self.cv_cycle_list}
		reads = []
		for cycle in sorted({0, *self._read_cycles(), *cv_cycles}):
			if cycle in cv_cycles:
				reads.append((cycle, 'CV'))
			reads.append((cycle, 'PUND'))
		return reads

	def _is_z_theta(self):
		return self.cmu_mode in (B1500_CMUM_Z_TDEG, B1500_CMUM_Z_TRAD)

	def _configure_plot(self, device, reads):
		log_max = np.log10(max(reads[-1][0], 1))
		indices = {kind: [i for i, (_, k) in enumerate(reads) if k == kind] for kind in ('PUND', 'CV')}
		pund, cv = [], [[] for _ in self.cv_frequencies]
		for read_idx, (cycle, kind) in enumerate(reads):
			intensity = 0.2 + 0.7 * (np.log10(max(cycle, 1)) / max(log_max, 1))
			show = read_idx in (indices[kind][0], indices[kind][-1])
			if kind == 'PUND':
				pund.append(Curve(f"QV_{read_idx}", color=self._phase_color('pund', intensity),
				                  legend_label=f"cycle {cycle}", show_in_legend=show))
			else:
				for fi, curves in enumerate(cv):
					curves.append(Curve(f"CV_{read_idx}_{fi}", mode='line_scatter', marker='o', marker_size=3,
					                    color=self._phase_color('pn', intensity),
					                    legend_label=f"cycle {cycle}", show_in_legend=show))
		y_label = "Cp (F)" if self._is_z_theta() else format_cmu_component_label(get_cmu_mode_components(self.cmu_mode)[0])
		columns = max(1, len(self.cv_frequencies))
		plots = [PlotDef("pund_qv", row=0, col=0, colspan=columns, title="PUND reads",
		                 xlabel="Voltage (V)", ylabels=("Charge (nC)",), elements=pund)]
		for fi, freq in enumerate(self.cv_frequencies):
			plots.append(PlotDef(f"cv_{fi}", row=1, col=fi, title=f"C-V at {freq_label(freq)}",
			                     xlabel="Bias (V)", ylabels=(y_label,), elements=cv[fi]))
		self.runner.configure_plot(f'CV Fatigue - {device.name}', plots, row_ratios=[1.0, 1.0])

	def _run_wgfmu_block(self, wgfmu, ts, block, items, reads, base):
		"""Send one block: items are ('FAT', count) and ('PUND', read_idx), in order. Saves and plots its reads."""
		if not items:
			return
		self._configure_wgfmu(wgfmu)
		initial_pg = self._idle_voltage()
		settle = 1.0 / self.fatigue_freq
		freq = self.read_frequencies[0]
		pund_vectors = self._build_read_vectors(freq)
		interval = self._sample_interval(freq)
		points = max(1, int(round(sum(dt for dt, _ in pund_vectors) / interval)))
		fatigue_vectors = self._build_fatigue_vectors()
		fat, read = (f"CVFAT_FAT_PG_{ts}_{block}", f"CVFAT_FAT_IV_{ts}_{block}"), \
			(f"CVFAT_PUND_PG_{ts}_{block}", f"CVFAT_PUND_IV_{ts}_{block}")
		self._create_pattern_pair(wgfmu, *fat, initial_pg, fatigue_vectors)
		self._create_pattern_pair(wgfmu, *read, initial_pg, [(settle, initial_pg), *pund_vectors],
		                          measure_points=points, sample_interval=interval, measure_start=settle)
		read_indices = []
		for kind, value in items:
			pattern = fat if kind == 'FAT' else read
			wgfmu.add_sequence(self.channel_1, pattern[0], float(value if kind == 'FAT' else 1))
			wgfmu.add_sequence(self.channel_2, pattern[1], float(value if kind == 'FAT' else 1))
			if kind == 'PUND':
				read_indices.append(value)

		# Fatigue progress over this block: cycles grow during fatigue and hold during reads.
		start_cycle = self._cycles_sent
		fatigue_period = sum(dt for dt, _ in fatigue_vectors)
		times, cycles, t, c = [0.0], [start_cycle], 0.0, start_cycle
		for kind, value in items:
			if kind == 'FAT':
				t, c = t + value * fatigue_period, c + value
			else:
				t += settle + sum(dt for dt, _ in pund_vectors)
			times.append(t)
			cycles.append(c)

		self.check_stop(self.b1500)
		wgfmu.execute()
		expected = points * len(read_indices)
		samples_v, samples_i, done = [], [], 0
		while True:
			self.check_stop(self.b1500)
			status, elapsed, _ = wgfmu.get_status()
			self._report_fatigue_progress(int(np.interp(elapsed, times, cycles)))
			measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
			measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
			available = min(measured_1, measured_2, expected)
			if available > len(samples_v):
				samples_v += wgfmu.read_chunk(self.channel_1, len(samples_v), available - len(samples_v))
				samples_i += wgfmu.read_chunk(self.channel_2, len(samples_i), available - len(samples_i))
				while done < len(read_indices) and (done + 1) * points <= len(samples_v):
					self._finish_pund_read(reads, read_indices[done], samples_v[done * points:(done + 1) * points],
					                       samples_i[done * points:(done + 1) * points], interval, base)
					done += 1
			# Status was read before fetching, so a completed block has no samples left to read.
			if status == self.STATUS_COMPLETED:
				break
			time.sleep(0.05)
		self._cycles_sent = cycles[-1]
		self._report_fatigue_progress(self._cycles_sent)
		if done < len(read_indices):
			self.log(f"Warning: block {block} measured {done} of {len(read_indices)} PUND reads.")
		# Switched-off channels hand their RSUs back to the From-SMU input, which the CMU uses.
		wgfmu.release()

	def _finish_pund_read(self, reads, read_idx, samples_v, samples_i, interval, base):
		cycle = reads[read_idx][0]
		self.save_data([[cycle, t, v, i] for (t, v), (_, i) in zip(samples_v, samples_i)],
		               f"{base}_c{cycle}_PUND.csv", PUND_HEADERS, add_timestamp=False)
		v = np.array([x for _, x in samples_v])
		cur = np.array([x for _, x in samples_i])
		# Q-V as in PUNDFatigue: offset from the first samples, negated current.
		charge = np.cumsum(-(cur[PUND_BASELINE_POINTS:] - cur[:PUND_BASELINE_POINTS].mean())) * interval
		self.runner.plot.append_batch({f"QV_{read_idx}": list(zip(v[PUND_BASELINE_POINTS:], charge * 1e9))})
		self._reads_done += 1

	def _run_cv(self, reads, read_idx, base, statuses):
		"""C-V sweep at every C-V frequency, through the SCUU and the idle RSUs."""
		b1500 = self.b1500
		cycle = reads[read_idx][0]
		primary, monitor = get_cmu_mode_components(self.cmu_mode)
		is_degrees = self.cmu_mode == B1500_CMUM_Z_TDEG
		rows = []
		try:
			# CN on the CMU also switches the SCUU outputs to it.
			b1500.set_switch(B1500_CH_ALL, False)
			b1500.set_switch(self.cmu_channel, True)
			b1500.set_cmu_integ(self.integration_mode, self.integration_value)
			for fi, freq in enumerate(self.cv_frequencies):
				self.check_stop(b1500)
				b1500.set_cmu_freq(self.cmu_channel, freq)
				# Set every time: zero_output (DZ) after the previous C-V also set the AC level to 0.
				b1500.force_cmu_ac_level(self.cmu_channel, self.ac_level_mv / 1000.0)

				def on_point(bias, para1, para2, time_s, s1, s2, _fi=fi, _freq=freq):
					self.check_stop(b1500)
					y = z_theta_pairs(para1, para2, _freq, is_degrees)["cp"] if self._is_z_theta() else para1
					self.runner.plot.append_point(f"CV_{read_idx}_{_fi}", bias, y)
					report_cmu_status(self.runner, self.cmu_channel, statuses, s1, s2)
					rows.append([cycle, _freq, bias, para1, para2, time_s, s1, s2, s1 | s2])

				run_cv_sweep(b1500, self.cmu_channel, self.cmu_mode, self.measurement_range, self.sweep_type,
				             self.start_bias, self.stop_bias, self.points,
				             self.hold_time, self.delay_time, self.second_delay, on_point)
		finally:
			b1500.zero_output(B1500_CH_ALL)
			b1500.set_switch(B1500_CH_ALL, False)
			# Also after a stop, so a partial C-V is kept. One that measured nothing
			# (e.g. in the waveform preview) writes no file.
			if rows:
				self.save_data(rows, f"{base}_c{cycle}_CV.csv",
				               ["Cycle", "Frequency_Hz", "Bias_V", format_cmu_component_label(primary),
				                format_cmu_component_label(monitor), "Time_sec", f"Status_{primary}",
				                f"Status_{monitor}", "Status_Combined"],
				               add_timestamp=False)
		self._reads_done += 1

	def measure(self, device):
		b1500 = self.b1500
		wgfmu = b1500.wgfmu
		self.check_stop(b1500)
		reads = self._reads()
		self._configure_plot(device, reads)
		self._cycles_sent = 0
		self._reads_done = 0
		self._report_fatigue_progress(0)
		cv_count = sum(kind == 'CV' for _, kind in reads)
		self.log(f"Starting CV Fatigue on {device.name}: {self.fatigue_count_int:.2e} {self.fatigue_pulse_type} "
		         f"fatigue cycles, {len(reads) - cv_count} PUND reads, {cv_count} C-V reads at "
		         f"[{', '.join(freq_label(f) for f in self.cv_frequencies)}]")

		b1500.reset()
		b1500.set_timeout(10000)
		b1500.enable_error_detect(True)
		# *RST stops the use of the calibration data; switch it back on.
		self.apply_cmu_calibration(b1500)

		ts = self.get_run_timestamp()
		base = self.format_filename("CV_Fatigue", device.name)
		statuses = set()
		try:
			# Blocks of WGFMU work run between C-V reads; fatigue towards a C-V cycle ends the block before it.
			items, block, prev_cycle = [], 0, 0
			for read_idx, (cycle, kind) in enumerate(reads):
				if cycle > prev_cycle:
					items.append(('FAT', cycle - prev_cycle))
					prev_cycle = cycle
				if kind == 'PUND':
					items.append(('PUND', read_idx))
					continue
				self._run_wgfmu_block(wgfmu, ts, block, items, reads, base)
				items, block = [], block + 1
				self._run_cv(reads, read_idx, base, statuses)
			self._run_wgfmu_block(wgfmu, ts, block, items, reads, base)
			self._report_fatigue_progress(self.fatigue_count_int)
			if self._reads_done:
				self.save_plot_png(f"{base}_plot.png")
			self.log(f"CV Fatigue complete: {self._reads_done} of {len(reads)} reads saved as separate files")
		finally:
			try:
				wgfmu.clear()
				wgfmu.release()
			except Exception:
				pass
