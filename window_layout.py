"""Window placement in desktop work-area coordinates (Windows lab machines)."""

import ctypes
from ctypes import wintypes
from functools import lru_cache
import logging
import os
import sys

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _windows():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    signatures = {
        "GetAncestor": ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
        "MonitorFromWindow": ([wintypes.HWND, wintypes.DWORD], wintypes.HANDLE),
        "GetMonitorInfoW": ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
        "GetWindowRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        "GetClientRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        "SetWindowPos": ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
        "GetWindowThreadProcessId": ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        "IsWindowVisible": ([wintypes.HWND], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(user32, name)
        function.argtypes = arguments
        function.restype = result
    return user32


def enable_dpi_awareness():
    """Use physical pixels in both GUI processes before creating any windows."""
    if sys.platform != "win32":
        return
    user32 = _windows()
    try:
        function = user32.SetProcessDpiAwarenessContext
        function.argtypes = [ctypes.c_void_p]
        function.restype = wintypes.BOOL
        # PER_MONITOR_AWARE_V2. A manifest may have already set awareness.
        function(ctypes.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def _tk_handle(window):
    return _windows().GetAncestor(window.winfo_id(), 2)  # GA_ROOT


def work_area(window):
    """Return left, top, right, bottom on the monitor containing a Tk window."""
    if sys.platform == "win32":
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]

        api = _windows()
        monitor = api.MonitorFromWindow(_tk_handle(window), 2)  # nearest monitor
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if api.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return info.work.left, info.work.top, info.work.right, info.work.bottom
        raise ctypes.WinError(ctypes.get_last_error())
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight()


def _visible_rect(handle):
    api = _windows()
    outer = wintypes.RECT()
    if not api.GetWindowRect(handle, ctypes.byref(outer)):
        raise ctypes.WinError(ctypes.get_last_error())
    visible = wintypes.RECT()
    dwm = ctypes.WinDLL("dwmapi")
    get_bounds = dwm.DwmGetWindowAttribute
    get_bounds.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    get_bounds.restype = ctypes.c_long
    if get_bounds(handle, 9, ctypes.byref(visible), ctypes.sizeof(visible)) != 0:
        visible = outer
    return outer, visible


def _place_native(handle, bounds):
    """Fit the visible frame, compensating for Windows' invisible resize borders."""
    outer, visible = _visible_rect(handle)
    left, top, right, bottom = bounds
    x = left - (visible.left - outer.left)
    y = top - (visible.top - outer.top)
    width = right - left + (outer.right - outer.left) - (visible.right - visible.left)
    height = bottom - top + (outer.bottom - outer.top) - (visible.bottom - visible.top)
    if not _windows().SetWindowPos(handle, None, x, y, width, height, 0x0014):
        raise ctypes.WinError(ctypes.get_last_error())  # NOZORDER | NOACTIVATE


def tile_main_window(root):
    root.update_idletasks()
    left, top, right, bottom = work_area(root)
    middle = left + (right - left) // 2
    if sys.platform == "win32":
        handle = _tk_handle(root)
        bounds = (left, top, middle, bottom)
        _place_native(handle, bounds)
        # Record an explicit Tk size so later form changes cannot autosize it.
        client = wintypes.RECT()
        if not _windows().GetClientRect(handle, ctypes.byref(client)):
            raise ctypes.WinError(ctypes.get_last_error())
        root.geometry(f"{client.right-client.left}x{client.bottom-client.top}")
        root.update_idletasks()
        _place_native(handle, bounds)
    else:
        # Tk geometry sizes the client area; reserve space for the frame.
        border = max(0, root.winfo_rootx() - root.winfo_x())
        title = max(0, root.winfo_rooty() - root.winfo_y())
        root.geometry(f"{max(1, middle-left-2*border)}x{max(1, bottom-top-title-border)}{left:+d}{top:+d}")
    return {"width": right - middle, "height": bottom - top,
            "x_pos": middle, "y_pos": top}


def tile_plot_window(geometry):
    """Place the viewer's native window after Dear PyGui has shown it."""
    if sys.platform != "win32" or not geometry:
        return
    api = _windows()
    handles = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def collect(handle, _):
        process = wintypes.DWORD()
        api.GetWindowThreadProcessId(handle, ctypes.byref(process))
        if process.value == os.getpid() and api.IsWindowVisible(handle):
            handles.append(handle)
        return True

    api.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    api.EnumWindows.restype = wintypes.BOOL
    api.EnumWindows(collect, 0)
    if len(handles) != 1:
        logger.warning("Could not identify the plot viewport for placement: %s windows", len(handles))
        return
    left, top = geometry["x_pos"], geometry["y_pos"]
    _place_native(handles[0], (left, top, left + geometry["width"], top + geometry["height"]))


def center_popup(dialog, parent):
    dialog.update_idletasks()
    left, top, right, bottom = work_area(parent)
    if sys.platform == "win32":
        handle = _tk_handle(dialog)
        _, frame = _visible_rect(handle)
        width, height = frame.right - frame.left, frame.bottom - frame.top
        x, y = left + (right - left - width) // 2, top + (bottom - top - height) // 2
        _place_native(handle, (x, y, x + width, y + height))
    else:
        width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
        x, y = left + (right - left - width) // 2, top + (bottom - top - height) // 2
        dialog.geometry(f"{x:+d}{y:+d}")
