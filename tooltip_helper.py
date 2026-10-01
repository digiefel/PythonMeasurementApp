import tkinter as tk


class ToolTip:
    """Lightweight tooltip that shows on hover."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self._show_job = None

    def schedule(self, event=None):
        self.hide()
        self._show_job = self.widget.after(400, self.show)

    def show(self, event=None):
        self._show_job = None
        text = self.text() if callable(self.text) else self.text
        if self.tipwindow or not text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=text,
            justify=tk.LEFT,
            wraplength=440,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("TkDefaultFont", 9),
            padx=4,
            pady=2,
        )
        label.pack(ipadx=1)

    def hide(self, event=None):
        if self._show_job is not None:
            self.widget.after_cancel(self._show_job)
            self._show_job = None
        tw = self.tipwindow
        if tw:
            tw.destroy()
            self.tipwindow = None


def attach_tooltip(widget, text):
    """Bind hover handlers to show/hide a tooltip with the given text."""
    if not text:
        return
    tooltip = ToolTip(widget, text)
    widget.bind("<Enter>", tooltip.schedule, add="+")
    widget.bind("<Leave>", tooltip.hide, add="+")
    widget.bind("<ButtonPress>", tooltip.hide, add="+")
    widget.bind("<Destroy>", tooltip.hide, add="+")
