"""
PUND Fatigue Procedure - High cycle count pulsing with sparse measurements.

Sends up to 1e12 PUND cycles using WGFMU hardware repetition.
Optionally measures at N points (linear or log spaced) throughout the run.
"""

import numpy as np
from procedures.base import MeasurementProcedure
from bindings import (
	WGFMUSession,
	WGFMU_OPERATION_MODE_PG,
	WGFMU_OPERATION_MODE_FASTIV,
	WGFMU_FORCE_VOLTAGE_RANGE_AUTO,
	WGFMU_MEASURE_MODE_VOLTAGE,
	WGFMU_MEASURE_MODE_CURRENT,
	WGFMU_MEASURE_ENABLED_ENABLE,
	WGFMU_MEASURE_EVENT_DATA_AVERAGED,
	WGFMU_MEASURE_VOLTAGE_RANGES,
	WGFMU_MEASURE_CURRENT_RANGES,
)


class PUNDFatigueProcedure(MeasurementProcedure):
	def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
		super().__init__(settings, output_root, output_relative, runner, fallback_root)
		self.gpib_address = settings.get('gpib_address', 'GPIB0::17::INSTR')
		self.channel_1 = int(settings.get('channel_1', 101))  # PG + Vmeas
		self.channel_2 = int(settings.get('channel_2', 102))  # FastIV + Imeas
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
		# Each pulse: 0.4T at ±Vmax, 0.4T at 0V, 0.2T gap; edges 0.1T
		T = 1.0 / self.frequency
		pulse_width = 0.4 * T
		gap = 0.2 * T + self.pulse_delay
		edge = 0.1 * T

		vectors = [(edge, 0.0)]
		for s in signs:
			vectors += [(pulse_width, s * self.vmax), (pulse_width, 0.0), (gap, 0.0)]
		vectors[-1] = (edge, 0.0)  # last gap becomes trailing edge
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
		"""
		n = int(cycle_count)
		ppd = points_per_decade
		if ppd <= 0 or n < 1:
			return []
		
		# Cap at 10 points per decade
		ppd = min(ppd, 10)
		
		cycles = []
		decade = 0
		while True:
			base = 10 ** decade
			next_base = base * 10
			
			if decade == 0:
				# First decade: only first ppd cycles (1,2,...,ppd)
				for c in range(1, min(ppd + 1, n + 1)):
					cycles.append(c)
			else:
				# step = base * round(10/ppd)
				# For ppd=10: step=10 -> 20,30,...,100
				# For ppd=5: step=20 -> 20,40,60,80,100
				# For ppd=2: step=50 -> 50,100
				step_mult = round(10 / ppd)
				step = base * step_mult
				
				# Start after base to avoid duplicate with previous decade's end
				start = step if step > base else step * 2
				
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
		
		# Pattern duration: 5 pulses, each with 0.4T on + 0.4T off + 0.2T gap, plus edges
		# Total = 5 * (0.4 + 0.4 + 0.2) * T + 0.2T edges = 5.2 * T
		T = 1.0 / frequency if frequency > 0 else 1.0
		pattern_duration = 5.2 * T  # approximate
		total_duration = pattern_duration * cycle_count
		
		return {
			'measure_cycles': measure_cycles,
			'total_measurements': len(measure_cycles),
			'pattern_duration': pattern_duration,
			'total_duration': total_duration,
			'decades': np.log10(max(n, 1)),
		}

	def run(self, b1500, device):
		self.check_stop(b1500)

		vectors = self._build_pund_pattern()
		pattern_duration = sum(dt for dt, _ in vectors)
		measure_cycles = self._get_measure_cycles()
		total_time = pattern_duration * self.cycle_count

		self.log(f"Starting PUND Fatigue on {device.name}")
		self.log(f"  {self.cycle_count:.2e} cycles @ {self.frequency:.0f} Hz, Vmax={self.vmax}V")
		self.log(f"  {len(measure_cycles)} measurement points ({self.points_per_decade} pts/decade)")
		self.log(f"  Estimated duration: {total_time:.1f} s (+ initialization + data transfer ≈ 25 s)")

		wgfmu = WGFMUSession(self.gpib_address)
		ts = self.get_run_timestamp()
		pattern_fat = f"FAT_{ts}"  # fatigue pattern (no measure)
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
			sample_points = int(pattern_duration / sample_interval)

			# Create fatigue pattern (no measure event) - same waveform for both channels
			wgfmu.create_pattern(pattern_fat, 0.0)
			for dt, voltage in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_fat, dt, voltage)

			# Create measure patterns with sampling
			wgfmu.create_pattern(pattern_meas_pg, 0.0)
			for dt, voltage in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_meas_pg, dt, voltage)

			wgfmu.create_pattern(pattern_meas_iv, 0.0)
			for dt, _ in vectors:
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
					wgfmu.add_sequence(self.channel_1, pattern_fat, fatigue_count)
					wgfmu.add_sequence(self.channel_2, pattern_fat, fatigue_count)
				# Measure cycle
				wgfmu.add_sequence(self.channel_1, pattern_meas_pg, 1)
				wgfmu.add_sequence(self.channel_2, pattern_meas_iv, 1)
				prev_cycle = mc

			# Remaining fatigue cycles after last measurement
			remaining = int(self.cycle_count) - prev_cycle
			if remaining > 0:
				wgfmu.add_sequence(self.channel_1, pattern_fat, remaining)
				wgfmu.add_sequence(self.channel_2, pattern_fat, remaining)

			wgfmu.execute()
			wgfmu.wait_until_completed()

			# Read measurement data
			data = []
			for ch in [self.channel_1, self.channel_2]:
				measured, _ = wgfmu.get_measure_value_size(ch)
				ch_data = []
				for i in range(measured):
					t, v = wgfmu.get_measure_value(ch, i)
					ch_data.append((t, v))
				data.append(ch_data)

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
				filename = self.format_filename("PUND_Fatigue", device.name) + ".csv"
				self.save_data(all_rows, filename,
					["Cycle", "Time_s", "Voltage_V", "Current_A"], add_timestamp=False)

			self.log(f"PUND Fatigue complete: {self.cycle_count:.2e} cycles, {len(measure_cycles)} measurements")

		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
				wgfmu.close()
			except Exception:
				pass
