"""
FTJ Fatigue Procedure - PUND fatigue with an SMU I-V sweep after every read.

Same fatigue and read schedule as PUNDFatigue. After each WGFMU read, both
RSUs switch to their SMU input and a butterfly staircase sweep reads the
junction: SMU 1 (on WGFMU channel 1) sweeps base → base+Vmax → base → base−Vmax
→ base, while SMU 2 (on WGFMU channel 2) holds 0 V and measures the current.
The RSUs then switch back to the WGFMU for the next fatigue block.
"""
import time
import numpy as np
from plotting import PlotDef, Curve
from procedures.base import SMU, Choice, parameter
from procedures.pund_fatigue import PUNDFatigueProcedure
from procedures._iv_model import sweep_segments
from instrumentio.codes import (
	B1500_CH_ALL, B1500_CH_NOCH, B1500_LAST_STOP, B1500_STOP_DISABLE,
	B1500_SWP_VF_DBLLIN, B1500_SWP_VF_SGLLIN,
	WGFMU_OPERATION_MODE_SMU,
)
from instrumentio.constants import B1500_CURRENT_RANGES
from instrumentio.descriptors import describe_status_bits

# Each RSU has one SMU cabled into it; this is wiring, not a setting.
# SMU numbers become B1500 slots through the channel map found at start-up.
RSU_SMU = {101: "SMU1", 102: "SMU2"}


class FTJFatigueProcedure(PUNDFatigueProcedure):
	NAME = "FTJFatigue"
	PARAMETERS = (
		*PUNDFatigueProcedure.PARAMETERS,
		parameter('smu_points', 'SMU Sweep Points (outward leg)', 21, int,
		          help="Butterfly sweep base → +Vmax → base → −Vmax → base, with the PUND Vmax."),
		parameter('smu_current_range', 'SMU Current Range (A)', 1e-9, Choice(B1500_CURRENT_RANGES, float)),
		parameter('smu_current_compliance', 'SMU Current Compliance (A)', 1e-3, float),
		parameter('smu_adc_type', 'SMU ADC Type', 1, Choice(((0, 'High-speed'), (1, 'High-resolution')), int)),
	)

	def _validate_settings(self):
		super()._validate_settings()
		if self.channel_1 not in RSU_SMU or self.channel_2 not in RSU_SMU or self.channel_1 == self.channel_2:
			raise ValueError(f"FTJFatigue needs WGFMU channels {sorted(RSU_SMU)}, which have SMUs on their RSUs.")
		if self.smu_current_compliance <= 0:
			raise ValueError("SMU current compliance must be > 0")
		sweep_segments(0.0, self.vmax, self.smu_points, 'Butterfly')

	def _configure_plot(self, device, read_cycles, read_duration):
		log_max = np.log10(max(read_cycles[-1], 1))
		waveform, qv, smu = [], [], []
		for read_idx, cycle_num in enumerate(read_cycles):
			intensity = 0.2 + 0.7 * (np.log10(max(cycle_num, 1)) / max(log_max, 1))
			color = self._phase_color('pund', intensity)
			show = read_idx in (0, len(read_cycles) - 1)
			label = f"cycle {cycle_num}"
			waveform.append(Curve(f"V_{read_idx}", color=color, yaxis=0, legend_label=f"V ({label})", show_in_legend=show))
			waveform.append(Curve(f"I_{read_idx}", color=color, yaxis=1, legend_label=f"I ({label})", show_in_legend=show))
			qv.append(Curve(f"QV_{read_idx}", color=color, legend_label=label, show_in_legend=show))
			smu.append(Curve(f"SMU_{read_idx}", mode='line_scatter', marker='o', marker_size=3, color=color,
			                 legend_label=label, show_in_legend=show))

		max_abs_v = abs(self.vmax)
		v_margin = max(max_abs_v * 0.1, 0.1)
		self.runner.configure_plot(f'FTJ Fatigue - {device.name}', [
			PlotDef("pund", row=0, col=0, colspan=2,
			        xlabel="Time (s)",
			        ylabels=("Voltage (V)", "Current (uA)"),
			        xlim=(0, read_duration),
			        ylims=((min(0.0, self.base_voltage - max_abs_v) - v_margin,
			                max(0.0, self.base_voltage + max_abs_v) + v_margin), None),
			        elements=waveform),
			PlotDef("qv", row=1, col=0, xlabel="Voltage (V)", ylabels=("Charge (nC)",), elements=qv),
			PlotDef("smu_iv", row=1, col=1, xlabel="SMU 1 Voltage (V)", ylabels=("|SMU 2 Current| (A)",),
			        yscales=("log",), elements=smu),
		], row_ratios=[2.0, 1.0])

	def _run_wgfmu_block(self, wgfmu, ts, block, fatigue_reps, fatigue_vectors, read_vectors,
	                     settle_duration, sample_points, sample_interval):
		"""Send fatigue_reps fatigue cycles, then one read. Returns the read's (t, V, I) samples."""
		# Each block is its own execute, so the patterns are rebuilt after clear().
		self._configure_wgfmu(wgfmu)
		initial_pg = self._idle_voltage()
		fat_pg, fat_iv = f"FTJ_FAT_PG_{ts}_{block}", f"FTJ_FAT_IV_{ts}_{block}"
		read_pg, read_iv = f"FTJ_READ_PG_{ts}_{block}", f"FTJ_READ_IV_{ts}_{block}"
		self._create_pattern_pair(wgfmu, fat_pg, fat_iv, initial_pg, fatigue_vectors)
		self._create_pattern_pair(wgfmu, read_pg, read_iv, initial_pg,
		                          [(settle_duration, initial_pg), *read_vectors],
		                          measure_points=sample_points, sample_interval=sample_interval,
		                          measure_start=settle_duration)
		if fatigue_reps > 0:
			wgfmu.add_sequence(self.channel_1, fat_pg, float(fatigue_reps))
			wgfmu.add_sequence(self.channel_2, fat_iv, float(fatigue_reps))
		wgfmu.add_sequence(self.channel_1, read_pg, 1.0)
		wgfmu.add_sequence(self.channel_2, read_iv, 1.0)
		wgfmu.execute()

		while True:
			self.check_stop(self.b1500)
			status, _, _ = wgfmu.get_status()
			if status == self.STATUS_COMPLETED:
				break
			time.sleep(0.05)
		measured_1, _ = wgfmu.get_measure_value_size(self.channel_1)
		measured_2, _ = wgfmu.get_measure_value_size(self.channel_2)
		count = min(measured_1, measured_2)
		samples_v = wgfmu.read_chunk(self.channel_1, 0, count)
		samples_i = wgfmu.read_chunk(self.channel_2, 0, count)
		return [(t, v, i) for (t, v), (_, i) in zip(samples_v, samples_i)]

	def _plot_read(self, read_idx, samples):
		if not samples:
			return
		t0 = samples[0][0]
		batch = {f"V_{read_idx}": [], f"I_{read_idx}": [], f"QV_{read_idx}": []}
		# Same Q-V as PUNDFatigue: offset from the first 50 samples, negated current.
		baseline = float(np.mean([i for _, _, i in samples[:50]]))
		charge, last_t = 0.0, t0
		for t, v, i in samples:
			batch[f"V_{read_idx}"].append((t - t0, v))
			batch[f"I_{read_idx}"].append((t - t0, i * 1e6))
			charge += -(i - baseline) * (t - last_t)
			last_t = t
			batch[f"QV_{read_idx}"].append((v, charge * 1e9))
		self.runner.plot.append_batch(batch)

	def _smu_sweep(self, read_idx):
		"""Butterfly sweep on SMU 1 with SMU 2 at 0 V. Returns (segment, V1, I1, I2, status) rows."""
		b1500 = self.b1500
		wgfmu = b1500.wgfmu
		force, ground = SMU.coerce(RSU_SMU[self.channel_1]), SMU.coerce(RSU_SMU[self.channel_2])
		for channel in (self.channel_1, self.channel_2):
			wgfmu.set_operation_mode(channel, WGFMU_OPERATION_MODE_SMU)
			wgfmu.update_channel(channel)
		b1500.set_switch(force, True)
		b1500.set_switch(ground, True)
		b1500.force_voltage(ground, 0.0, compliance=self.smu_current_compliance)

		rows = []
		for segment, (start, stop, double, points) in enumerate(sweep_segments(0.0, self.vmax, self.smu_points, 'Butterfly')):
			self.check_stop(b1500)
			b1500.set_iv_sweep(force, B1500_SWP_VF_DBLLIN if double else B1500_SWP_VF_SGLLIN, 0.0,
			                   self.base_voltage + start, self.base_voltage + stop, points,
			                   compliance=self.smu_current_compliance)
			b1500.start_measure([force, ground], [1, 1], [self.smu_current_range] * 2, source_output=1, timestamp=0)
			outputs, currents, seen = [], {force: [], ground: []}, set()
			while True:
				_, eod, kind, value, status, channel = b1500.read_data()
				if status and (channel, kind, status) not in seen:
					seen.add((channel, kind, status))
					self.runner.report_status(dict(channel=channel, data_type=kind, status=status,
					                               desc=describe_status_bits(status)))
				if kind == 1 and channel in currents:
					currents[channel].append((value, status))
				elif kind == 4 and channel in (force, B1500_CH_NOCH, B1500_CH_ALL):
					outputs.append((value, status))
				if eod:
					break
			b1500.finish_measure()
			for (v, s0), (i1, s1), (i2, s2) in zip(outputs, currents[force], currents[ground]):
				rows.append((segment, v, i1, i2, s0 | s1 | s2))
		b1500.set_switch(B1500_CH_ALL, False)

		# A log axis cannot show negative currents, so the plot shows |I|; the CSV keeps the sign.
		self.runner.plot.append_batch({f"SMU_{read_idx}": [(v, abs(i2)) for _, v, _, i2, _ in rows]})
		return rows

	def measure(self, device):
		b1500 = self.b1500
		wgfmu = b1500.wgfmu
		self.check_stop(b1500)

		read_cycles = self._read_cycles()
		fatigue_vectors = self._build_fatigue_vectors()
		read_vectors = self._build_read_vectors()
		read_duration = sum(dt for dt, _ in read_vectors)
		settle_duration = 1.0 / self.fatigue_freq
		sample_interval = self._sample_interval()
		sample_points = max(1, int(round(read_duration / sample_interval)))
		self._configure_plot(device, read_cycles, read_duration)
		self._report_fatigue_progress(0)
		self.log(f"Starting FTJ Fatigue on {device.name}: {self.fatigue_count_int:.2e} cycles, "
		         f"{len(read_cycles)} PUND reads, each followed by an SMU sweep")

		ts = self.get_run_timestamp()
		pund_rows, smu_rows = [], []
		try:
			b1500.enable_error_detect(True)
			b1500.stop_mode(B1500_STOP_DISABLE, B1500_LAST_STOP)
			smu_channels = [SMU.coerce(RSU_SMU[self.channel_1]), SMU.coerce(RSU_SMU[self.channel_2])]
			self.prepare_asu_channels(b1500, smu_channels, self.smu_current_range)
			# High-resolution ADC in auto mode: sensitive at nA, still well under a second per sweep.
			b1500.configure_smu_acquisition(smu_channels, adc=self.smu_adc_type, mode=0, coefficient=0,
			                               parallel=False, autozero=False,
			                               source_wait_factor=1.0, source_wait_offset=0.0,
			                               measurement_wait_factor=1.0, measurement_wait_offset=0.0)

			prev_cycle = 0
			for read_idx, cycle_num in enumerate(read_cycles):
				self.check_stop(b1500)
				samples = self._run_wgfmu_block(wgfmu, ts, read_idx, cycle_num - prev_cycle,
				                                fatigue_vectors, read_vectors, settle_duration,
				                                sample_points, sample_interval)
				prev_cycle = cycle_num
				pund_rows += [[cycle_num, t, v, i] for t, v, i in samples]
				self._plot_read(read_idx, samples)
				smu_rows += [[cycle_num, *row] for row in self._smu_sweep(read_idx)]
				self._report_fatigue_progress(cycle_num)
			# The last read cycle is always the final fatigue cycle, so nothing is left to send.
		finally:
			base = self.format_filename("FTJ_Fatigue", device.name)
			self.save_data(smu_rows, f"{base}_smu.csv",
			               ["Cycle", "Segment", "SMU1_Voltage_Programmed_V", "SMU1_Current_A", "SMU2_Current_A", "Status"],
			               add_timestamp=False)
			self.save_measurement_outputs(pund_rows, "FTJ_Fatigue_PUND", device,
			                              ["Cycle", "Time_s", "Voltage_V", "Current_A"],
			                              save_plot=bool(pund_rows))
			try:
				wgfmu.clear()
				wgfmu.disconnect(self.channel_1)
				wgfmu.disconnect(self.channel_2)
			except Exception:
				pass
		self.log(f"FTJ Fatigue complete: {len(read_cycles)} reads, {len(pund_rows)} PUND samples, "
		         f"{len(smu_rows)} SMU points")
