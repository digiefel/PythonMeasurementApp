"""
FORC Fatigue Procedure - fatigue cycles with a full FORC measurement as the read.

Same fatigue settings and log-spaced read schedule as PUNDFatigueV2, all in one
WGFMU run. Each read is the FORC waveform of the FORC procedure (Vstart, Vend,
number of reversal curves, frequency). The fatigue cycles use their own
amplitude around the base voltage.

The live plot shows one continuous Q-V curve per read, coloured by cycle, and
the I(Vr, V) map of a few reads spread over the run, including the first and last.
"""
import time
import numpy as np
from plotting import PlotDef, Curve, Heatmap
from procedures.base import parameter
from procedures.forc import FORCProcedure, forc_map_axes, forc_map_grid
from procedures.pund_fatigue_v2 import PUNDFatigueV2Procedure

# Each map is its own small plot, so only this many reads get one.
MAX_MAPS = 6

# Fatigue settings from PUNDFatigueV2; its read-pulse settings are replaced by the FORC ones.
_FATIGUE_PARAMETERS = tuple(p for p in PUNDFatigueV2Procedure.PARAMETERS
                            if p.key not in ('vmax', 'read_pulse_freq', 'read_pulse_type'))


class FORCFatigueProcedure(PUNDFatigueV2Procedure):
	NAME = "FORCFatigue"
	PARAMETERS = (
		*_FATIGUE_PARAMETERS[:3],
		parameter('vmax', 'Fatigue Amplitude (V)', 1.0, float,
		          help="Fatigue cycles swing to base ± this voltage."),
		*_FATIGUE_PARAMETERS[3:-2],
		*(p for p in FORCProcedure.PARAMETERS if p.key in ('vstart', 'vend', 'forc_count', 'frequency')),
		*_FATIGUE_PARAMETERS[-2:],  # measurement ranges
	)

	def _validate_settings(self):
		if self.vmax == 0.0:
			raise ValueError("Fatigue amplitude must be non-zero.")
		if self.fatigue_freq <= 0:
			raise ValueError("fatigue_freq must be > 0")
		if self.fatigue_delay < 0:
			raise ValueError("fatigue_delay must be >= 0")
		if self.fatigue_count_int < 1:
			raise ValueError("fatigue_count must be >= 1")
		if self.reads_per_decade <= 0:
			raise ValueError("reads_per_decade must be > 0")
		if self.fatigue_pulse_type not in ('square', 'triangle', 'pund'):
			raise ValueError(f"Invalid fatigue_pulse_type: {self.fatigue_pulse_type!r}")
		FORCProcedure._build_forc_vectors(self)

	def _configure_plot(self, device, read_cycles, map_reads, map_axes):
		log_max = np.log10(max(read_cycles[-1], 1))
		qv = []
		for read_idx, cycle_num in enumerate(read_cycles):
			intensity = 0.2 + 0.7 * (np.log10(max(cycle_num, 1)) / max(log_max, 1))
			qv.append(Curve(f"QV_{read_idx}", color=self._phase_color('pund', intensity),
			                legend_label=f"cycle {cycle_num}",
			                show_in_legend=read_idx in (0, len(read_cycles) - 1)))
		_, _, bounds_min, bounds_max = map_axes
		plots = [PlotDef("qv", row=0, col=0, colspan=len(map_reads),
		                 xlabel="Voltage (V)", ylabels=("Charge (nC)",), elements=qv)]
		for col, read_idx in enumerate(map_reads):
			plots.append(PlotDef(f"map_{read_idx}", row=1, col=col,
			                     title=f"cycle {self._format_cycle_count(read_cycles[read_idx])}",
			                     xlabel="Vr (V)", ylabels=("V (V)",),
			                     xlim=(bounds_min[0], bounds_max[0]), ylims=((bounds_min[1], bounds_max[1]),),
			                     elements=[Heatmap(f"MAP_{read_idx}", rows=self.forc_count + 1, cols=self.forc_count,
			                                       bounds_min=bounds_min, bounds_max=bounds_max,
			                                       show_in_legend=False)]))
		self.runner.configure_plot(f'FORC Fatigue - {device.name}', plots, row_ratios=[1.5, 1.0])

	def measure(self, device):
		b1500 = self.b1500
		wgfmu = b1500.wgfmu
		self.check_stop(b1500)

		read_cycles = self._compute_read_cycles(self.fatigue_count_int, self.reads_per_decade)
		fatigue_vectors = self._build_fatigue_vectors()
		forc_vectors, hold, forcs = FORCProcedure._build_forc_vectors(self)
		forc_duration = sum(dt for dt, _ in forc_vectors)
		settle_duration = 1.0 / self.fatigue_freq

		# 1000 samples per full FORC triangle, rounded to the 10 ns WGFMU resolution, as in FORC.
		sample_interval = max(round(1e-3 / self.frequency / self.RESOLUTION), 1) * self.RESOLUTION
		sample_points = int(forc_duration / sample_interval)
		baseline_points = max(1, int(hold / sample_interval))
		expected_total = sample_points * len(read_cycles)

		map_axes = forc_map_axes(self.vstart, self.vend, self.forc_count)
		v_grid, vr_grid, _, _ = map_axes
		map_reads = sorted({int(round(k)) for k in np.linspace(0, len(read_cycles) - 1, min(MAX_MAPS, len(read_cycles)))})
		self._configure_plot(device, read_cycles, map_reads, map_axes)
		self._report_fatigue_progress(0)
		self.log(f"Starting FORC Fatigue on {device.name}: {self.fatigue_count_int:.2e} "
		         f"{self.fatigue_pulse_type} fatigue cycles, {len(read_cycles)} FORC reads of "
		         f"{self.forc_count} curves, {sample_points} samples each")

		ts = self.get_run_timestamp()
		initial_pg = self._idle_voltage()
		try:
			self._configure_wgfmu(wgfmu)
			fat_pg, fat_iv = f"FORCFAT_FAT_PG_{ts}", f"FORCFAT_FAT_IV_{ts}"
			read_pg, read_iv = f"FORCFAT_READ_PG_{ts}", f"FORCFAT_READ_IV_{ts}"
			self._create_pattern_pair(wgfmu, fat_pg, fat_iv, initial_pg, fatigue_vectors)
			# The FORC waveform starts and ends at 0 V; settle from and return to the fatigue idle voltage.
			self._create_pattern_pair(wgfmu, read_pg, read_iv, initial_pg,
			                          [(settle_duration, 0.0), *forc_vectors, (0.1 * settle_duration, initial_pg)],
			                          measure_points=sample_points, sample_interval=sample_interval,
			                          measure_start=settle_duration)
			prev_cycle = 0
			for cycle_num in read_cycles:
				if cycle_num > prev_cycle:
					wgfmu.add_sequence(self.channel_1, fat_pg, float(cycle_num - prev_cycle))
					wgfmu.add_sequence(self.channel_2, fat_iv, float(cycle_num - prev_cycle))
				wgfmu.add_sequence(self.channel_1, read_pg, 1.0)
				wgfmu.add_sequence(self.channel_2, read_iv, 1.0)
				prev_cycle = cycle_num
			# The last read cycle is always the final fatigue cycle, so nothing is left to send.

			self.check_stop(b1500)
			wgfmu.execute()

			rows = []
			read_samples = [[] for _ in read_cycles]  # (V, I) per read
			while True:
				self.check_stop(b1500)
				status, _, _ = wgfmu.get_status()
				measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2, expected_total)

				if available > len(rows):
					start = len(rows)
					samples_v = wgfmu.read_chunk(self.channel_1, start, available - start)
					samples_i = wgfmu.read_chunk(self.channel_2, start, available - start)
					for index, ((t, v), (_, cur)) in enumerate(zip(samples_v, samples_i), start):
						read_idx = index // sample_points
						rows.append([read_cycles[read_idx], t, v, cur])
						read_samples[read_idx].append((v, cur))

					# Plot every read that this chunk completed.
					first_done, done = start // sample_points, available // sample_points
					for read_idx in range(first_done, done):
						samples = np.array(read_samples[read_idx])
						v, cur = samples.T
						# Same Q-V as FORC: offset from the 0 V hold, negated current.
						baseline = cur[:baseline_points].mean()
						charge = np.cumsum(-(cur[baseline_points:] - baseline)) * sample_interval
						self.runner.plot.append_batch({f"QV_{read_idx}": list(zip(v[baseline_points:], charge * 1e9))})
						if read_idx in map_reads:
							t_read = np.arange(len(v)) * sample_interval
							forc_samples = [samples[(t_read >= t0) & (t_read <= t1)].tolist() for t0, t1, _ in forcs]
							grid = forc_map_grid(self.vstart, forcs, forc_samples, v_grid, vr_grid)
							self.runner.plot.replace_source(f"MAP_{read_idx}", [0.0] * grid.size, grid.ravel().tolist())
						self._report_fatigue_progress(read_cycles[read_idx])

				# Status was read before fetching, so a completed run has no samples left to read.
				if status == self.STATUS_COMPLETED:
					break
				time.sleep(0.05)

			self.save_measurement_outputs(rows, "FORC_Fatigue", device, ["Cycle", "Time_s", "Voltage_V", "Current_A"],
			                              save_plot=bool(rows))
			self.log(f"FORC Fatigue complete: {len(read_cycles)} reads, {len(rows)} samples")
		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
