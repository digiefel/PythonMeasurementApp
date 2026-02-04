import time
from typing import Optional, Callable
from sentio_prober_control.Sentio.ProberSentio import SentioProber
from sentio_prober_control.Sentio.Enumerations import (
    XyReference,
    SteppingContactMode,
    ChuckSite,
    ThermoChuckState,
    ZReference,
)
from sentio_prober_control.Sentio.Response import Response


class ProberController:
    """Encapsulate SENTIO prober interactions."""

    def __init__(self, log: Callable[[str], None]):
        self.log = log
        self.prober: Optional[SentioProber] = None
        self.subsite_origin = None

    def _get(self) -> SentioProber:
        if self.prober is None:
            addr = "GPIB0::28::INSTR"
            self.log(f'Opening SENTIO prober session at {addr}')
            self.prober = SentioProber.create_prober("visa", addr)
            self.prober.set_stepping_contact_mode(SteppingContactMode.BackToContact)
        return self.prober

    # --- Positioning helpers ---
    def set_subsite_origin(self, x_offset: float, y_offset: float):
        try:
            prober = self._get()
            x, y = prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
            x, y = (x - x_offset, y - y_offset)
            self.subsite_origin = (x, y)
            self.log(f'Subsite origin recorded at X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log(f'Warning: Failed to set subsite origin: {e}')

    def go_home(self):
        try:
            if not self.subsite_origin:
                self.log('No subsite origin recorded. Use "Set Home" first.')
                return
            prober = self._get()
            x0, y0 = self.subsite_origin
            x, y = prober.move_chuck_xy(XyReference.Home, x0, y0)
            prober.wait_all()
            self.log(f'Chuck moved to recorded origin X={x:.1f}um, Y={y:.1f}um')
        except Exception as e:
            self.log(f'Warning: Go home failed: {e}')

    def contact(self) -> bool:
        try:
            prober = self._get()
            prober.move_chuck_contact()
            prober.wait_all()
            self.log('Chuck moved to contact')
            return True
        except Exception as e:
            self.log(f'Warning: Contact failed: {e}')
            return False

    def separation(self) -> bool:
        try:
            prober = self._get()
            prober.move_chuck_separation()
            prober.wait_all()
            self.log('Chuck moved to separation')
            return True
        except Exception as e:
            self.log(f'Warning: Separation failed: {e}')
            return False

    def read_position(self):
        try:
            prober = self._get()
            x, y = prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
            return x, y
        except Exception as e:
            self.log(f'Warning: Read position failed: {e}')
            return None

    def get_chuck_height(self) -> Optional[float]:
        try:
            prober = self._get()
            height = prober.get_chuck_z(ZReference.Contact)
            return height
        except Exception as e:
            self.log(f"Warning: Get chuck height failed: {e}")
            return None

    def move_xy_home(self, target_x: float, target_y: float):
        prober = self._get()
        prober.move_chuck_xy(XyReference.Home, target_x, target_y)
        prober.wait_all()
        return prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)

    # --- Temperature helpers ---
    def set_temp(self, temp_c: float):
        self.log(f"Setting temperature setpoint to {temp_c:.2f} C")
        try:
            prober = self._get()
            prober.status.comm.send(f"status:set_chuck_temp {temp_c:.2f}")
            Response.check_resp(prober.status.comm.read_line())
            return True
        except Exception as e:
            self.log(f"Warning: Set chuck temperature failed: {e}")
            return False

    def get_temp(self) -> Optional[float]:
        try:
            prober = self._get()
            if prober.status.get_chuck_thermo_state() == ThermoChuckState.Uncontrolled:
                return 25.0 # TODO this is a bit of a hack
            else:
                return prober.status.get_chuck_temp()
        except Exception as e:
            self.log(f"Warning: Get chuck temperature failed: {e}")
            return None

    def get_temp_setpoint(self) -> Optional[float]:
        try:
            prober = self._get()
            return prober.status.get_chuck_temp_setpoint()
        except Exception as e:
            self.log(f"Warning: Get chuck temperature setpoint failed: {e}")
            return None

    def get_chuck_site_height(self, site: ChuckSite = ChuckSite.Wafer):
        """Return (contact, separation, overtravel, hover) heights for the site."""
        try:
            prober = self._get()
            return prober.get_chuck_site_height(site)
        except Exception as e:
            self.log(f"Warning: Get chuck site height failed: {e}")
            return None

    def set_chuck_site_height(self, contact: float, separation: float, overtravel_dist: float, hover_gap: float, site: ChuckSite = ChuckSite.Wafer):
        """Set chuck Z positions for the site."""
        try:
            prober = self._get()
            prober.set_chuck_site_height(site, contact, separation, overtravel_dist, hover_gap)
            return True
        except Exception as e:
            self.log(f"Warning: Set chuck site height failed: {e}")
            return False

    def get_thermo_state(self) -> Optional[str]:
        try:
            prober = self._get()
            state = prober.status.get_chuck_thermo_state()
            match state:
                case ThermoChuckState.Heating:
                    return "heating"
                case ThermoChuckState.Cooling:
                    return "cooling"
                case ThermoChuckState.Controlling:
                    return "controlling"
                case ThermoChuckState.Error:
                    return "error"
                case ThermoChuckState.Soaking:
                    return "soaking"
                case _:
                    return "idle"
        except Exception as e:
            self.log(f"Warning: Get thermo state failed: {e}")
            return None

    def wait_until_temp(
        self,
        target_c: float,
        tol_c: float = 0.5,
        wait_time_s: float = 0.0,
        poll_s: float = 1.0,
        timeout_s: float = 900.0,
        sample_cb=None,
        stop_check=None,
    ) -> bool:
        """Poll until temp within tolerance, optionally enforcing soak time."""
        self.log(f"Waiting for chuck to stabilize at {target_c:.1f} C (+/-{tol_c:.1f} C)")
        start = time.time()
        reached = False
        while True:
            if stop_check:
                stop_check("Stop requested during temperature wait")
            temp = self.get_temp()
            if sample_cb and temp is not None:
                sample_cb(time.time(), temp)
            if temp is not None and abs(temp - target_c) <= tol_c:
                if wait_time_s > 0:
                    stable_start = time.time()
                    while True:
                        if stop_check:
                            stop_check("Stop requested during temperature wait")
                        temp = self.get_temp()
                        if sample_cb and temp is not None:
                            sample_cb(time.time(), temp)
                        if temp is not None and abs(temp - target_c) <= tol_c:
                            if (time.time() - stable_start) >= wait_time_s:
                                break
                        else:
                            stable_start = time.time()
                        time.sleep(max(poll_s, 0.25))
                reached = True
                break
            if timeout_s and (time.time() - start) > timeout_s:
                break
            time.sleep(max(poll_s, 0.25))
        return reached

    def close(self):
        """Return control to local and tear down VISA session cleanly."""
        if not self.prober:
            return
        try:
            self.prober.comm.send("*LOCAL")
        except Exception:
            pass
        try:
            # Explicitly disconnect communicator so pyvisa ResourceManager does not rely on __del__.
            self.prober.comm.disconnect()
            rm = getattr(self.prober.comm, "_CommunicatorVisa__rm", None)
            if rm:
                rm.close()
        except Exception:
            pass
        self.prober = None
