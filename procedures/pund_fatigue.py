"""
PUND Fatigue Procedure - High cycle count pulsing with sparse measurements.

Sends up to 1e12 PUND cycles using WGFMU hardware repetition.
Optionally measures at N points (linear or log spaced) throughout the run.
"""
import time
import numpy as np
from plotting import PlotDef, Curve
from procedures.base import MeasurementProcedure
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


class PUNDFatigueProcedure(MeasurementProcedure):
	def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
		super().__init__(settings, output_root, output_relative, runner, fallback_root)
		self.gpib_address = settings.get('gpib_address', 'GPIB0::17::INSTR')
		self.channel_1 = int(settings.get('channel_1', 101))  # PG + Vmeas
		self.channel_2 = int(settings.get('channel_2', 102))  # FastIV + Imeas
		
		self.base_voltage = float(settings.get('base_voltage', 0.0))
		self.vmax = float(settings.get('vmax', 1.0))
		self.frequency = float(settings.get('frequency', 1e3))
		self.pulse_delay = float(settings.get('pulse_delay', 0.0))
		self.cycle_count = float(settings.get('cycle_count', 1e6))
		self.invert_polarity = bool(settings.get('invert_polarity', False))

		# Measurement spacing
		self.points_per_decade = int(settings.get('points_per_decade', 10))

		self.meas_range_1 = int(settings.get('meas_range_1', WGFMU_MEASURE_VOLTAGE_RANGES[0][0]))
		self.meas_range_2 = int(settings.get('meas_range_2', WGFMU_MEASURE_CURRENT_RANGES[0][0]))

	def _build_pund_pattern(self):
		"""Build PUND waveform vectors: N-P-P-N-N (or inverted P-N-N-P-P)."""
		if self.frequency <= 0:
			raise ValueError("Frequency must be > 0")
		if self.vmax <= 0:
			raise ValueError("Vmax must be > 0")

		signs = [1, -1, -1, 1, 1] if self.invert_polarity else [-1, 1, 1, -1, -1]

		# Timing as fractions of period T = 1/f
		# Each pulse: 0.4T at ±Vmax, 0.4T at base_voltage, 0.2T gap; edges 0.1T
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
		return vectors

	def _build_pn_pattern(self):
		"""Build PN switching waveform vectors: P-N (or inverted N-P)."""
		signs = [-1, 1] if self.invert_polarity else [1, -1]
		T = 1.0 / self.frequency
		pulse_width = 0.4 * T
		gap = 0.2 * T + self.pulse_delay
		edge = 0.1 * T

		vectors = [(edge, self.base_voltage)]
		for s in signs:
			vectors += [(pulse_width, (s * self.vmax) + self.base_voltage), 
			            (pulse_width, self.base_voltage), 
			            (gap, self.base_voltage)]
		vectors[-1] = (edge, self.base_voltage)
		return vectors

	def _get_measure_cycles(self):
		"""Return list of cycle numbers at which to measure.
		
		Uses points_per_decade for linear spacing within each decade.
		For example, with ppd=10 and cycle_count=1e3:
		  1,2,3,4,5,6,7,8,9,10,20,30,...,100,200,300,...,1000
		"""
		n = int(self.cycle_count)
		ppd = self.points_per_decade
		if ppd <= 0 or n < 1:
			return []
		
		return self._compute_measure_cycles(n, ppd)
	
	@staticmethod
	def _compute_measure_cycles(cycle_count: int, points_per_decade: int) -> list:
		"""Compute measurement cycles with linear spacing per decade.
		
		With ppd=10: 1,2,...,10,20,30,...,100,200,300,...
		With ppd=5:  1,2,3,4,5,20,40,60,80,100,200,400,...
		With ppd=2:  1,2,50,100,500,1000,...
		With ppd=1:  1,100,1000,...
		With ppd=20: 1,2,...,10,15,20,25,...,100,150,200,...
		"""
		n = int(cycle_count)
		ppd = points_per_decade
		if ppd <= 0 or n < 1:
			return []
		
		cycles = []
		decade = 0
		while True:
			base = 10 ** decade
			next_base = base * 10
			
			if decade == 0:
				# First decade: only first ppd cycles (1,2,...,ppd)
				# Cap at (1,2,...,10)
				for c in range(1, min(ppd + 1, 10 + 1, n + 1)):
					cycles.append(c)
			else:
				# step = next_base / ppd (integer division, at least 1)
				# For ppd=10: step=10 -> 20,30,...,100
				# For ppd=5: step=20 -> 20,40,60,80,100
				# For ppd=2: step=50 -> 50,100
				# For ppd=20: step=5 -> 15,20,25,...,100
				# For ppd=50: step=2 -> 12,14,16,...,100
				step = max(1, next_base // ppd)
				
				# Start after base to avoid duplicate with previous decade's end
				if step > base:
					start = step  # step is already past base
				elif step == base:
					start = step * 2  # skip base (which equals step)
				else:  # step < base (ppd > 10)
					start = base + step
				
				for c in range(start, next_base + 1, step):
					if c > n:
						break
					cycles.append(c)
			
			if next_base >= n:
				break
			decade += 1
		
		return cycles

	@staticmethod
	def get_preview_info(cycle_count: float, frequency: float, points_per_decade: int) -> dict:
		"""Generate preview info for UI without instantiating the procedure.
		
		Returns dict with:
		  - measure_cycles: list of cycle numbers where measurements occur
		  - total_measurements: count of measurement points
		  - pattern_duration: single cycle duration in seconds
		  - total_duration: estimated total run time
		  - decades: number of decades spanned
		"""
		n = int(cycle_count)
		ppd = points_per_decade
		
		# Use shared method for cycle calculation
		measure_cycles = PUNDFatigueProcedure._compute_measure_cycles(n, ppd)
		
		# Pattern duration for fatigue is the PN cycle: 2 pulses instead of 5
		T = 1.0 / frequency if frequency > 0 else 1.0
		meas_duration = 5.2 * T 
		fatigue_duration = 2.2 * T
		
		# Most cycles are fatigue. So approximate total duration by fatigue cycles.
		total_duration = (fatigue_duration * (cycle_count - len(measure_cycles))) + (meas_duration * len(measure_cycles))
		
		return {
			'measure_cycles': measure_cycles,
			'total_measurements': len(measure_cycles),
			'pattern_duration': meas_duration,
			'total_duration': total_duration,
			'decades': np.log10(max(n, 1)),
		}

	def run(self, b1500, device):
		self.check_stop(b1500)

		vectors_meas = self._build_pund_pattern()
		vectors_fat = self._build_pn_pattern()
		pattern_duration_meas = sum(dt for dt, _ in vectors_meas)
		pattern_duration_fat = sum(dt for dt, _ in vectors_fat)
		
		measure_cycles = self._get_measure_cycles()
		total_time = (pattern_duration_fat * (self.cycle_count - len(measure_cycles))) + (pattern_duration_meas * len(measure_cycles))

		self.log(f"Starting PUND Fatigue on {device.name}")
		self.log(f"  {self.cycle_count:.2e} cycles @ {self.frequency:.0f} Hz, Vmax={self.vmax}V")
		self.log(f"  {len(measure_cycles)} measurement points ({self.points_per_decade} pts/decade)")
		self.log(f"  Estimated duration: {total_time:.1f} s (+ initialization + data transfer ≈ 25 s)")

		wgfmu = b1500.wgfmu
		ts = self.get_run_timestamp()
		pattern_fat_pg = f"FAT_PG_{ts}"  # fatigue pattern ch1 (PUND waveform, no measure)
		pattern_fat_iv = f"FAT_IV_{ts}"  # fatigue pattern ch2 (0V, no measure)
		pattern_meas_pg = f"MEAS_PG_{ts}"  # measure pattern ch1
		pattern_meas_iv = f"MEAS_IV_{ts}"  # measure pattern ch2

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

			# Compute sampling parameters for measure pattern
			MIN_INTERVAL = 1e-8
			RESOLUTION = 1e-8
			raw_interval = 1e-3 / self.frequency
			sample_interval = max(raw_interval, MIN_INTERVAL)
			sample_interval = round(sample_interval / RESOLUTION) * RESOLUTION
			sample_points = int(pattern_duration_meas / sample_interval)

			# Create fatigue pattern for ch1 (PG mode - applies PN waveform, no measure event)
			wgfmu.create_pattern(pattern_fat_pg, self.base_voltage)
			for dt, voltage in vectors_fat:
				if dt > 0:
					wgfmu.add_vector(pattern_fat_pg, dt, voltage)

			# Create fatigue pattern for ch2 (FastIV mode - holds at 0V, no measure event)
			wgfmu.create_pattern(pattern_fat_iv, 0.0)
			for dt, _ in vectors_fat:
				if dt > 0:
					wgfmu.add_vector(pattern_fat_iv, dt, 0.0)

			# Create measure patterns with sampling
			wgfmu.create_pattern(pattern_meas_pg, self.base_voltage)
			for dt, voltage in vectors_meas:
				if dt > 0:
					wgfmu.add_vector(pattern_meas_pg, dt, voltage)

			wgfmu.create_pattern(pattern_meas_iv, 0.0)
			for dt, _ in vectors_meas:
				if dt > 0:
					wgfmu.add_vector(pattern_meas_iv, dt, 0.0)

			wgfmu.set_measure_event(
				pattern_meas_pg, "meas", 0.0, sample_points,
				sample_interval, sample_interval, WGFMU_MEASURE_EVENT_DATA_AVERAGED
			)
			wgfmu.set_measure_event(
				pattern_meas_iv, "meas", 0.0, sample_points,
				sample_interval, sample_interval, WGFMU_MEASURE_EVENT_DATA_AVERAGED
			)

			# Build sequence: interleave fatigue bursts with measure cycles
			prev_cycle = 0
			for mc in measure_cycles:
				fatigue_count = mc - prev_cycle - 1
				if fatigue_count > 0:
					wgfmu.add_sequence(self.channel_1, pattern_fat_pg, fatigue_count)
					wgfmu.add_sequence(self.channel_2, pattern_fat_iv, fatigue_count)
				# Measure cycle
				wgfmu.add_sequence(self.channel_1, pattern_meas_pg, 1)
				wgfmu.add_sequence(self.channel_2, pattern_meas_iv, 1)
				prev_cycle = mc

			# Remaining fatigue cycles after last measurement
			remaining = int(self.cycle_count) - prev_cycle
			if remaining > 0:
				wgfmu.add_sequence(self.channel_1, pattern_fat_pg, remaining)
				wgfmu.add_sequence(self.channel_2, pattern_fat_iv, remaining)

			pattern_cleanup = f"CLEANUP_{ts}"
			wgfmu.create_pattern(pattern_cleanup, self.base_voltage)
			wgfmu.add_vector(pattern_cleanup, 1e-4, 0.0) 
			wgfmu.add_sequence(self.channel_1, pattern_cleanup, 1.0)
			
			pattern_cleanup_iv = f"CLEANUP_IV_{ts}"
			wgfmu.create_pattern(pattern_cleanup_iv, 0.0)
			wgfmu.add_vector(pattern_cleanup_iv, 1e-4, 0.0) 
			wgfmu.add_sequence(self.channel_2, pattern_cleanup_iv, 1.0)

			wgfmu.execute()

			# --- Set up live plot before polling ---
			runner = self.runner
			base = self.format_filename("PUND_Fatigue", device.name)
			
			# Build Curve elements with logarithmic color gradient for each measured cycle
			# Blues for voltage, oranges for current
			max_cycles_to_plot = min(len(measure_cycles), 50)
			step_plot = max(1, len(measure_cycles) // max_cycles_to_plot)
			cycles_to_plot_idx = list(range(0, len(measure_cycles), step_plot))
			if (len(measure_cycles) - 1) not in cycles_to_plot_idx:
				cycles_to_plot_idx.append(len(measure_cycles) - 1)

			# For logarithmic color scaling: use log10 of cycle number
			max_cycle = measure_cycles[-1] if measure_cycles else 1
			log_max = np.log10(max(max_cycle, 1))

			elements = []
			iv_elements = []
			qv_elements = []
			meas_idx_to_sources = {}  # meas_idx -> (v_source, i_source, iv_source, qv_source)
			for plot_idx, meas_idx in enumerate(cycles_to_plot_idx):
				cycle_num = measure_cycles[meas_idx]
				log_cycle = np.log10(max(cycle_num, 1))
				intensity = 0.2 + 0.7 * (log_cycle / max(log_max, 1))
				show = (meas_idx == 0 or meas_idx == len(measure_cycles) - 1)
				v_legend = f"V (cycle {cycle_num})" if show else ""
				i_legend = f"I (cycle {cycle_num})" if show else ""
				q_legend = f"Q (cycle {cycle_num})" if show else ""
				i_color = (intensity, 0.3 * intensity, 0)
				elements.append(Curve(f"V_{cycle_num}", color=(0, 0, intensity),
				                      yaxis=0, legend_label=v_legend, show_in_legend=show))
				elements.append(Curve(f"I_{cycle_num}", color=i_color,
				                      yaxis=1, legend_label=i_legend, show_in_legend=show))
				iv_elements.append(Curve(f"IV_{cycle_num}", color=i_color,
				                         legend_label=i_legend, show_in_legend=show))
				qv_elements.append(Curve(f"QV_{cycle_num}", color=i_color,
				                         legend_label=q_legend, show_in_legend=show))
				meas_idx_to_sources[meas_idx] = (f"V_{cycle_num}", f"I_{cycle_num}",
				                                  f"IV_{cycle_num}", f"QV_{cycle_num}")

			# Calculate expected limits for the overlay plot
			v_margin = self.vmax * 0.1
			xlim = (0, pattern_duration_meas)
			ylim = (self.base_voltage - self.vmax - v_margin, self.base_voltage + self.vmax + v_margin)

			runner.configure_plot(f'PUND Fatigue Overlay - {device.name}', [
				PlotDef("pund_fat", row=0, col=0, colspan=2,
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

			# Poll for data and plot live
			STATUS_COMPLETED = 10000
			plotted_count = 0
			data_ch1 = []
			data_ch2 = []
			i_baseline_samples: dict[int, list] = {}
			i_baseline: dict[int, float] = {}
			q_accum: dict[int, float] = {}
			last_t_per_cycle: dict[int, float] = {}

			while True:
				self.check_stop(b1500)
				status, elapsed, total = wgfmu.get_status()

				# Get available measurement data
				measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2)

				# Fetch and plot new points
				if available > plotted_count:
					# Group points by measurement cycle for overlay plotting
					cycle_batches: dict[int, dict] = {}

					for i in range(plotted_count, available):
						self.check_stop(b1500)

						t_v, v = wgfmu.get_measure_value(self.channel_1, i)
						t_i, cur = wgfmu.get_measure_value(self.channel_2, i)
						data_ch1.append((t_v, v))
						data_ch2.append((t_i, cur))

						# Determine which measurement cycle this point belongs to
						meas_idx = i // sample_points
						sample_in_cycle = i % sample_points

						# Only plot cycles in our display list
						if meas_idx in cycles_to_plot_idx and meas_idx < len(measure_cycles):
							rel_t = sample_in_cycle * sample_interval

							if meas_idx not in cycle_batches:
								cycle_batches[meas_idx] = {'v': [], 'i': [], 'iv': [], 'qv': []}
							cycle_batches[meas_idx]['v'].append((rel_t, v))
							cycle_batches[meas_idx]['i'].append((rel_t, cur * 1e6))

							# Accumulate first 50 samples per cycle for baseline
							if meas_idx not in i_baseline:
								samples = i_baseline_samples.setdefault(meas_idx, [])
								if len(samples) < 50:
									samples.append(cur)
								if len(samples) == 50:
									i_baseline[meas_idx] = float(np.mean(samples))

							# IV and QV use baseline-corrected current, only once baseline is ready
							if meas_idx in i_baseline:
								cur_adj = -(cur - i_baseline[meas_idx])
								cycle_batches[meas_idx]['iv'].append((v, cur_adj * 1e6))

								if meas_idx not in q_accum:
									q_accum[meas_idx] = 0.0
									last_t_per_cycle[meas_idx] = rel_t
								else:
									dt = rel_t - last_t_per_cycle[meas_idx]
									if dt > 0:
										q_accum[meas_idx] += cur_adj * dt
									last_t_per_cycle[meas_idx] = rel_t
								cycle_batches[meas_idx]['qv'].append((v, q_accum[meas_idx] * 1e9))

					# Build batch update for all cycles
					batch_update = {}
					for meas_idx, batch_data in cycle_batches.items():
						if meas_idx in meas_idx_to_sources:
							v_source, i_source, iv_source, qv_source = meas_idx_to_sources[meas_idx]
							batch_update[v_source] = batch_data['v']
							batch_update[i_source] = batch_data['i']
							batch_update[iv_source] = batch_data['iv']
							batch_update[qv_source] = batch_data['qv']

					if batch_update:
						runner.plot.append_batch(batch_update)

					plotted_count = available
					self.check_stop(b1500)

				if status == STATUS_COMPLETED:
					break

				time.sleep(0.05)

			# Build data arrays from collected points
			data = [data_ch1, data_ch2]

			# Save data: each measurement point is sample_points samples
			# Group by measurement cycle
			all_rows = []
			for meas_idx, cycle_num in enumerate(measure_cycles):
				offset = meas_idx * sample_points
				for i in range(sample_points):
					if offset + i < len(data[0]) and offset + i < len(data[1]):
						t_v, voltage = data[0][offset + i]
						t_i, current = data[1][offset + i]
						all_rows.append([cycle_num, t_v, voltage, current])

			if all_rows:
				filename = f"{base}.csv"
				self.save_data(all_rows, filename,
					["Cycle", "Time_s", "Voltage_V", "Current_A"], add_timestamp=False)

			# Finalize and save the overlay plot
			if measure_cycles:
				plot_filename = f'{base}_overlay.png'
				runner.plot.save_png(plot_filename, self.output_root, self.output_relative, self.fallback_root)

			self.log(f"PUND Fatigue complete: {self.cycle_count:.2e} cycles, {len(measure_cycles)} measurements")

		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
