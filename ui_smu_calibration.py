"""Explicit SMU maintenance, independent of the selected measurement procedure.

Physical open terminals are confirmed by the operator; opening SMU output relays
alone does not establish that condition. Use the existing runner ownership and
Abort path, but do not schedule calibration or save it as a procedure setting.
"""

import threading
from tkinter import messagebox

from instrumentio.protocol import InstrumentCancelled
from runner import MeasurementAbortRequested, MeasurementSkipRequested


def calibrate_smus(ui):
    if ui._run_thread and ui._run_thread.is_alive():
        messagebox.showwarning("SMU Calibration", "Stop the active run before calibrating.", parent=ui.root)
        return
    session = ui.runner.b1500
    address = session.address if session and session.is_open else ui.config.data.get('gpib_address', 'GPIB0::17::INSTR')
    if not messagebox.askokcancel(
        "SMU Calibration",
        f"Calibrate installed SMUs at {address}.\n\n"
        "Open all SMU measurement terminals and disconnect the device under test.\n"
        "Press OK when the open-circuit condition is ready.", parent=ui.root,
    ):
        return

    ui.runner.stop_event.clear()
    ui.runner.skip_device_event.clear()
    ui._set_running_state(True)
    ui._set_section_enabled(ui.prober_frame, False)
    ui.log(f"SMU self-calibration started at {address}.")

    def finish():
        ui._run_thread = None
        ui.runner.stop_event.clear()
        ui.runner.skip_device_event.clear()
        ui._set_running_state(False)
        ui._set_section_enabled(ui.prober_frame, True)

    def target():
        try:
            b1500 = ui.runner.get_b1500(address)
            with b1500.exclusive():
                ui.runner.check_stop("SMU calibration cancelled before start")
                slots = b1500.calibrate_smus()
            text = "SMU self-calibration passed: slots " + ', '.join(map(str, slots)) + '.'
            ui._post_log(text)
            ui._post(messagebox.showinfo, "SMU Calibration", text)
        except (MeasurementAbortRequested, MeasurementSkipRequested, InstrumentCancelled):
            ui._post_log("SMU self-calibration cancelled; completion was not confirmed.")
        except Exception as exc:
            ui._post_log(f"SMU self-calibration failed: {exc}")
            ui._post(messagebox.showerror, "SMU Calibration", str(exc))
        finally:
            ui._post(finish)

    ui._run_thread = threading.Thread(target=target, daemon=True)
    ui._run_thread.start()
