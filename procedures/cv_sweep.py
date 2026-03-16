from procedures.base import MeasurementProcedure
from bindings import B1500Session


class CVSweepProcedure(MeasurementProcedure):
    """CMU-based capacitance-voltage sweep for B1500."""

    def __init__(self, settings, output_root, output_relative, runner, fallback_root=None):
        super().__init__(settings, output_root, output_relative, runner, fallback_root)

        self.gpib_address = settings.get("gpib_address", "GPIB0::17::INSTR")
        self.cmu_channel = int(settings.get("cmu_channel", -1))
        self.double_sweep = bool(settings["double_sweep"])
        self.cmu_mode = int(settings.get("cmu_mode", B1500Session.CMUM_CP_D))

        self.start_bias = float(settings.get("start_bias", -2.0))
        self.stop_bias = float(settings.get("stop_bias", 2.0))
        self.points = max(1, int(float(settings.get("points", 101))))
        self.measurement_range = float(settings.get("measurement_range", B1500Session.AUTO_RANGE))

        self.ac_level_mv = float(settings.get("ac_level_mv", 30.0))
        self.ac_level = self.ac_level_mv / 1000.0
        self.frequency_hz = float(settings.get("frequency_hz", 1e5))
        self.integration_mode = int(settings.get("integration_mode", 0))
        self.integration_value = int(settings.get("integration_value", 1))

        self.hold_time = float(settings.get("hold_time", 0.0))
        self.delay_time = float(settings.get("delay_time", 0.0))
        self.second_delay = float(settings.get("second_delay", 0.0))

        self._validate_settings()

    def _validate_settings(self):
        if self.points < 1:
            raise ValueError("C-V points must be >= 1")
        if self.start_bias == self.stop_bias and self.points > 1:
            raise ValueError("Start Bias and Stop Bias are equal; use points=1 for spot-like measurement.")
        if not (0.0 <= self.ac_level_mv <= 250.0):
            raise ValueError("AC Level must be between 0 and 250 mV for CMU.")
        if not (1e3 <= self.frequency_hz <= 5e6):
            raise ValueError("Frequency must be between 1 kHz and 5 MHz for CMU.")
        if self.integration_mode not in (0, 1, 2):
            raise ValueError("Integration Mode must be Auto, Manual, or PLC.")
        if self.integration_value < 1:
            raise ValueError("Integration Value must be >= 1.")

    @staticmethod
    def _cmu_mode_name(mode: int) -> str:
        names = {
            B1500Session.CMUM_R_X: "R-X",
            B1500Session.CMUM_G_B: "G-B",
            B1500Session.CMUM_Z_TRAD: "Z-Theta (radian)",
            B1500Session.CMUM_Z_TDEG: "Z-Theta (degree)",
            B1500Session.CMUM_Y_TRAD: "Y-Theta (radian)",
            B1500Session.CMUM_Y_TDEG: "Y-Theta (degree)",
            B1500Session.CMUM_CP_G: "Cp-G",
            B1500Session.CMUM_CP_D: "Cp-D",
            B1500Session.CMUM_CP_Q: "Cp-Q",
            B1500Session.CMUM_CP_RP: "Cp-Rp",
            B1500Session.CMUM_CS_RS: "Cs-Rs",
            B1500Session.CMUM_CS_D: "Cs-D",
            B1500Session.CMUM_CS_Q: "Cs-Q",
            B1500Session.CMUM_LP_G: "Lp-G",
            B1500Session.CMUM_LP_D: "Lp-D",
            B1500Session.CMUM_LP_Q: "Lp-Q",
            B1500Session.CMUM_LP_RP: "Lp-Rp",
            B1500Session.CMUM_LS_RS: "Ls-Rs",
            B1500Session.CMUM_LS_D: "Ls-D",
            B1500Session.CMUM_LS_Q: "Ls-Q",
        }
        return names.get(mode, f"Mode {mode}")

    @staticmethod
    def _cmu_mode_components(mode: int):
        parts = {
            B1500Session.CMUM_R_X: ("R", "X"),
            B1500Session.CMUM_G_B: ("G", "B"),
            B1500Session.CMUM_Z_TRAD: ("Z", "Theta_rad"),
            B1500Session.CMUM_Z_TDEG: ("Z", "Theta_deg"),
            B1500Session.CMUM_Y_TRAD: ("Y", "Theta_rad"),
            B1500Session.CMUM_Y_TDEG: ("Y", "Theta_deg"),
            B1500Session.CMUM_CP_G: ("Cp", "G"),
            B1500Session.CMUM_CP_D: ("Cp", "D"),
            B1500Session.CMUM_CP_Q: ("Cp", "Q"),
            B1500Session.CMUM_CP_RP: ("Cp", "Rp"),
            B1500Session.CMUM_CS_RS: ("Cs", "Rs"),
            B1500Session.CMUM_CS_D: ("Cs", "D"),
            B1500Session.CMUM_CS_Q: ("Cs", "Q"),
            B1500Session.CMUM_LP_G: ("Lp", "G"),
            B1500Session.CMUM_LP_D: ("Lp", "D"),
            B1500Session.CMUM_LP_Q: ("Lp", "Q"),
            B1500Session.CMUM_LP_RP: ("Lp", "Rp"),
            B1500Session.CMUM_LS_RS: ("Ls", "Rs"),
            B1500Session.CMUM_LS_D: ("Ls", "D"),
            B1500Session.CMUM_LS_Q: ("Ls", "Q"),
        }
        return parts.get(mode, ("Primary", "Monitor"))

    @staticmethod
    def _cmu_component_unit(name: str) -> str:
        units = {
            "R": "Ohm",
            "X": "Ohm",
            "Z": "Ohm",
            "Y": "S",
            "G": "S",
            "B": "S",
            "Cp": "F",
            "Cs": "F",
            "Lp": "H",
            "Ls": "H",
            "Rp": "Ohm",
            "Rs": "Ohm",
            "D": "",
            "Q": "",
            "Theta_rad": "rad",
            "Theta_deg": "deg",
        }
        return units.get(name, "")

    def _series_label_with_unit(self, base: str) -> str:
        unit = self._cmu_component_unit(base)
        return f"{base} ({unit})" if unit else base

    def run(self, b1500: B1500Session, device):
        primary_name, monitor_name = self._cmu_mode_components(self.cmu_mode)
        primary_label = self._series_label_with_unit(primary_name)
        monitor_label = self._series_label_with_unit(monitor_name)

        self.log(f"Starting C-V sweep on {device.name}")
        self.log(
            f"CMU setup: channel={self.cmu_channel}, output={self._cmu_mode_name(self.cmu_mode)}, "
            f"double_sweep={'ON' if self.double_sweep else 'OFF'}, "
            f"f={self.frequency_hz:.1f} Hz, Vac={self.ac_level_mv:.1f} mV"
        )

        self.check_stop(b1500)
        b1500.reset()
        b1500.set_timeout(10000)
        b1500.enable_error_detect(True)

        # Keep behavior aligned with other sweep procedures.
        b1500.stop_mode(B1500Session.STOP_DISABLE, B1500Session.LAST_STOP)

        results = self.perform_cv_sweep(b1500, device)

        base = self.format_filename("CVSweep", device.name)
        filename = f"{base}.csv"
        self.save_data(
            results,
            filename,
            [
                "Bias_V",
                primary_label,
                monitor_label,
                "Time_sec",
                f"Status_{primary_name}",
                f"Status_{monitor_name}",
                "Status_Combined",
            ],
            add_timestamp=False,
        )
        plot_filename = f"{base}_plot.png"
        self.runner.finalize_plot(plot_filename, self.output_root, self.output_relative, self.fallback_root)
        self.log(f"C-V sweep completed for {device.name}")

    def perform_cv_sweep(self, b1500: B1500Session, device):
        self.check_stop(b1500)

        primary_name, monitor_name = self._cmu_mode_components(self.cmu_mode)
        primary_label = self._series_label_with_unit(primary_name)
        monitor_label = self._series_label_with_unit(monitor_name)

        expected_points = self._expected_points()
        nonzero_statuses = set()
        results = []

        try:
            b1500.set_switch(B1500Session.CH_ALL, False)
            b1500.set_switch(self.cmu_channel, True)

            b1500.set_cmu_integ(self.integration_mode, self.integration_value)
            b1500.force_cmu_ac_level(self.cmu_channel, self.ac_level)
            b1500.set_cmu_freq(self.cmu_channel, self.frequency_hz)

            b1500.reset_timestamp()
            b1500.set_cv(
                self.cmu_channel,
                B1500Session.SWP_VF_DBLLIN if self.double_sweep else B1500Session.SWP_VF_SGLLIN,
                self.start_bias,
                self.stop_bias,
                self.points,
                hold=self.hold_time,
                delay=self.delay_time,
                second_delay=self.second_delay,
            )

            self.check_stop(b1500)
            source, value_raw, status_raw, _monitor_raw, status_mon_raw, times, count = b1500.sweep_cv(
                self.cmu_channel,
                self.cmu_mode,
                self.measurement_range,
                expected_points=expected_points,
            )

            # DLL interleaves two components per bias point:
            #   value_raw[2i]   = primary component (e.g. Cp)
            #   value_raw[2i+1] = secondary component (e.g. Rp)
            comp1 = value_raw[0::2]       # primary component, count entries
            comp2 = value_raw[1::2]       # secondary component, count entries
            stat1 = status_raw[0::2]
            stat2 = status_mon_raw[0::2]

            # C-V sweep returns all data at once, so render in a single batched plot update.
            self.runner.start_live_plot(
                title=f"C-V Sweep - {device.name}",
                xlabel="Bias (V)",
                ylabel=primary_label,
                series_label=None,
                series_labels=[primary_label, monitor_label],
                styles={primary_label: {"color": "C0"}, monitor_label: {"color": "C1"}},
                secondary_series=[monitor_label],
                secondary_ylabel=monitor_label,
            )
            if count > 0:
                self.runner.add_live_series(source, comp1, primary_label)
                self.runner.add_live_series(source, comp2, monitor_label)

            for idx in range(count):
                self.check_stop(b1500)
                x = source[idx]
                y1 = comp1[idx]
                y2 = comp2[idx]
                s1 = stat1[idx]
                s2 = stat2[idx]
                t = times[idx] if idx < len(times) else 0.0

                if s1:
                    key = (self.cmu_channel, 8, s1)
                    if key not in nonzero_statuses:
                        nonzero_statuses.add(key)
                        self.runner.report_status(
                            {
                                "channel": self.cmu_channel,
                                "data_type": 8,
                                "status": s1,
                                "desc": B1500Session.describe_status_bits(s1),
                            }
                        )
                if s2:
                    key = (self.cmu_channel, 9, s2)
                    if key not in nonzero_statuses:
                        nonzero_statuses.add(key)
                        self.runner.report_status(
                            {
                                "channel": self.cmu_channel,
                                "data_type": 9,
                                "status": s2,
                                "desc": B1500Session.describe_status_bits(s2),
                            }
                        )

                results.append([x, y1, y2, t, s1, s2, (s1 | s2)])
        finally:
            # Always force the instrument into a safe idle state after C-V sweep.
            try:
                b1500.zero_output(B1500Session.CH_ALL)
            except Exception as e:
                self.log(f"Warning: failed to zero outputs after C-V sweep: {e}")
            try:
                b1500.set_switch(B1500Session.CH_ALL, False)
            except Exception as e:
                self.log(f"Warning: failed to open switches after C-V sweep: {e}")

        if results:
            p_vals = [row[1] for row in results]
            m_vals = [row[2] for row in results]
            self.log(
                f"{primary_name} range: {min(p_vals):.6g} to {max(p_vals):.6g}; "
                f"{monitor_name} range: {min(m_vals):.6g} to {max(m_vals):.6g}"
            )
        self.log(f"Collected {len(results)} C-V points")
        return results

    def _expected_points(self):
        # For linear sweeps, single = points, double = 2*points-1.
        if self.double_sweep:
            return max(1, (2 * self.points) - 1)
        return self.points
