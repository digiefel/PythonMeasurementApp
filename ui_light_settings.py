"""Scope light settings dialog."""

import tkinter as tk
from tkinter import ttk

from tooltip_helper import attach_tooltip
from window_layout import center_popup


def show_light_settings(parent, settings, on_apply):
    dialog = tk.Toplevel(parent)
    dialog.title("Light settings")
    dialog.transient(parent)
    dialog.resizable(False, False)

    level = tk.IntVar(dialog, value=settings['level'])
    measurement_level = tk.IntVar(dialog, value=settings['measurement_level'])
    auto_adjust = tk.BooleanVar(dialog, value=settings['auto_adjust'])
    body = ttk.Frame(dialog, padding=12)
    body.grid(sticky="nsew")
    body.grid_columnconfigure(1, weight=1)

    ttk.Label(body, text="Light level (%)").grid(row=0, column=0, sticky="w", padx=(0, 12))
    normal_slider = tk.Scale(
        body, from_=0, to=100, resolution=1, orient=tk.HORIZONTAL,
        variable=level, length=240, highlightthickness=0,
    )
    normal_slider.grid(row=0, column=1, sticky="ew", columnspan=2)
    attach_tooltip(normal_slider, "Brightness used by Light ON and restored after measurements when Auto-adjust is enabled. 0 turns the light off.")

    ttk.Label(body, text="During measurement (%)").grid(row=1, column=0, sticky="w", padx=(0, 12))
    measurement_slider = tk.Scale(
        body, from_=0, to=100, resolution=1, orient=tk.HORIZONTAL,
        variable=measurement_level, length=240, highlightthickness=0,
    )
    measurement_slider.grid(row=1, column=1, sticky="ew")
    attach_tooltip(measurement_slider, "Brightness applied before each measurement when Auto-adjust is enabled. 0 measures with the light off.")

    def update_slider_state():
        enabled = auto_adjust.get()
        measurement_slider.configure(
            state=tk.NORMAL if enabled else tk.DISABLED,
            foreground=normal_slider.cget("foreground") if enabled else "gray",
        )

    auto_check = ttk.Checkbutton(
        body, text="Auto-adjust", variable=auto_adjust, command=update_slider_state,
    )
    auto_check.grid(row=1, column=2, sticky="w", padx=(12, 0))
    attach_tooltip(auto_check, "Use the measurement brightness during measurements and restore the normal brightness afterward. Uncheck to leave the light under manual control, including during Stop and Skip.")
    update_slider_state()

    ttk.Label(
        body, text="With Auto-adjust off, measurements leave the light untouched.",
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 12))

    def apply():
        on_apply({
            'level': level.get(),
            'measurement_level': measurement_level.get(),
            'auto_adjust': auto_adjust.get(),
        })
        dialog.destroy()

    buttons = ttk.Frame(body)
    buttons.grid(row=3, column=0, columnspan=3, sticky="e")
    ttk.Button(buttons, text="Cancel", command=dialog.destroy).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(buttons, text="Apply", command=apply).grid(row=0, column=1)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    center_popup(dialog, parent)
    dialog.grab_set()
    return dialog
