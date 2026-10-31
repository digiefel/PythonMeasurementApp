"""First-order reversal curves (FORC) on a ferroelectric capacitor with the WGFMU.

The waveform saturates at Vmax, then repeatedly goes down to a reversal voltage
Vr and back up to Vmax. Each rising branch from Vr to Vmax is one FORC. The
reversal voltages are evenly spaced from Vmax down to Vmin, and every ramp has
the same slope, so all FORCs are measured at the same sweep rate.

The live plot shows the voltage and current against time, one continuous Q-V
curve, and an I(Vr, V) heatmap preview: the measured current of each finished
FORC at the samples closest to the reversal voltages.
"""
import time
import numpy as np
from plotting import PlotDef, Curve, Heatmap
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


class FORCProcedure(MeasurementProcedure):
	NAME = "FORC"
	PARAMETERS = (
		parameter('gpib_address', 'GPIB Address', 'GPIB0::17::INSTR', str),
		parameter('channel_1', 'WGFMU Channel 1 (PG Vmeas)', 101, WGFMUChannel),
		parameter('channel_2', 'WGFMU Channel 2 (FastIV Imeas)', 102, WGFMUChannel),
		parameter('vmax', 'Vmax (V)', 1.0, float,
		          help="Saturation voltage. Every reversal curve ends here."),
		parameter('vmin', 'Vmin (V)', -1.0, float,
		          help="Lowest reversal voltage, reached by the last reversal curve."),
		parameter('forc_count', 'Number of Reversal Curves', 20, int,
		          help="Reversal voltages are evenly spaced from Vmax down to Vmin."),
		parameter('frequency', 'Frequency (Hz)', 1e3, float,
		          help="Frequency of one full Vmax → Vmin → Vmax triangle. "
		               "All ramps use this slope, so shorter curves take less time."),
		parameter('meas_range_1', 'Meas Range Ch1 (V)', WGFMU_MEASURE_VOLTAGE_RANGES[0][0], Choice(WGFMU_MEASURE_VOLTAGE_RANGES, int)),
		parameter('meas_range_2', 'Meas Range Ch2 (I)', WGFMU_MEASURE_CURRENT_RANGES[0][0], Choice(WGFMU_MEASURE_CURRENT_RANGES, int)),
	)

	def _build_forc_vectors(self):
		"""Build the FORC waveform as (duration, end voltage) ramps.

		Returns the vectors, the time of the initial 0 V hold, and one
		(start time, end time, Vr) entry per reversal curve.
		"""
		if self.frequency <= 0:
			raise ValueError("Frequency must be > 0")
		if self.vmax <= self.vmin:
			raise ValueError("Vmax must be greater than Vmin")
		if self.forc_count < 1:
			raise ValueError("Number of reversal curves must be at least 1")

		# One full Vmax -> Vmin -> Vmax triangle lasts 1/f; every ramp shares its slope.
		slope = 2 * (self.vmax - self.vmin) * self.frequency
		# The 0 V hold at the start gives a current baseline, like the leading edge in PUND.
		hold = 0.1 / self.frequency

		vectors = [(hold, 0.0), (abs(self.vmax) / slope, self.vmax)]
		t = sum(dt for dt, _ in vectors)
		forcs = []
		for vr in np.linspace(self.vmax, self.vmin, self.forc_count + 1)[1:]:
			ramp = (self.vmax - vr) / slope
			vectors += [(ramp, float(vr)), (ramp, self.vmax)]
			forcs.append((t + ramp, t + 2 * ramp, float(vr)))
			t += 2 * ramp
		vectors.append((abs(self.vmax) / slope, 0.0))
		return vectors, hold, forcs

	def measure(self, device):
		b1500 = self.b1500
		self.check_stop(b1500)
		self.log(f"Starting FORC on {device.name}")

		wgfmu = b1500.wgfmu
		pattern_pg = f"FORC_PG_{self.get_run_timestamp()}"
		pattern_iv = f"FORC_IV_{self.get_run_timestamp()}"

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

			vectors, hold, forcs = self._build_forc_vectors()
			pattern_duration = sum(dt for dt, _ in vectors)

			# 1000 samples per full triangle, rounded to the 10 ns WGFMU resolution.
			RESOLUTION = 1e-8
			sample_interval = max(round(1e-3 / self.frequency / RESOLUTION), 1) * RESOLUTION
			points = int(pattern_duration / sample_interval)
			baseline_points = max(1, int(hold / sample_interval))

			# Channel 1 owns the voltage waveform. Channel 2 stays at 0 V but measures current through FastIV.
			wgfmu.create_pattern(pattern_pg, 0.0)
			wgfmu.create_pattern(pattern_iv, 0.0)
			for dt, voltage in vectors:
				if dt > 0:
					wgfmu.add_vector(pattern_pg, dt, voltage)
					wgfmu.add_vector(pattern_iv, dt, 0.0)

			for pattern in (pattern_pg, pattern_iv):
				wgfmu.set_measure_event(
					pattern, "meas", 0.0, points, sample_interval, sample_interval,
					WGFMU_MEASURE_EVENT_DATA_AVERAGED,
				)

			wgfmu.add_sequence(self.channel_1, pattern_pg, 1.0)
			wgfmu.add_sequence(self.channel_2, pattern_iv, 1.0)

			# The map samples every curve at the reversal voltages: one column per curve, one row per voltage.
			v_grid = np.linspace(self.vmax, self.vmin, self.forc_count + 1)  # top row first
			step = (self.vmax - self.vmin) / self.forc_count
			map_bounds_min = (self.vmin - step / 2, self.vmin - step / 2)
			map_bounds_max = (self.vmax - step / 2, self.vmax + step / 2)

			v_margin = 0.1 * (self.vmax - self.vmin)
			runner = self.runner
			runner.configure_plot(f'FORC - {device.name}', [
				PlotDef("waveform", row=0, col=0, colspan=2,
				        xlabel="Time (s)",
				        ylabels=("Voltage (V)", "Current (uA)"),
				        xlim=(0, pattern_duration),
				        ylims=((min(self.vmin, 0.0) - v_margin, max(self.vmax, 0.0) + v_margin), None),
				        elements=[
					        Curve("V", color=(0, 0, 0.8), yaxis=0, legend_label="V"),
					        Curve("I", color=(0.9, 0.27, 0), yaxis=1, legend_label="I"),
				        ]),
				PlotDef("qv", row=1, col=0,
				        xlabel="Voltage (V)",
				        ylabels=("Charge (nC)",),
				        elements=[Curve("QV", color=(0.9, 0.27, 0), show_in_legend=False)]),
				PlotDef("map", row=1, col=1,
				        xlabel="Reversal Voltage Vr (V)",
				        ylabels=("Voltage (V)",),
				        xlim=(map_bounds_min[0], map_bounds_max[0]),
				        ylims=((map_bounds_min[1], map_bounds_max[1]),),
				        elements=[
					        Heatmap("MAP", rows=self.forc_count + 1, cols=self.forc_count,
					                bounds_min=map_bounds_min, bounds_max=map_bounds_max,
					                show_in_legend=False),
				        ]),
			], row_ratios=[2.0, 1.0])

			self.check_stop(b1500)
			wgfmu.execute()

			STATUS_COMPLETED = 10000
			data = []
			baseline_samples = []
			baseline = None
			charge = 0.0
			last_t = None
			forc_samples = [[] for _ in forcs]  # (V, I) on each rising branch
			drawn_forcs = 0

			while True:
				self.check_stop(b1500)
				status, _, _ = wgfmu.get_status()

				measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2)

				if available > len(data):
					samples_v = wgfmu.read_chunk(self.channel_1, len(data), available - len(data))
					samples_i = wgfmu.read_chunk(self.channel_2, len(data), available - len(data))
					batch = {"V": [], "I": [], "QV": []}
					for (t, v), (_, cur) in zip(samples_v, samples_i):
						data.append([t, cur, v])
						batch["V"].append((t, v))
						batch["I"].append((t, cur * 1e6))
						for k, (t_start, t_end, _) in enumerate(forcs):
							if t_start <= t <= t_end:
								forc_samples[k].append((v, cur))
								break

						# The 0 V hold sets the current offset; charge integrates from there on.
						if baseline is None:
							baseline_samples.append(cur)
							if len(baseline_samples) == baseline_points:
								baseline = float(np.mean(baseline_samples))
								last_t = t
							continue
						# Negate current so positive switching charge plots in the expected direction, as in PUND.
						cur_adj = -(cur - baseline)
						charge += cur_adj * (t - last_t)
						last_t = t
						batch["QV"].append((v, charge * 1e9))
					runner.plot.append_batch(batch)

					finished = sum(1 for _, t_end, _ in forcs if t_end <= data[-1][0])
					self.report_progress(finished, len(forcs), "Reversal curves")

					# Redraw the whole map whenever a curve finishes; cells without data stay NaN.
					if finished > drawn_forcs:
						drawn_forcs = finished
						grid = np.full((self.forc_count + 1, self.forc_count), np.nan)
						for k, ((_, _, vr), samples) in enumerate(zip(forcs[:finished], forc_samples)):
							if not samples:
								continue
							v_measured, i_measured = np.array(samples).T
							# Each cell shows the measured current at the sample closest to that grid voltage.
							rows = np.flatnonzero(v_grid >= vr - 1e-9)
							nearest = np.abs(v_measured[None, :] - v_grid[rows, None]).argmin(axis=1)
							# Columns run left to right in increasing Vr, while curves run in decreasing Vr.
							grid[rows, self.forc_count - 1 - k] = i_measured[nearest] * 1e6
						runner.plot.replace_source("MAP", [0.0] * grid.size, grid.ravel().tolist())

				# Status was read before fetching, so a completed run has no samples left to read.
				if status == STATUS_COMPLETED:
					break
				time.sleep(0.05)

			self.save_measurement_outputs(
				data,
				"FORC",
				device,
				["Time_s", "Current_A", "Voltage_V"],
			)
			self.log(f"FORC complete: {len(forcs)} reversal curves, {len(data)} points")
		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
