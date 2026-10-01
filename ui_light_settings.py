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

    normal_label = ttk.Label(body, text="Light level (%)")
    normal_label.grid(row=0, column=0, sticky="w", padx=(0, 12))
    normal_slider = tk.Scale(
        body, from_=0, to=100, resolution=1, orient=tk.HORIZONTAL,
        variable=level, length=240, highlightthickness=0,
    )
    normal_slider.grid(row=0, column=1, sticky="ew", columnspan=2)
    attach_tooltip(normal_label, "Set the scope brightness used when you turn the light on. With Auto-adjust enabled, this brightness is restored after each measurement.")

    measurement_label = ttk.Label(body, text="During measurement (%)")
    measurement_label.grid(row=1, column=0, sticky="w", padx=(0, 12))
    measurement_slider = tk.Scale(
        body, from_=0, to=100, resolution=1, orient=tk.HORIZONTAL,
        variable=measurement_level, length=240, highlightthickness=0,
    )
    measurement_slider.grid(row=1, column=1, sticky="ew")
    attach_tooltip(measurement_label, "Set the scope brightness used during measurements when Auto-adjust is enabled. Set it to 0 to measure with the light off.")

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
    attach_tooltip(auto_check, "Automatically switch to the measurement brightness before each measurement and restore the normal brightness afterward.")
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
    cancel_button = ttk.Button(buttons, text="Cancel", command=dialog.destroy)
    cancel_button.grid(row=0, column=0, padx=(0, 6))
    apply_button = ttk.Button(buttons, text="Apply", command=apply)
    apply_button.grid(row=0, column=1)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    center_popup(dialog, parent)
    dialog.grab_set()
    return dialog
