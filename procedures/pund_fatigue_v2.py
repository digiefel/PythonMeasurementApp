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


class PUNDFatigueV2Procedure(MeasurementProcedure):
	NAME = "PUNDFatigueV2"
	PARAMETERS = (
		parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
		parameter('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 101, WGFMUChannel),
		parameter('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 102, WGFMUChannel),
		parameter('vmax', 'Pulse Amplitude (V)', 1.0, float),
        parameter('base_voltage', 'Base Voltage (V)', 0.0, float), # baseline voltage: V = V_base +- V_max
        parameter('hold_base', 'Hold Base V continuously', True, bool), # hold baseline for the entire time?
		parameter('fatigue_freq', 'Fatigue Frequency (Hz)', 1e4, float), # inverse duration of the fatigue pulses
        parameter('fatigue_delay', 'Fatigue Cycle Delay (s)', 0.0, float), # wait time between fatigue pulses
		parameter('fatigue_count', 'Fatigue Cycle Count', 1e6, float), # total fatigue cycle count
		parameter('fatigue_pulse_type', 'Type of Fatigue Cycle', 'square',
            Choice((('square', 'Square'), ('triangle', 'Triangle'), ('pund', 'PUND')))),
        parameter('read_pulse_freq', 'Read Frequency (Hz)', 1e4, float), # inverse duration of the read pulses
        parameter('read_pulse_type', 'Type of Read Cycle', 'pund',
                  Choice((('pund', 'PUND'), ('pn', 'PN'), ('both', 'PN+PUND')))),
		parameter('reads_per_decade', 'Read Cycles per Decade', 10, int),
        parameter('meas_range_1', 'Meas Range Ch1 (V)', WGFMU_MEASURE_VOLTAGE_RANGES[0][0],
                  Choice(WGFMU_MEASURE_VOLTAGE_RANGES, int)),
        parameter('meas_range_2', 'Meas Range Ch2 (I)', WGFMU_MEASURE_CURRENT_RANGES[0][0],
                  Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
	)
	UI_ACTIONS = (
		action("Preview Sequence", "_show_pund_fatigue_preview"),
	)


	MIN_INTERVAL = 1e-8
	RESOLUTION = 1e-8
	STATUS_COMPLETED = 10000
	POST_COMPLETION_DRAIN_TIMEOUT_S = 30.0

	def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
		super().__init__(settings, output_root, output_relative, runner, fallback_root)
		self.fatigue_count_int = int(float(self.fatigue_count))
		self._validate_settings()

	def _validate_settings(self):
		if self.vmax == 0.0:
			raise ValueError("vmax must be non-zero. Use a negative value to invert polarity.")
		if self.fatigue_freq <= 0:
			raise ValueError("fatigue_freq must be > 0")
		if self.read_pulse_freq <= 0:
			raise ValueError("read_pulse_freq must be > 0")
		if self.fatigue_delay < 0:
			raise ValueError("fatigue_delay must be >= 0")
		if self.fatigue_count_int < 1:
			raise ValueError("fatigue_count must be >= 1")
		if self.reads_per_decade <= 0:
			raise ValueError("reads_per_decade must be > 0")
		if self.fatigue_pulse_type not in ('square', 'triangle', 'pund'):
			raise ValueError(f"Invalid fatigue_pulse_type: {self.fatigue_pulse_type!r}")
		if self.read_pulse_type not in ('pund', 'pn', 'both'):
			raise ValueError(f"Invalid read_pulse_type: {self.read_pulse_type!r}")

	def _idle_voltage(self):
		return self.base_voltage if self.hold_base else 0.0

	def _positive_level(self):
		return self.base_voltage + self.vmax

	def _negative_level(self):
		return self.base_voltage - self.vmax

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
		self._append_square_level(vectors, self._positive_level(), segment)
		self._append_square_level(vectors, self._negative_level(), segment)
		self._append_idle_hold(vectors, self.fatigue_delay)
		return vectors

	def _build_triangle_fatigue_vectors(self):
		"""Seamless triangular PN fatigue cycle, then optional idle delay."""
		ramp = (2.0 / self.fatigue_freq) / 3.0
		vectors = [
			(ramp, self._positive_level()),
			(ramp, self._negative_level()),
			(ramp, self._idle_voltage()),
		]
		self._append_idle_hold(vectors, self.fatigue_delay)
		return vectors

	def _build_pund_like_vectors(self, frequency):
		"""Four square PUND pulses with base holds between pulses."""
		pulse = 1.0 / frequency
		vectors = []
		for idx, level in enumerate((
			self._positive_level(),
			self._positive_level(),
			self._negative_level(),
			self._negative_level(),
		)):
			self._append_square_level(vectors, level, pulse)
			if idx < 3:
				self._append_square_level(vectors, self.base_voltage, pulse)
			else:
				vectors.append((self.MIN_INTERVAL, self._idle_voltage()))
		return vectors

	def _build_fatigue_vectors(self):
		if self.fatigue_pulse_type == 'square':
			return self._build_square_fatigue_vectors()
		if self.fatigue_pulse_type == 'triangle':
			return self._build_triangle_fatigue_vectors()
		vectors = self._build_pund_like_vectors(self.fatigue_freq)
		self._append_idle_hold(vectors, self.fatigue_delay)
		return vectors

	def _build_pn_read_vectors(self):
		"""Seamless triangular PN read pulse with total ramp duration 2/read_pulse_freq."""
		ramp = (2.0 / self.read_pulse_freq) / 3.0
		return [
			(ramp, self._positive_level()),
			(ramp, self._negative_level()),
			(ramp, self._idle_voltage()),
		]

	def _build_pund_read_vectors(self):
		return self._build_pund_like_vectors(self.read_pulse_freq)

	def _build_read_vectors(self):
		if self.read_pulse_type == 'pn':
			return self._build_pn_read_vectors()
		if self.read_pulse_type == 'pund':
			return self._build_pund_read_vectors()

		vectors = []
		vectors.extend(self._build_pn_read_vectors())
		self._append_idle_hold(vectors, 1.0 / self.read_pulse_freq)
		vectors.extend(self._build_pund_read_vectors())
		return vectors

	def _iv_vectors_for(self, vectors):
		# Channel 2 always stays at 0 V; all PG/base/fatigue/read voltage is applied only on channel 1.
		return [(dt, 0.0) for dt, _ in vectors]

	def _sample_interval(self):
		raw_interval = 1e-3 / self.read_pulse_freq
		sample_interval = max(raw_interval, self.MIN_INTERVAL)
		sample_interval = round(sample_interval / self.RESOLUTION) * self.RESOLUTION
		return max(sample_interval, self.MIN_INTERVAL)

	@staticmethod
	def _compute_read_cycles(cycle_count: int, reads_per_decade: int) -> list[int]:
		"""Return sparse read cycle numbers, with the final fatigue cycle always included."""
		n = int(cycle_count)
		ppd = int(reads_per_decade)
		if ppd <= 0 or n < 1:
			return []

		cycles = []
		decade = 0
		while True:
			base = 10 ** decade
			next_base = base * 10

			if decade == 0:
				for c in range(1, min(ppd + 1, 10 + 1, n + 1)):
					cycles.append(c)
			else:
				step = max(1, next_base // ppd)
				if step > base:
					start = step
				elif step == base:
					start = step * 2
				else:
					start = base + step

				for c in range(start, next_base + 1, step):
					if c > n:
						break
					cycles.append(c)

			if next_base >= n:
				break
			decade += 1

		if n not in cycles:
			cycles.append(n)
		return sorted(set(cycles))

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
	def _add_vectors(wgfmu, pattern_name, vectors):
		for dt, voltage in vectors:
			if dt > 0:
				wgfmu.add_vector(pattern_name, dt, voltage)

	def _create_pattern_pair(self, wgfmu, pg_name, iv_name, initial_pg, pg_vectors, measure_points=None, sample_interval=None):
		wgfmu.create_pattern(pg_name, initial_pg)
		self._add_vectors(wgfmu, pg_name, pg_vectors)

		wgfmu.create_pattern(iv_name, 0.0)
		self._add_vectors(wgfmu, iv_name, self._iv_vectors_for(pg_vectors))

		if measure_points is not None and sample_interval is not None:
			wgfmu.set_measure_event(
				pg_name,
				"meas",
				0.0,
				measure_points,
				sample_interval,
				sample_interval,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)
			wgfmu.set_measure_event(
				iv_name,
				"meas",
				0.0,
				measure_points,
				sample_interval,
				sample_interval,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)

	def _plot_sources(self, cycle_num):
		return f"V_{cycle_num}", f"I_{cycle_num}", f"IV_{cycle_num}", f"QV_{cycle_num}"

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

		for read_idx in plot_indices:
			cycle_num = read_cycles[read_idx]
			log_cycle = np.log10(max(cycle_num, 1))
			intensity = 0.2 + 0.7 * (log_cycle / max(log_max, 1))
			show = read_idx == 0 or read_idx == len(read_cycles) - 1
			i_color = (intensity, 0.3 * intensity, 0)
			v_source, i_source, iv_source, qv_source = self._plot_sources(cycle_num)
			label = f"cycle {cycle_num}"
			elements.append(Curve(v_source, color=(0, 0, intensity), yaxis=0,
			                      legend_label=f"V ({label})", show_in_legend=show))
			elements.append(Curve(i_source, color=i_color, yaxis=1,
			                      legend_label=f"I ({label})", show_in_legend=show))
			iv_elements.append(Curve(iv_source, color=i_color,
			                         legend_label=label, show_in_legend=show))
			qv_elements.append(Curve(qv_source, color=i_color,
			                         legend_label=label, show_in_legend=show))
			source_map[read_idx] = (v_source, i_source, iv_source, qv_source)

		max_abs_v = abs(self.vmax)
		v_margin = max(max_abs_v * 0.1, 0.1)
		y_min = min(0.0, self.base_voltage - max_abs_v) - v_margin
		y_max = max(0.0, self.base_voltage + max_abs_v) + v_margin

		self.runner.configure_plot(f'PUND Fatigue V2 Overlay - {device.name}', [
			PlotDef("pund_fat_v2", row=0, col=0, colspan=2,
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
	def get_preview_info(cycle_count: float, frequency: float, reads_per_decade: int) -> dict:
		read_cycles = PUNDFatigueV2Procedure._compute_read_cycles(int(cycle_count), int(reads_per_decade))
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

		read_cycles = self._compute_read_cycles(self.fatigue_count_int, self.reads_per_decade)
		if not read_cycles:
			raise ValueError("No read cycles were generated.")

		fatigue_vectors = self._build_fatigue_vectors()
		read_vectors = self._build_read_vectors()
		fatigue_duration = sum(dt for dt, _ in fatigue_vectors)
		read_duration = sum(dt for dt, _ in read_vectors)
		sample_interval = self._sample_interval()
		sample_points = max(1, int(read_duration / sample_interval))
		expected_total = sample_points * len(read_cycles)
		source_map = self._configure_plot(device, read_cycles, read_duration)

		total_time = (self.fatigue_count_int * fatigue_duration) + (len(read_cycles) * read_duration)
		self.log(f"Starting PUND Fatigue V2 on {device.name}")
		self.log(
			f"  {self.fatigue_count_int:.2e} {self.fatigue_pulse_type} fatigue cycles, "
			f"Vmax={self.vmax:g} V, reads={len(read_cycles)}"
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
			fat_pg = f"FAT2_FAT_PG_{ts}"
			fat_iv = f"FAT2_FAT_IV_{ts}"
			read_pg = f"FAT2_READ_PG_{ts}"
			read_iv = f"FAT2_READ_IV_{ts}"

			self._create_pattern_pair(wgfmu, fat_pg, fat_iv, initial_pg, fatigue_vectors)
			self._create_pattern_pair(
				wgfmu,
				read_pg,
				read_iv,
				initial_pg,
				read_vectors,
				measure_points=sample_points,
				sample_interval=sample_interval,
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

			cleanup_pg = f"FAT2_CLEANUP_PG_{ts}"
			cleanup_iv = f"FAT2_CLEANUP_IV_{ts}"
			self._create_pattern_pair(wgfmu, cleanup_pg, cleanup_iv, initial_pg, [(1e-4, 0.0)])
			wgfmu.add_sequence(self.channel_1, cleanup_pg, 1.0)
			wgfmu.add_sequence(self.channel_2, cleanup_iv, 1.0)

			self.check_stop(b1500)
			wgfmu.execute()

			plotted_count = 0
			data_ch1 = []
			data_ch2 = []
			i_baseline_samples: dict[int, list] = {}
			i_baseline: dict[int, float] = {}
			q_accum: dict[int, float] = {}
			last_t_per_read: dict[int, float] = {}
			last_progress_time = time.monotonic()

			while True:
				self.check_stop(b1500)
				status, _elapsed, _total = wgfmu.get_status()
				measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2, expected_total)

				if available > plotted_count:
					batches: dict[int, dict] = {}

					for sample_index in range(plotted_count, available):
						self.check_stop(b1500)
						t_v, voltage = wgfmu.get_measure_value(self.channel_1, sample_index)
						t_i, current = wgfmu.get_measure_value(self.channel_2, sample_index)
						data_ch1.append((t_v, voltage))
						data_ch2.append((t_i, current))

						read_idx = sample_index // sample_points
						sample_in_read = sample_index % sample_points
						if read_idx >= len(read_cycles) or read_idx not in source_map:
							continue

						rel_t = sample_in_read * sample_interval
						batch = batches.setdefault(read_idx, {'v': [], 'i': [], 'iv': [], 'qv': []})
						batch['v'].append((rel_t, voltage))
						batch['i'].append((rel_t, current * 1e6))

						if read_idx not in i_baseline:
							samples = i_baseline_samples.setdefault(read_idx, [])
							if len(samples) < 50:
								samples.append(current)
							if len(samples) == 50:
								i_baseline[read_idx] = float(np.mean(samples))

						if read_idx in i_baseline:
							current_adj = -(current - i_baseline[read_idx])
							batch['iv'].append((voltage, current_adj * 1e6))
							if read_idx not in q_accum:
								q_accum[read_idx] = 0.0
								last_t_per_read[read_idx] = rel_t
							else:
								dt = rel_t - last_t_per_read[read_idx]
								if dt > 0:
									q_accum[read_idx] += current_adj * dt
								last_t_per_read[read_idx] = rel_t
							batch['qv'].append((voltage, q_accum[read_idx] * 1e9))

					plot_batch = {}
					for read_idx, batch in batches.items():
						v_source, i_source, iv_source, qv_source = source_map[read_idx]
						plot_batch[v_source] = batch['v']
						plot_batch[i_source] = batch['i']
						plot_batch[iv_source] = batch['iv']
						plot_batch[qv_source] = batch['qv']
					if plot_batch:
						self.runner.plot.append_batch(plot_batch)

					plotted_count = available
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
						_t_v, voltage = data_ch1[row_idx]
						_t_i, current = data_ch2[row_idx]
						all_rows.append([cycle_num, i * sample_interval, voltage, current])

			self.save_measurement_outputs(
				all_rows,
				"PUND_Fatigue_V2",
				device,
				["Cycle", "Time_s", "Voltage_V", "Current_A"],
				plot_suffix="_overlay.png",
				save_plot=bool(all_rows),
			)

			self.log(
				f"PUND Fatigue V2 complete: {self.fatigue_count_int:.2e} cycles, "
				f"{len(read_cycles)} reads, {len(all_rows)} samples"
			)

		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
