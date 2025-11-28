import tkinter as tk


class ToolTip:
    """Lightweight tooltip that shows on hover."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tipwindow = None

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("TkDefaultFont", 9),
            padx=4,
            pady=2,
        )
        label.pack(ipadx=1)

    def hide(self, event=None):
        tw = self.tipwindow
        if tw:
            tw.destroy()
            self.tipwindow = None


def attach_tooltip(widget, text: str):
    """Bind hover handlers to show/hide a tooltip with the given text."""
    if not text:
        return
    tooltip = ToolTip(widget, text)
    widget.bind("<Enter>", tooltip.show)
    widget.bind("<Leave>", tooltip.hide)
