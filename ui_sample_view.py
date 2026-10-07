"""An embedded whole-sample map using the selection dialog's viewport and gestures."""

import tkinter as tk
from tkinter import ttk

from ui_device_selection import DeviceSelectionDialog
from data_management import STATUS_COLORS


class SampleMap(DeviceSelectionDialog):
    def __init__(self, parent, items, annotations, selected, on_select, on_context):
        self.on_select, self.on_context = on_select, on_context
        self._context_start = None
        self._labels_visible = False
        self._label_scale = None
        self._site_items = {}
        self._appearance = {}
        self._manual_state = None
        self._items_by_name = {item.name: item for item in items}
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
        if self.unpositioned_devices:
            unplaced = ttk.LabelFrame(self.frame, text='Devices without map positions')
            unplaced.pack(side='bottom', fill='x', padx=5, pady=5)
            self.manual_list = tk.Listbox(unplaced, selectmode=tk.MULTIPLE, exportselection=False,
                                          height=min(4, len(self.unpositioned_devices)), width=1)
            scrollbar = ttk.Scrollbar(unplaced, command=self.manual_list.yview)
            scrollbar.pack(side='right', fill='y')
            self.manual_list.configure(yscrollcommand=scrollbar.set)
            self.manual_list.pack(fill='x', expand=True)
            self.manual_list.bind('<<ListboxSelect>>', self._update_manual_selection)
            self.manual_list.bind('<Button-3>', self._manual_context)
            self.manual_list.bind('<Button-2>', self._manual_context)
        self.canvas = tk.Canvas(self.frame, width=700, height=600, background='white', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        # Batch thousands of marker coordinates in one Python/Tcl crossing.
        self.canvas.tk.eval("""
            proc ::pma_map_positions {canvas markers labels} {
                foreach {id x0 y0 x1 y1} $markers { $canvas coords $id $x0 $y0 $x1 $y1 }
                foreach {id x y} $labels { $canvas coords $id $x $y }
            }
        """)
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
        self._hide_annotation()
        transform = self._calculate_transform()
        scale = self._view[0]
        self.point_radius = max(1.2, min(6, 32 * scale))
        if self._label_scale is None:
            groups = {}
            for item in self.devices:
                groups.setdefault((item.identity.site, item.identity.subsite), []).append((item.x, item.y))
            gaps = []
            for points in groups.values():
                for axis in (0, 1):
                    values = sorted({point[axis] for point in points})
                    gaps.extend(b - a for a, b in zip(values, values[1:]) if b > a)
            label_width = max((len(item.display_name) for item in self.devices), default=0) * 6 + 20
            self._label_scale = label_width / min(gaps) if gaps else 0
            # Assessed markers are drawn above unassessed markers at shared positions.
            self.devices.sort(key=lambda item: bool(self.annotations.get(item.name, {}).get('status')))
        self._labels_visible = scale >= self._label_scale
        positions, sites = [], {}
        for item in self.devices:
            cx, cy = transform(item.x, item.y)
            sites.setdefault(item.identity.site, []).append((cx, cy))
            if item.name not in self.device_items:
                self.device_items[item.name] = self._draw_device(item, transform)
            marker, _ = self.device_items[item.name]
            radius = self.point_radius
            positions.extend((marker, cx - radius, cy - radius, cx + radius, cy + radius))
            annotation = self.annotations.get(item.name, {})
            appearance = (item.name in self.selected_devices, annotation.get('status'), annotation.get('has_notes'))
            if self._appearance.get(item.name) != appearance:
                self._update_device_appearance(item.name, appearance[0])
                self._appearance[item.name] = appearance
                if appearance[0] or appearance[1]:
                    self.canvas.tag_raise(marker)
        labels = self._sync_labels(transform)
        self.canvas.tk.call('::pma_map_positions', str(self.canvas), tuple(positions), tuple(labels))
        self._refresh_manual_list()
        self.site_bounds = {}
        padding = 64 * scale  # A fixed margin in sample coordinates, not screen pixels.
        for site, points in sites.items():
            xs, ys = zip(*points)
            left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
            self.site_bounds[site] = (left - padding, top - padding, right + padding, bottom + padding)
            if site not in self._site_items:
                box = self.canvas.create_rectangle(0, 0, 0, 0, outline='gray75', dash=(3, 3),
                                                   tags=('map_content', 'site_box', site))
                label = self.canvas.create_text(0, 0, text=site, anchor='sw', fill='gray30',
                                                font=('TkDefaultFont', 9, 'bold'), tags=('map_content',))
                background = self.canvas.create_rectangle(0, 0, 0, 0, fill='white', outline='white',
                                                           tags=('map_content',))
                self._site_items[site] = box, label, background
            box, label, background = self._site_items[site]
            self.canvas.coords(box, *self.site_bounds[site])
            self.canvas.tag_lower(box)
            self.canvas.coords(label, left - padding, top - padding - 3)
            bounds = self.canvas.bbox(label)
            if bounds:
                x0, y0, x1, y1 = bounds
                self.canvas.coords(background, x0 - 2, y0 - 1, x1 + 2, y1 + 1)
            self.canvas.tag_raise(background)
            self.canvas.tag_raise(label)

    def _label_visible(self, item):
        x, y = self._calculate_transform()(item.x, item.y)
        return (-20 <= x <= self.canvas_width + 20 and -20 <= y <= self.canvas_height + 20
                and (self._labels_visible or (len(self.selected_devices) <= 10 and item.name in self.selected_devices)))

    def _sync_labels(self, transform):
        positions = []
        for item in self.devices:
            marker, label = self.device_items[item.name]
            if self._label_visible(item):
                if label is None:
                    label = self._create_device_label(item, transform)
                cx, cy = transform(item.x, item.y)
                positions.extend((label, cx + self.label_offset, cy - self.label_offset))
                self.canvas.tag_raise(label)
            elif label is not None:
                self.canvas.delete(label)
                label = None
            self.device_items[item.name] = marker, label
        return positions

    def _update_device_appearance(self, name, selected):
        super()._update_device_appearance(name, selected)
        if name in self.device_items:
            marker, label = self.device_items[name]
            if selected:
                self.canvas.tag_raise(marker)
            if label is not None:
                item = self._items_by_name[name]
                annotation = self.annotations.get(name, {})
                self.canvas.itemconfigure(label, text=item.display_name
                                          + (f" [{annotation['status']}]" if annotation.get('status') else '')
                                          + (' *' if annotation.get('has_notes') else ''))

    def _refresh_manual_list(self):
        if self.manual_list is None:
            return
        state = tuple((item.name, self.annotations.get(item.name, {}).get('status', ''),
                       item.name in self.selected_devices) for item in self.unpositioned_devices)
        if state == self._manual_state:
            return
        self._manual_state = state
        self.manual_list.delete(0, tk.END)
        for index, item in enumerate(self.unpositioned_devices):
            annotation = self.annotations.get(item.name, {})
            status = annotation.get('status', '')
            self.manual_list.insert(tk.END, item.name + (f' [{status}]' if status else ''))
            if status:
                self.manual_list.itemconfigure(index, foreground=STATUS_COLORS.get(status, 'gray'))
            if item.name in self.selected_devices:
                self.manual_list.selection_set(index)

    def _manual_context(self, event):
        index = self.manual_list.nearest(event.y)
        self.on_context('device', self.unpositioned_devices[index].identity, event)

    def _update_selection_label(self):
        super()._update_selection_label()
        self._sync_labels(self._calculate_transform())
        self.on_select(set(self.selected_devices))

    def _on_pan_start(self, event):
        self._context_start = event.x, event.y
        return super()._on_pan_start(event)

    def _on_pan_drag(self, event):
        if self._pan_start is not None:
            dx, dy = event.x - self._pan_start[0], event.y - self._pan_start[1]
            self.site_bounds = {site: (left + dx, top + dy, right + dx, bottom + dy)
                                for site, (left, top, right, bottom) in self.site_bounds.items()}
        return super()._on_pan_drag(event)

    def _on_pan_end(self, event):
        super()._on_pan_end(event)
        self._sync_labels(self._calculate_transform())
        if self._context_start is not None:
            x, y = self._context_start
            if abs(event.x - x) < 5 and abs(event.y - y) < 5:
                item = self._device_at(event.x, event.y)
                if item is not None:
                    self.on_context('device', item.identity, event)
                else:
                    site = next((name for name, (left, top, right, bottom) in self.site_bounds.items()
                                 if left <= event.x <= right and top <= event.y <= bottom), None)
                    self.on_context('site' if site else 'chip', site, event)
        self._context_start = None
        return 'break'
