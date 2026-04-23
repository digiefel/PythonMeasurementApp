"""Framebuffer capture to PNG using DearPyGui's built-in file output."""

from __future__ import annotations

import os
import time

import dearpygui.dearpygui as dpg


def capture_framebuffer(path: str) -> None:
    """Capture the viewport framebuffer to a PNG file.

    Uses dpg.output_frame_buffer(file=...) which writes the PNG on the next
    rendered frame. Renders a couple of frames after the request to give the
    runtime time to complete the capture.
    """
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Flush any pending draws before capturing.
    for _ in range(3):
        dpg.render_dearpygui_frame()

    dpg.output_frame_buffer(file=path)

    # The capture completes on a subsequent rendered frame.
    for _ in range(5):
        dpg.render_dearpygui_frame()
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return
        time.sleep(0.01)

    if not os.path.exists(path):
        raise RuntimeError(f"output_frame_buffer did not create file: {path!r}")
    if os.path.getsize(path) == 0:
        raise RuntimeError(f"output_frame_buffer wrote empty file: {path!r}")
