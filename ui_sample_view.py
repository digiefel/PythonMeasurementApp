"""An embedded whole-sample map using the selection dialog's viewport and gestures."""

import tkinter as tk
from tkinter import ttk

from ui_device_selection import DeviceSelectionDialog


class SampleMap(DeviceSelectionDialog):
    def __init__(self, parent, items, annotations, selected, on_select, on_context):
        self.on_select, self.on_context = on_select, on_context
        self._context_start = None
        super().__init__(parent, items, initially_selected=selected, annotations=annotations)

    def _create_dialog(self):
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill='both', expand=True)
        controls = ttk.Frame(self.frame)
        controls.pack(fill='x', padx=5, pady=5)
        for label, action in (
            ('Fit View', self._fit_view), ('Select All', self._select_all), ('Clear', self._clear_selection),
            ('−', lambda: self._zoom_at(self.canvas_width / 2, self.canvas_height / 2, 1 / 1.2)),
            ('+', lambda: self._zoom_at(self.canvas_width / 2, self.canvas_height / 2, 1.2)),
        ):
            ttk.Button(controls, text=label, command=action).pack(side='left', padx=2)
        self.selection_label = ttk.Label(controls, text=f'Selected: {len(self.selected_devices)}')
        self.selection_label.pack(side='right')
        self.canvas = tk.Canvas(self.frame, width=700, height=600, background='white', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self._bind_canvas_events()
        self._draw_devices()
        self._fit_job = self.frame.after_idle(self._initial_fit)
        self.frame.bind('<Destroy>', self._on_destroy, add='+')

    def _initial_fit(self):
        self._fit_job = None
        self._fit_view()

    def _on_destroy(self, event):
        if event.widget == self.frame:
            if self._fit_job:
                self.frame.after_cancel(self._fit_job)
            self._hide_annotation()

    def _draw_devices(self):
        super()._draw_devices()
        transform, sites = self._calculate_transform(), {}
        self.site_bounds = {}
        for item in self.devices:
            sites.setdefault(item.identity.site, []).append(transform(item.x, item.y))
        for site, points in sites.items():
            xs, ys = zip(*points)
            self.site_bounds[site] = min(xs) - 18, min(ys) - 35, max(xs) + 18, max(ys) + 18
            box = self.canvas.create_rectangle(min(xs) - 18, min(ys) - 25, max(xs) + 18, max(ys) + 18,
                                               outline='gray75', dash=(3, 3), tags=('site_box', site))
            self.canvas.tag_lower(box)
            self.canvas.create_text(min(xs) - 15, min(ys) - 28, text=site, anchor='sw', fill='gray40')

    def _update_selection_label(self):
        super()._update_selection_label()
        self.on_select(set(self.selected_devices))

    def _on_pan_start(self, event):
        self._context_start = event.x, event.y
        return super()._on_pan_start(event)

    def _on_pan_end(self, event):
        super()._on_pan_end(event)
        if self._context_start is not None:
            x, y = self._context_start
            if abs(event.x - x) < 5 and abs(event.y - y) < 5:
                transform = self._calculate_transform()
                item = next((item for item in self.devices if self._contains_point(item, transform, event.x, event.y)), None)
                if item is not None:
                    self.on_context('device', item.identity, event)
                else:
                    site = next((name for name, (left, top, right, bottom) in self.site_bounds.items()
                                 if left <= event.x <= right and top <= event.y <= bottom), None)
                    self.on_context('site' if site else 'chip', site, event)
        self._context_start = None
        return 'break'
