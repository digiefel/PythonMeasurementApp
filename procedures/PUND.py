import time
import numpy as np
from plotting import PlotDef, Curve
from procedures.base import Choice, MeasurementProcedure, WGFMUChannel, parameter
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


class PUNDProcedure(MeasurementProcedure):
	NAME = "PUND"
	PARAMETERS = (
		parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
		parameter('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 101, WGFMUChannel),
		parameter('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 102, WGFMUChannel),
		parameter('vmax', 'Vmax (V)', 1.0, float),
		parameter('base_voltage', 'Base Voltage (V)', 0.0, float),
		parameter('frequency', 'Frequency (Hz)', 1e3, float),
		parameter('pulse_delay', 'Pulse Delay (s)', 0.0, float),
		parameter('repetition_count', 'Repetition Count', 1, int),
		parameter('repetition_delay', 'Repetition Delay (s)', 0.0, float),
		parameter('invert_polarity', 'Invert Polarity (PNNPP)', False, bool),
		parameter('meas_range_1', 'Meas Range Ch1 (V)', WGFMU_MEASURE_VOLTAGE_RANGES[0][0], Choice(WGFMU_MEASURE_VOLTAGE_RANGES, int)),
		parameter('meas_range_2', 'Meas Range Ch2 (I)', WGFMU_MEASURE_CURRENT_RANGES[0][0], Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
	)

	def _build_pund_vectors(self):
		"""Build PUND waveform: N-P-P-N-N sequence (or inverted P-N-N-P-P)."""
		if self.frequency <= 0:
			raise ValueError("Frequency must be > 0")
		if self.vmax <= 0:
			raise ValueError("Vmax must be > 0")

		# NPPNN = [-1, 1, 1, -1, -1], inverted = PNNPP
		signs = [1, -1, -1, 1, 1] if self.invert_polarity else [-1, 1, 1, -1, -1]

		# Timing as fractions of period T = 1/f
		# Each pulse: 0.4T high, 0.4T low, 0.2T gap; edges 0.1T; total = 5T
		T = 1.0 / self.frequency
		pulse_width = 0.4 * T
		gap = 0.2 * T + self.pulse_delay
		edge = 0.1 * T

		vectors = [(edge, self.base_voltage)]
		for s in signs:
			vectors += [(pulse_width, (s * self.vmax) + self.base_voltage), 
			            (pulse_width, self.base_voltage), 
			            (gap, self.base_voltage)]
		vectors[-1] = (edge, self.base_voltage)  # last gap becomes trailing edge

		# Track active duration (before repetition_delay)
		self._active_duration = sum(dt for dt, _ in vectors)

		if self.repetition_delay > 0:
			vectors.append((self.repetition_delay, self.base_voltage))
		return vectors

	def measure(self, device):
		b1500 = self.b1500
		self.check_stop(b1500)
		self.log(f"Starting PUND on {device.name}")

		wgfmu = b1500.wgfmu
		pattern_pg = f"PUND_PG_{self.get_run_timestamp()}"
		pattern_iv = f"PUND_IV_{self.get_run_timestamp()}"

		try:
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

			self.check_stop(b1500)

			vectors = self._build_pund_vectors()
			pattern_duration = sum(dt for dt, _ in vectors)
			active_duration = self._active_duration

			# Compute sample interval and points per WGFMU constraints:
			# - interval >= 10 ns, in 10 ns resolution
			MIN_INTERVAL = 1e-8
			RESOLUTION = 1e-8
			raw_interval = 1e-3 / self.frequency
			sample_interval = max(raw_interval, MIN_INTERVAL)
			sample_interval = round(sample_interval / RESOLUTION) * RESOLUTION
			averaging_time = sample_interval
			active_points = int(active_duration / sample_interval)

			# For repetition_delay: sparse sampling (10 points or fewer)
			DELAY_POINTS = 100
			if self.repetition_delay > 0:
				delay_interval = max(self.repetition_delay / DELAY_POINTS, MIN_INTERVAL)
				delay_interval = round(delay_interval / RESOLUTION) * RESOLUTION
				delay_points = int(self.repetition_delay / delay_interval)
			else:
				delay_points = 0
				delay_interval = sample_interval

			wgfmu.create_pattern(pattern_pg, self.base_voltage)
			for dt, voltage in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_pg, dt, voltage)

			wgfmu.create_pattern(pattern_iv, 0.0)
			for dt, _ in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_iv, dt, 0.0)

			# Measure event for active portion (full rate)
			wgfmu.set_measure_event(
				pattern_pg,
				"meas_active",
				0.0,
				active_points,
				sample_interval,
				averaging_time,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)
			wgfmu.set_measure_event(
				pattern_iv,
				"meas_active",
				0.0,
				active_points,
				sample_interval,
				averaging_time,
				WGFMU_MEASURE_EVENT_DATA_AVERAGED,
			)

			# Measure event for repetition_delay portion (sparse)
			if delay_points > 0:
				wgfmu.set_measure_event(
					pattern_pg,
					"meas_delay",
					active_duration,
					delay_points,
					delay_interval,
					delay_interval,
					WGFMU_MEASURE_EVENT_DATA_AVERAGED,
				)
				wgfmu.set_measure_event(
					pattern_iv,
					"meas_delay",
					active_duration,
					delay_points,
					delay_interval,
					delay_interval,
					WGFMU_MEASURE_EVENT_DATA_AVERAGED,
				)

			self.check_stop(b1500)
			wgfmu.add_sequence(self.channel_1, pattern_pg, float(self.repetition_count))
			wgfmu.add_sequence(self.channel_2, pattern_iv, float(self.repetition_count))
			
			# Return both WGFMU channels to a known idle level after the repeated pattern.
			pattern_cleanup = f"CLEANUP_{self.get_run_timestamp()}"
			wgfmu.create_pattern(pattern_cleanup, self.base_voltage)
			wgfmu.add_vector(pattern_cleanup, 1e-4, 0.0) 
			wgfmu.add_sequence(self.channel_1, pattern_cleanup, 1.0)
			
			pattern_cleanup_iv = f"CLEANUP_IV_{self.get_run_timestamp()}"
			wgfmu.create_pattern(pattern_cleanup_iv, 0.0)
			wgfmu.add_vector(pattern_cleanup_iv, 1e-4, 0.0) 
			wgfmu.add_sequence(self.channel_2, pattern_cleanup_iv, 1.0)

			# Calculate expected limits for the overlay plot
			v_margin = self.vmax * 0.1
			xlim = (0, pattern_duration)
			ylim = (self.base_voltage - self.vmax - v_margin, self.base_voltage + self.vmax + v_margin)

			# Build Curve elements with color gradient for each rep
			# Blues for voltage, oranges for current
			max_reps_to_plot = min(self.repetition_count, 50)
			step = max(1, self.repetition_count // max_reps_to_plot)
			reps_to_plot = list(range(0, self.repetition_count, step))
			if (self.repetition_count - 1) not in reps_to_plot:
				reps_to_plot.append(self.repetition_count - 1)

			elements = []
			iv_elements = []
			qv_elements = []
			for idx, rep in enumerate(reps_to_plot):
				intensity = 0.2 + 0.7 * (idx / max(1, len(reps_to_plot) - 1))
				show = (rep == 0 or rep == self.repetition_count - 1)
				v_legend = f"V (rep {rep+1})" if show else ""
				i_legend = f"I (rep {rep+1})" if show else ""
				q_legend = f"Q (rep {rep+1})" if show else ""
				i_color = (intensity, 0.3 * intensity, 0)
				elements.append(Curve(f"V_{rep}", color=(0, 0, intensity),
				                      yaxis=0, legend_label=v_legend, show_in_legend=show))
				elements.append(Curve(f"I_{rep}", color=i_color,
				                      yaxis=1, legend_label=i_legend, show_in_legend=show))
				iv_elements.append(Curve(f"IV_{rep}", color=i_color,
				                         legend_label=i_legend, show_in_legend=show))
				qv_elements.append(Curve(f"QV_{rep}", color=i_color,
				                         legend_label=q_legend, show_in_legend=show))

			# Initialize live overlay plot
			runner = self.runner
			runner.configure_plot(f'PUND Overlay - {device.name}', [
				PlotDef("pund", row=0, col=0, colspan=2,
				        xlabel="Time (s)",
				        ylabels=("Voltage (V)", "Current (uA)"),
				        xlim=xlim,
				        ylims=(ylim, None),
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

			self.check_stop(b1500)
			wgfmu.execute()

			# Poll for data and plot live in overlay mode
			STATUS_COMPLETED = 10000

			data = []
			plotted_count = 0
			i_baseline_samples: dict[int, list] = {}
			i_baseline: dict[int, float] = {}
			q_accum: dict[int, float] = {}
			last_t_per_rep: dict[int, float] = {}

			while True:
				self.check_stop(b1500)

				status, elapsed, total = wgfmu.get_status()

				# Get available measurement data
				measured_1, total_1 = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, total_2 = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2)

				# Fetch new points
				if available > plotted_count:
					# Group points by rep for overlay plotting
					rep_batches: dict[int, dict] = {}

					for i in range(plotted_count, available):
						t_v, v = wgfmu.get_measure_value(self.channel_1, i)
						t_i, cur = wgfmu.get_measure_value(self.channel_2, i)
						t = t_v if t_v is not None else t_i
						data.append([t, cur, v])

						# Determine which rep this point belongs to
						# Timestamps are absolute across repetitions; map each sample back to an overlay trace.
						rep_idx = int(t / pattern_duration) if pattern_duration > 0 else 0
						rep_idx = min(rep_idx, self.repetition_count - 1)

						# Only plot reps in our display list
						if rep_idx in reps_to_plot:
							rel_t = t - (rep_idx * pattern_duration)

							if rep_idx not in rep_batches:
								rep_batches[rep_idx] = {'v': [], 'i': [], 'iv': [], 'qv': []}

							rep_batches[rep_idx]['v'].append((rel_t, v))
							rep_batches[rep_idx]['i'].append((rel_t, cur * 1e6))

							# Accumulate first 50 samples per rep for baseline
							if rep_idx not in i_baseline:
								samples = i_baseline_samples.setdefault(rep_idx, [])
								if len(samples) < 50:
									samples.append(cur)
								if len(samples) == 50:
									i_baseline[rep_idx] = float(np.mean(samples))

							# IV and QV use baseline-corrected current, only once baseline is ready
							if rep_idx in i_baseline:
								cur_adj = -(cur - i_baseline[rep_idx])
								rep_batches[rep_idx]['iv'].append((v, cur_adj * 1e6))

								if rep_idx not in q_accum:
									q_accum[rep_idx] = 0.0
									last_t_per_rep[rep_idx] = rel_t
								else:
									dt = rel_t - last_t_per_rep[rep_idx]
									if dt > 0:
										q_accum[rep_idx] += cur_adj * dt
									last_t_per_rep[rep_idx] = rel_t
								rep_batches[rep_idx]['qv'].append((v, q_accum[rep_idx] * 1e9))

					# Build batch update for all reps
					batch_update = {}
					for rep_idx, batch_data in rep_batches.items():
						batch_update[f"V_{rep_idx}"] = batch_data['v']
						batch_update[f"I_{rep_idx}"] = batch_data['i']
						batch_update[f"IV_{rep_idx}"] = batch_data['iv']
						batch_update[f"QV_{rep_idx}"] = batch_data['qv']

					if batch_update:
						runner.plot.append_batch(batch_update)

					plotted_count = available

				if status == STATUS_COMPLETED:
					break

				time.sleep(0.05)

			self.save_measurement_outputs(
				data,
				"PUND",
				device,
				["Time_s", "Current_A", "Voltage_V"],
				plot_suffix="_overlay.png",
			)
			self.log(f"PUND complete: {len(data)} points")
		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
