import time
from typing import Optional, Callable
from sentio_prober_control.Communication.CommunicatorVisa import CommunicatorVisa
from sentio_prober_control.Sentio.ProberSentio import SentioProber
from sentio_prober_control.Sentio.Enumerations import (
    XyReference,
    SteppingContactMode,
    ChuckSite,
    ThermoChuckState,
    ZReference,
    CameraMountPoint,
)
from sentio_prober_control.Sentio.Response import Response


class ProberController:
    """Encapsulate SENTIO prober interactions."""

    DEFAULT_ADDRESS = "GPIB0::28::INSTR"
    INIT_TIMEOUT_MS = 5000

    def __init__(self, log: Callable[[str], None]):
        self.log = log
        self.prober: Optional[SentioProber] = None
        self._last_init_error: Optional[str] = None
        self.subsite_origin = None
        self._scope_light_on: Optional[bool] = None

    def initialize(self, force: bool = False) -> bool:
        """Initialize the SENTIO session.

        Returns True when the prober is ready for commands.
        Returns False when initialization fails; details are available via
        get_last_init_error().
        """
        if self.prober is not None:
            if force:
                self.close()
            else:
                return True
        return self._initialize_session()

    def _initialize_session(self) -> bool:
        """Open VISA, create SENTIO prober, and apply startup defaults."""
        comm = CommunicatorVisa()
        try:
            self.log(f"Opening SENTIO prober session at {self.DEFAULT_ADDRESS}")
            self._connect_with_init_timeout(comm)

            prober = SentioProber(comm)
            prober.set_stepping_contact_mode(SteppingContactMode.BackToContact)

            self.prober = prober
            self._last_init_error = None
            return True
        except Exception as e:
            err = f"SENTIO initialization failed: {e}"
            self.log(f"Warning: {err}")
            self._last_init_error = err
            self.prober = None
            self._cleanup_failed_comm(comm)
            return False

    def _connect_with_init_timeout(self, comm: CommunicatorVisa) -> None:
        """Open VISA resource with a short timeout during initialization.

        sentio_prober_control does not provide a public timeout parameter for
        CommunicatorVisa.connect(), so we set the internal VISA handle directly.
        """
        rm = getattr(comm, "_CommunicatorVisa__rm")
        visa = rm.open_resource(self.DEFAULT_ADDRESS)
        visa.timeout = self.INIT_TIMEOUT_MS
        setattr(comm, "_CommunicatorVisa__visa", visa)
        setattr(comm, "_CommunicatorVisa__address", self.DEFAULT_ADDRESS)

    def _cleanup_failed_comm(self, comm: CommunicatorVisa) -> None:
        """Best-effort cleanup for partially initialized VISA communicator."""
        try:
            comm.disconnect()
        except Exception:
            pass

        rm = getattr(comm, "_CommunicatorVisa__rm", None)
        if rm is not None:
            try:
                rm.close()
            except Exception:
                pass

    def get_last_init_error(self) -> Optional[str]:
        return self._last_init_error

    def _get(self) -> SentioProber:
        if self.prober is None:
            if not self.initialize():
                raise RuntimeError(self._last_init_error or "SENTIO prober is not available.")
        assert self.prober is not None
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

    def read_position(self) -> tuple[float, float]:
        prober = self._get()
        x, y = prober.get_chuck_xy(ChuckSite.Wafer, XyReference.Home)
        return x, y

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

    # --- Vision helpers ---
    def set_scope_light(self, light_on: bool, on_level: int = 80) -> Optional[bool]:
        try:
            prober = self._get()
            camera = CameraMountPoint.Scope
            if not prober.vision.has_camera(camera):
                self.log("Warning: Scope camera is not available on this prober.")
                return None

            target = on_level if light_on else 0
            prober.vision.camera.set_light(camera, target)
            self._scope_light_on = light_on
            self.log(f"Scope light {'ON' if light_on else 'OFF'} (level={target}).")
            return light_on
        except Exception as e:
            self.log(f"Warning: Set scope light failed: {e}")
            return None

    def toggle_scope_light(self, on_level: int = 80) -> Optional[bool]:
        try:
            prober = self._get()
            camera = CameraMountPoint.Scope
            if not prober.vision.has_camera(camera):
                self.log("Warning: Scope camera is not available on this prober.")
                return None

            if self._scope_light_on is None:
                current = prober.vision.camera.get_light(camera)
                self._scope_light_on = current > 0.5

            return self.set_scope_light(not self._scope_light_on, on_level)
        except Exception as e:
            self.log(f"Warning: Toggle scope light failed: {e}")
            return None

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
                return None
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
                case ThermoChuckState.Uncontrolled:
                    return "uncontrolled"
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
