"""Framebuffer capture and PNG validation for the DearPyGui viewer process."""

from __future__ import annotations

import os

import dearpygui.dearpygui as dpg


def capture_framebuffer(path: str) -> None:
    """Render one frame, capture the framebuffer to path, and validate the result.

    Raises RuntimeError if the file was not created or is empty.
    """
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    dpg.render_dearpygui_frame()
    dpg.save_image(path)

    if not os.path.exists(path):
        raise RuntimeError(f"save_image did not create file: {path!r}")
    if os.path.getsize(path) == 0:
        raise RuntimeError(f"save_image wrote empty file: {path!r}")
