"""List builder dialog: fill a list field with evenly spaced values."""

import math
import tkinter as tk
from tkinter import ttk

from si_utils import format_si_compact, parse_si_list, parse_si_value
from window_layout import center_popup

MAX_VALUES = 10000
# Six significant figures keep log-spaced values readable while linear steps stay distinct.
SIG_FIGS = 6


def build_values(start: float, stop: float, points: int, spacing: str = "linear", step: float | None = None) -> list[float]:
    """Return ``points`` values going from ``start`` toward ``stop``.

    Linear spacing adds ``step`` each time. Without a step it uses the one that
    lands exactly on ``stop``; a step that does not divide the range stops short.
    Log spacing is even on a log scale, always ends on ``stop``, and needs
    ``start`` and ``stop`` of the same sign.
    """
    if points < 1:
        raise ValueError("Points must be at least 1")
    if points > MAX_VALUES:
        raise ValueError(f"At most {MAX_VALUES} values")
    if points == 1:
        return [start]
    if spacing == "log":
        if not start * stop > 0:
            raise ValueError("Log spacing needs start and stop of the same sign, not 0")
        return [start * (stop / start) ** (i / (points - 1)) for i in range(points)]
    if step is None:
        step = (stop - start) / (points - 1)
    else:
        # The direction always follows start -> stop, whatever sign was typed.
        step = math.copysign(abs(step), stop - start)
    return [start + step * i for i in range(points)]


def points_for_step(start: float, stop: float, step: float) -> int:
    """Number of linear values from ``start`` that fit before passing ``stop``."""
    if step == 0:
        raise ValueError("Step must not be 0")
    # The small tolerance keeps e.g. 1 -> 4 in steps of 0.1 at 31 points despite float rounding.
    return math.floor(abs(stop - start) / abs(step) + 1e-9) + 1


def _format(value: float) -> str:
    return format_si_compact(value, SIG_FIGS)


def show_list_builder(parent, target_var, title="Build list"):
    """Open the builder for ``target_var``; Append or Replace writes the list into it."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)

    # Start from the list already in the field, so small edits stay small.
    try:
        current = parse_si_list(target_var.get())
    except ValueError:
        current = []
    start_var = tk.StringVar(dialog, value=_format(current[0]) if current else "0")
    stop_var = tk.StringVar(dialog, value=_format(current[-1]) if len(current) > 1 else "1")
    points_var = tk.StringVar(dialog, value=str(len(current)) if len(current) > 1 else "11")
    spacing_var = tk.StringVar(dialog, value="Linear")
    step_var = tk.StringVar(dialog)
    values = None

    body = ttk.Frame(dialog, padding=10)
    body.grid(sticky="nsew")
    start_entry = ttk.Entry(body, textvariable=start_var, width=9)
    stop_entry = ttk.Entry(body, textvariable=stop_var, width=9)
    spacing_box = ttk.Combobox(body, textvariable=spacing_var, values=("Linear", "Log"), state="readonly", width=7)
    points_entry = ttk.Entry(body, textvariable=points_var, width=7)
    step_entry = ttk.Entry(body, textvariable=step_var, width=9)
    labels = []
    for column, (text, widget) in enumerate((
        ("Start", start_entry), ("Stop", stop_entry), ("Spacing", spacing_box),
        ("Points", points_entry), ("Step", step_entry),
    )):
        label = ttk.Label(body, text=text)
        label.grid(row=0, column=column, sticky="w", padx=(0, 6))
        widget.grid(row=1, column=column, sticky="w", padx=(0, 6))
        labels.append(label)
    step_label = labels[-1]

    status = ttk.Label(body)
    status.grid(row=2, column=0, columnspan=5, sticky="w", pady=(8, 0))
    status_color = status.cget("foreground")
    preview = ttk.Label(body, font="TkFixedFont", wraplength=380, justify="left")
    preview.grid(row=3, column=0, columnspan=5, sticky="w", pady=(2, 0))

    def update(source):
        """Recompute the field linked to the one just edited, then the preview."""
        nonlocal values
        linear = spacing_var.get() == "Linear"
        # Step only exists for linear spacing; log values are set by start, stop and points.
        for widget in (step_label, step_entry):
            if linear:
                widget.grid()
            else:
                widget.grid_remove()
        values = None
        preview.configure(text="")
        try:
            start, stop = parse_si_value(start_var.get()), parse_si_value(stop_var.get())
            step = parse_si_value(step_var.get()) if linear and source == "step" else None
            points = None if step is not None else int(points_var.get())
        except ValueError:
            status.configure(text="Enter numbers like 1u, 10m or 100", foreground="#a32d2d")
            return
        try:
            if step is not None:
                points = points_for_step(start, stop, step)
                points_var.set(str(points))
            values = build_values(start, stop, points, "linear" if linear else "log", step)
        except ValueError as exc:
            status.configure(text=str(exc), foreground="#a32d2d")
            return
        if linear and step is None:
            step_var.set(_format(abs(stop - start) / (points - 1)) if points > 1 else "")
        status.configure(text=f"{len(values)} values", foreground=status_color)
        preview.configure(text=", ".join(_format(v) for v in values))

    for entry in (start_entry, stop_entry, points_entry):
        entry.bind("<KeyRelease>", lambda event: update("points"))
    step_entry.bind("<KeyRelease>", lambda event: update("step"))
    spacing_box.bind("<<ComboboxSelected>>", lambda event: update("points"))

    def write(append):
        if values is None:
            dialog.bell()
            return
        text = ", ".join(_format(v) for v in values)
        existing = target_var.get().strip()
        target_var.set(f"{existing}, {text}" if append and existing else text)
        dialog.destroy()

    buttons = ttk.Frame(body)
    buttons.grid(row=4, column=0, columnspan=5, sticky="e", pady=(10, 0))
    ttk.Button(buttons, text="Append", command=lambda: write(True)).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(buttons, text="Replace", command=lambda: write(False)).grid(row=0, column=1)
    dialog.bind("<Escape>", lambda event: dialog.destroy())

    update("points")
    center_popup(dialog, parent)
    dialog.grab_set()
    return dialog
