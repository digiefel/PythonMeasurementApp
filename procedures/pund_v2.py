"""
PUND v2 - PUND with independent positive, base and negative levels.

Like PUND, but the positive pulses peak at Vpos, the negative pulses at Vneg,
and the waveform rests at Vbase between pulses. All ramps have the same slew
rate: the tallest pulse ramps from Vbase to its peak in 0.4/f, as in PUND, and
the shorter pulses ramp at the same speed, so they end sooner.
"""
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


class PUNDv2Procedure(MeasurementProcedure):
	NAME = "PUND v2"
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
		parameter('frequency', 'Frequency (Hz)', 1e3, float,
		          help='Sets the ramp speed: the tallest pulse goes from Vbase to its peak in 0.4/f.'),
		parameter('pulse_delay', 'Pulse Delay (s)', 0.0, float),
		parameter('repetition_count', 'Repetition Count', 1, int),
		parameter('repetition_delay', 'Repetition Delay (s)', 0.0, float),
		parameter('invert_polarity', 'Invert Polarity (PNNPP)', False, bool),
		parameter('meas_range_1', 'Meas Range Ch1 (V)', WGFMU_MEASURE_VOLTAGE_RANGES[0][0], Choice(WGFMU_MEASURE_VOLTAGE_RANGES, int)),
		parameter('meas_range_2', 'Meas Range Ch2 (I)', WGFMU_MEASURE_CURRENT_RANGES[0][0], Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
	)

	def _build_pund_vectors(self):
		"""Build PUND waveform: N-P-P-N-N sequence (or inverted P-N-N-P-P)."""
		levels = [self.v_pos, self.v_neg, self.v_neg, self.v_pos, self.v_pos] if self.invert_polarity \
			else [self.v_neg, self.v_pos, self.v_pos, self.v_neg, self.v_neg]

		# Timing as fractions of period T = 1/f, as in PUND: the tallest pulse
		# ramps for 0.4T each way. Every ramp uses that same slew rate, so a pulse
		# of height |V - Vbase| ramps for 0.4T * |V - Vbase| / Vmax each way.
		T = 1.0 / self.frequency
		vmax = max(abs(self.v_pos - self.v_base), abs(self.v_neg - self.v_base))
		gap = 0.2 * T + self.pulse_delay
		edge = 0.1 * T

		vectors = [(edge, self.v_base)]
		for level in levels:
			ramp = 0.4 * T * abs(level - self.v_base) / vmax
			# Ramp to the peak, ramp back to base, then hold base before the next pulse.
			vectors += [(ramp, level),
			            (ramp, self.v_base),
			            (gap, self.v_base)]
		vectors[-1] = (edge, self.v_base)  # last gap becomes trailing edge

		# Track active duration (before repetition_delay)
		self._active_duration = sum(dt for dt, _ in vectors)

		if self.repetition_delay > 0:
			vectors.append((self.repetition_delay, self.v_base))
		return vectors

	def measure(self, device):
		b1500 = self.b1500
		self.check_stop(b1500)
		self.log(f"Starting PUND v2 on {device.name}")

		wgfmu = b1500.wgfmu
		pattern_pg = f"PUNDV2_PG_{self.get_run_timestamp()}"
		pattern_iv = f"PUNDV2_IV_{self.get_run_timestamp()}"

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
			# The default target is 1000 samples per pulse period, then rounded to hardware resolution.
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

			# Channel 1 owns the voltage waveform. Channel 2 stays at 0 V but measures current through FastIV.
			wgfmu.create_pattern(pattern_pg, self.v_base)
			for dt, voltage in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_pg, dt, voltage)

			wgfmu.create_pattern(pattern_iv, 0.0)
			for dt, _ in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_iv, dt, 0.0)

			# Measure event for active portion (full rate)
			# The active event excludes repetition_delay so pulse edges remain densely sampled.
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
				# Long idle delays are sampled sparsely to keep file size and transfer time reasonable.
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
			wgfmu.create_pattern(pattern_cleanup, self.v_base)
			wgfmu.add_vector(pattern_cleanup, 1e-4, 0.0) 
			wgfmu.add_sequence(self.channel_1, pattern_cleanup, 1.0)
			
			pattern_cleanup_iv = f"CLEANUP_IV_{self.get_run_timestamp()}"
			wgfmu.create_pattern(pattern_cleanup_iv, 0.0)
			wgfmu.add_vector(pattern_cleanup_iv, 1e-4, 0.0) 
			wgfmu.add_sequence(self.channel_2, pattern_cleanup_iv, 1.0)

			# Calculate expected limits for the overlay plot
			v_low, v_high = min(self.v_pos, self.v_neg, self.v_base), max(self.v_pos, self.v_neg, self.v_base)
			v_margin = (v_high - v_low) * 0.1
			xlim = (0, pattern_duration)
			ylim = (v_low - v_margin, v_high + v_margin)

			# Build Curve elements with color gradient for each rep
			# Blues for voltage, oranges for current
			# Plot at most 50 repetitions, but always include the first and last repetitions.
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
			runner.configure_plot(f'PUND v2 Overlay - {device.name}', [
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

					# One call per channel for all new samples, instead of two calls per sample.
					samples_v = wgfmu.read_chunk(self.channel_1, plotted_count, available - plotted_count)
					samples_i = wgfmu.read_chunk(self.channel_2, plotted_count, available - plotted_count)
					for (t_v, v), (t_i, cur) in zip(samples_v, samples_i):
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
							# Baseline correction makes the IV/QV loops easier to compare across repetitions.
							if rep_idx not in i_baseline:
								samples = i_baseline_samples.setdefault(rep_idx, [])
								if len(samples) < 50:
									samples.append(cur)
								if len(samples) == 50:
									i_baseline[rep_idx] = float(np.mean(samples))

							# IV and QV use baseline-corrected current, only once baseline is ready
							if rep_idx in i_baseline:
								# Negate current so positive switching charge plots in the expected direction.
								cur_adj = -(cur - i_baseline[rep_idx])
								rep_batches[rep_idx]['iv'].append((v, cur_adj * 1e6))

								if rep_idx not in q_accum:
									q_accum[rep_idx] = 0.0
									last_t_per_rep[rep_idx] = rel_t
								else:
									dt = rel_t - last_t_per_rep[rep_idx]
									if dt > 0:
										# Integrate current over time to accumulate charge for the Q-V loop.
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

					plotted_count = len(data)

				if status == STATUS_COMPLETED:
					break

				time.sleep(0.05)

			self.save_measurement_outputs(
				data,
				"PUND_v2",
				device,
				["Time_s", "Current_A", "Voltage_V"],
			)
			self.log(f"PUND v2 complete: {len(data)} points")
		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
