"""
FORC Fatigue Procedure - PUND reads during fatigue, with a full FORC at chosen cycles.

Same fatigue cycles and log-spaced PUND reads as PUNDFatigueV2, all in one WGFMU
run. A FORC (the waveform of the FORC procedure: Vstart, Vend, number of reversal
curves, frequency) runs on the pristine device at cycle 0 and after each fatigue
cycle count listed in "FORC at Cycles". Cycle 0 also gets a PUND read. Where a
cycle has both, the FORC comes first, so the cycle-0 FORC sees a pristine device.

Every read is saved as its own CSV as soon as it is measured:
``<base>_c<cycle>_PUND.csv`` and ``<base>_c<cycle>_FORC.csv``.

The live plot shows the Q-V curve of every PUND read and every FORC, coloured by
cycle, and the I(Vr, V) map of a few FORCs spread over the run, including the
first and last.
"""
import time
import numpy as np
from plotting import PlotDef, Curve, Heatmap
from procedures.base import parameter
from procedures.forc import FORCProcedure, forc_map_axes, forc_map_grid
from procedures.pund_fatigue_v2 import PUNDFatigueV2Procedure

# Each map is its own small plot, so only this many FORCs get one.
MAX_MAPS = 6
# PUND Q-V: the current offset is the mean of the first samples, as in PUNDFatigueV2.
PUND_BASELINE_POINTS = 50
HEADERS = ["Cycle", "Time_s", "Voltage_V", "Current_A"]

_V2_PARAMETERS = PUNDFatigueV2Procedure.PARAMETERS
_FORC_PARAMETERS = {p.key: p for p in FORCProcedure.PARAMETERS}


class FORCFatigueProcedure(PUNDFatigueV2Procedure):
	NAME = "FORCFatigue"
	PARAMETERS = (
		*_V2_PARAMETERS[:-2],
		_FORC_PARAMETERS['vstart'],
		_FORC_PARAMETERS['vend'],
		_FORC_PARAMETERS['forc_count'],
		# Renamed: this form already has a fatigue and a read frequency.
		parameter('frequency', 'FORC Frequency (Hz)', 1e3, float, help=_FORC_PARAMETERS['frequency'].help),
		parameter('forc_cycles', 'FORC at Cycles', '1e2, 1e4, 1e6', str,
		          help="Comma-separated fatigue cycle counts that get a FORC, besides the pristine one "
		               "at cycle 0. Each must be between 1 and the fatigue cycle count."),
		*_V2_PARAMETERS[-2:],  # measurement ranges
	)
	# TODO: the inherited "Preview Sequence" shows the PUND reads only, not cycle 0 or the FORCs.

	def _validate_settings(self):
		super()._validate_settings()
		FORCProcedure._build_forc_vectors(self)
		try:
			self.forc_cycle_list = sorted({int(float(c)) for c in str(self.forc_cycles).split(',') if c.strip()})
		except ValueError:
			raise ValueError(f"FORC at Cycles must be comma-separated numbers, got {self.forc_cycles!r}") from None
		outside = [c for c in self.forc_cycle_list if not 1 <= c <= self.fatigue_count_int]
		if outside:
			raise ValueError(f"FORC cycles {outside} are outside 1 to {self.fatigue_count_int} (the fatigue cycle count)")

	def _configure_plot(self, device, reads, map_reads, map_axes):
		log_max = np.log10(max(reads[-1][0], 1))
		curves = {'PUND': [], 'FORC': []}
		indices = {kind: [i for i, (_, k) in enumerate(reads) if k == kind] for kind in curves}
		for read_idx, (cycle, kind) in enumerate(reads):
			intensity = 0.2 + 0.7 * (np.log10(max(cycle, 1)) / max(log_max, 1))
			# Orange for PUND reads, blue for FORCs, darker for later cycles.
			color = self._phase_color('pund' if kind == 'PUND' else 'pn', intensity)
			curves[kind].append(Curve(f"QV_{read_idx}", color=color, legend_label=f"cycle {cycle}",
			                          show_in_legend=read_idx in (indices[kind][0], indices[kind][-1])))

		_, _, bounds_min, bounds_max = map_axes
		columns = max(2, len(map_reads))
		plots = [
			PlotDef("pund_qv", row=0, col=0, colspan=columns // 2, title="PUND reads",
			        xlabel="Voltage (V)", ylabels=("Charge (nC)",), elements=curves['PUND']),
			PlotDef("forc_qv", row=0, col=columns // 2, colspan=columns - columns // 2, title="FORC",
			        xlabel="Voltage (V)", ylabels=("Charge (nC)",), elements=curves['FORC']),
		]
		for col, read_idx in enumerate(map_reads):
			plots.append(PlotDef(f"map_{read_idx}", row=1, col=col,
			                     title=f"cycle {self._format_cycle_count(reads[read_idx][0])}",
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

		# Every read as (cycle, 'PUND' or 'FORC'), in the order the WGFMU runs them.
		forc_cycles = {0, *self.forc_cycle_list}
		pund_cycles = self._compute_read_cycles(self.fatigue_count_int, self.reads_per_decade)
		reads = []
		for cycle in sorted({0, *pund_cycles, *forc_cycles}):
			if cycle in forc_cycles:
				reads.append((cycle, 'FORC'))
			reads.append((cycle, 'PUND'))

		initial_pg = self._idle_voltage()
		settle_duration = 1.0 / self.fatigue_freq
		pund_vectors = self._build_read_vectors()
		pund_interval = self._sample_interval()
		forc_vectors, hold, forcs = FORCProcedure._build_forc_vectors(self)
		# 1000 samples per full FORC triangle, rounded to the 10 ns WGFMU resolution, as in FORC.
		forc_interval = max(round(1e-3 / self.frequency / self.RESOLUTION), 1) * self.RESOLUTION
		# Per read type: sample interval, samples per read, samples that set the current offset.
		sampling = {
			'PUND': (pund_interval, max(1, int(round(sum(dt for dt, _ in pund_vectors) / pund_interval))),
			         PUND_BASELINE_POINTS),
			'FORC': (forc_interval, int(sum(dt for dt, _ in forc_vectors) / forc_interval),
			         max(1, int(hold / forc_interval))),
		}
		read_ends = np.cumsum([sampling[kind][1] for _, kind in reads])
		expected_total = int(read_ends[-1])

		map_axes = forc_map_axes(self.vstart, self.vend, self.forc_count)
		v_grid, vr_grid, _, _ = map_axes
		forc_reads = [i for i, (_, kind) in enumerate(reads) if kind == 'FORC']
		map_reads = [forc_reads[k] for k in
		             sorted({int(round(k)) for k in np.linspace(0, len(forc_reads) - 1, min(MAX_MAPS, len(forc_reads)))})]
		self._configure_plot(device, reads, map_reads, map_axes)
		self._report_fatigue_progress(0)
		self.log(f"Starting FORC Fatigue on {device.name}: {self.fatigue_count_int:.2e} "
		         f"{self.fatigue_pulse_type} fatigue cycles, {len(reads) - len(forc_reads)} PUND reads, "
		         f"{len(forc_reads)} FORCs of {self.forc_count} curves at cycles {sorted(forc_cycles)}")

		ts = self.get_run_timestamp()
		base = self.format_filename("FORC_Fatigue", device.name)
		try:
			self._configure_wgfmu(wgfmu)
			patterns = {
				'FAT': (f"FORCFAT_FAT_PG_{ts}", f"FORCFAT_FAT_IV_{ts}"),
				'PUND': (f"FORCFAT_PUND_PG_{ts}", f"FORCFAT_PUND_IV_{ts}"),
				'FORC': (f"FORCFAT_FORC_PG_{ts}", f"FORCFAT_FORC_IV_{ts}"),
			}
			self._create_pattern_pair(wgfmu, *patterns['FAT'], initial_pg, self._build_fatigue_vectors())
			self._create_pattern_pair(wgfmu, *patterns['PUND'], initial_pg,
			                          [(settle_duration, initial_pg), *pund_vectors],
			                          measure_points=sampling['PUND'][1], sample_interval=pund_interval,
			                          measure_start=settle_duration)
			# The FORC waveform starts and ends at 0 V; settle from and return to the fatigue idle voltage.
			self._create_pattern_pair(wgfmu, *patterns['FORC'], initial_pg,
			                          [(settle_duration, 0.0), *forc_vectors, (0.1 * settle_duration, initial_pg)],
			                          measure_points=sampling['FORC'][1], sample_interval=forc_interval,
			                          measure_start=settle_duration)
			prev_cycle = 0
			for cycle, kind in reads:
				if cycle > prev_cycle:
					wgfmu.add_sequence(self.channel_1, patterns['FAT'][0], float(cycle - prev_cycle))
					wgfmu.add_sequence(self.channel_2, patterns['FAT'][1], float(cycle - prev_cycle))
				wgfmu.add_sequence(self.channel_1, patterns[kind][0], 1.0)
				wgfmu.add_sequence(self.channel_2, patterns[kind][1], 1.0)
				prev_cycle = cycle
			# The last read cycle is always the final fatigue cycle, so nothing is left to send.

			self.check_stop(b1500)
			wgfmu.execute()

			times, voltages, currents = [], [], []  # every sample of the run, in order
			done = 0  # reads already plotted and saved
			while True:
				self.check_stop(b1500)
				status, _, _ = wgfmu.get_status()
				measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
				measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
				available = min(measured_1, measured_2, expected_total)

				if available > len(times):
					start = len(times)
					samples_v = wgfmu.read_chunk(self.channel_1, start, available - start)
					samples_i = wgfmu.read_chunk(self.channel_2, start, available - start)
					for (t, v), (_, cur) in zip(samples_v, samples_i):
						times.append(t)
						voltages.append(v)
						currents.append(cur)

					# Plot and save every read that is now complete.
					while done < len(reads) and read_ends[done] <= len(times):
						cycle, kind = reads[done]
						interval, points, baseline_points = sampling[kind]
						span = slice(int(read_ends[done]) - points, int(read_ends[done]))
						v, cur = np.array(voltages[span]), np.array(currents[span])
						self.save_data([[cycle, t, vi, ci] for t, vi, ci in zip(times[span], voltages[span], currents[span])],
						               f"{base}_c{cycle}_{kind}.csv", HEADERS, add_timestamp=False)
						# Q-V as in FORC and PUND: offset from the first samples, negated current.
						charge = np.cumsum(-(cur[baseline_points:] - cur[:baseline_points].mean())) * interval
						self.runner.plot.append_batch({f"QV_{done}": list(zip(v[baseline_points:], charge * 1e9))})
						if done in map_reads:
							t_read = np.arange(len(v)) * interval
							samples = np.column_stack((v, cur))
							forc_samples = [samples[(t_read >= t0) & (t_read <= t1)].tolist() for t0, t1, _ in forcs]
							grid = forc_map_grid(self.vstart, forcs, forc_samples, v_grid, vr_grid)
							self.runner.plot.replace_source(f"MAP_{done}", [0.0] * grid.size, grid.ravel().tolist())
						self._report_fatigue_progress(cycle)
						done += 1

				# Status was read before fetching, so a completed run has no samples left to read.
				if status == self.STATUS_COMPLETED:
					break
				time.sleep(0.05)

			if done:
				self.save_plot_png(f"{base}_plot.png")
			if done < len(reads):
				self.log(f"Warning: only {done} of {len(reads)} reads were measured ({len(times)}/{expected_total} samples).")
			self.log(f"FORC Fatigue complete: {done} reads saved as separate files, {len(times)} samples")
		finally:
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
