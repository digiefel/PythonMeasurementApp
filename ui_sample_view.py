"""An embedded whole-sample map using the selection dialog's viewport and gestures."""

import tkinter as tk
from tkinter import ttk

from ui_device_selection import DeviceSelectionDialog
from data_management import STATUS_COLORS
from sample_map_model import build_geometry, location_summary


class SampleMap(DeviceSelectionDialog):
    def __init__(self, parent, items, annotations, selected, on_select, on_context):
        self.on_select, self.on_context = on_select, on_context
        self._context_start = None
        self._locations, self._sites, self._subsites = build_geometry(items)
        self._location_by_key = {location.key: location for location in self._locations}
        self._region_by_key = {region.key: region for region in self._sites + self._subsites}
        self._region_items, self._location_items, self._levels = {}, {}, {}
        self._visible_locations, self._visible_regions = {}, []
        self._active_location_keys, self._active_region_keys = set(), set()
        self._manual_state = None
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
        self.canvas.bind('<Double-Button-1>', self._on_double_click)
        self.canvas.tag_bind('map_hover', '<Enter>', self._on_device_hover)
        self.canvas.tag_bind('map_hover', '<Leave>', lambda event: self._hide_annotation())
        self._draw_devices()
        self._fit_job = self.frame.after_idle(self._initial_fit)
        self.frame.bind('<Destroy>', self._on_destroy, add='+')

    def _initial_fit(self):
        self._fit_job = None
        self._fit_view()
        self.canvas.focus_set()

    def _on_destroy(self, event):
        if event.widget == self.frame:
            if self._fit_job:
                self.frame.after_cancel(self._fit_job)
            self._hide_annotation()

    def _level(self, key, value, threshold):
        previous = self._levels.get(key, False)
        active = value >= threshold * (0.85 if previous else 1)
        self._levels[key] = active
        return active

    def _bounds(self, region, transform):
        left, top, right, bottom = region.bounds
        x0, y0 = transform(left - 64, top - 64)
        x1, y1 = transform(right + 64, bottom + 64)
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def _in_view(self, bounds):
        left, top, right, bottom = bounds
        return right >= -30 and bottom >= -30 and left <= self.canvas_width + 30 and top <= self.canvas_height + 30

    def _draw_devices(self):
        self._hide_annotation()
        transform = self._calculate_transform()
        scale = self._view[0]
        self._visible_regions, self._visible_locations = [], {}
        self.site_bounds = {}
        active_regions, active_locations = set(), set()
        detailed_sites, device_names, label_names = set(), set(), set()
        spacing_by_name = {}
        for region in self._sites:
            bounds = self._bounds(region, transform)
            self.site_bounds[region.site] = bounds
            span = max(128, region.bounds[2] - region.bounds[0], region.bounds[3] - region.bounds[1])
            expanded = self._level(region.key, span * scale, 180)
            if expanded:
                detailed_sites.add(region.site)
            if self._in_view(bounds):
                self._draw_region(region, bounds, collapsed=not expanded)
                active_regions.add(region.key)
        for region in self._subsites:
            if region.site not in detailed_sites:
                continue
            bounds = self._bounds(region, transform)
            show_devices = self._level(region.key, region.spacing * scale, 24)
            show_labels = self._level(region.key + ':labels', region.spacing * scale, 150)
            if self._in_view(bounds):
                self._draw_region(region, bounds, collapsed=not show_devices)
                active_regions.add(region.key)
                if show_devices:
                    device_names.update(region.names)
                    for name in region.names:
                        spacing_by_name[name] = region.spacing * scale
                    if show_labels:
                        label_names.update(region.names)
        positions, texts = [], []
        for location in self._locations:
            if not location.names & device_names:
                continue
            x, y = transform(location.x, location.y)
            if not self._in_view((x - 25, y - 25, x + 25, y + 25)):
                continue
            radius = min(18, max(3, min(spacing_by_name[name] for name in location.names & device_names) * 0.18))
            detailed = bool(location.names & label_names)
            self._draw_location(location, x, y, radius, detailed, positions, texts)
            self._visible_locations[location.key] = radius
            active_locations.add(location.key)
        for key in self._active_region_keys - active_regions:
            for item in self._region_items[key]:
                self.canvas.itemconfigure(item, state='hidden')
        for key in self._active_location_keys - active_locations:
            self.canvas.itemconfigure(key, state='hidden')
        self._active_region_keys, self._active_location_keys = active_regions, active_locations
        self.canvas.tk.call('::pma_map_positions', str(self.canvas), tuple(positions), tuple(texts))
        self._refresh_manual_list()

    def _draw_region(self, region, bounds, collapsed):
        if region.key not in self._region_items:
            tags = ('map_content', 'region', region.key, 'map_hover')
            box = self.canvas.create_rectangle(0, 0, 0, 0, tags=tags)
            label = self.canvas.create_text(0, 0, anchor='sw', fill='gray25',
                                            font=('TkDefaultFont', 9, 'bold'), tags=tags)
            background = self.canvas.create_rectangle(0, 0, 0, 0, fill='white', outline='white', tags=tags)
            self._region_items[region.key] = box, label, background
        box, label, background = self._region_items[region.key]
        count = len(region.names & self.selected_devices)
        self.canvas.itemconfigure(box, state='normal', fill=('#e7f0ff' if count else '#eef1f5') if collapsed and not region.subsites else '',
                                  outline='dodgerblue' if count else ('gray50' if collapsed else 'gray80'),
                                  width=2 if count or collapsed else 1, dash=() if collapsed else (3, 3))
        self.canvas.coords(box, *bounds)
        self.canvas.tag_lower(box)
        self.canvas.itemconfigure(label, state='normal', text=region.label + (f' · {count} selected' if count else ''))
        self.canvas.coords(label, max(4, bounds[0]), max(14, bounds[1] - 3))
        label_bounds = self.canvas.bbox(label)
        if label_bounds:
            x0, y0, x1, y1 = label_bounds
            self.canvas.coords(background, x0 - 2, y0 - 1, x1 + 2, y1 + 1)
        self.canvas.itemconfigure(background, state='normal')
        self.canvas.tag_raise(background)
        self.canvas.tag_raise(label)
        self._visible_regions.append(region)

    def _draw_location(self, location, x, y, radius, detailed, positions, texts):
        label_text, count, statuses = location_summary(location, self.annotations)
        selected = bool(location.names & self.selected_devices)
        tags = ('map_content', 'location', location.key, 'map_hover')
        if location.key not in self._location_items:
            marker = self.canvas.create_oval(0, 0, 0, 0, tags=tags)
            self._location_items[location.key] = [marker, None, None, []]
        marker, count_id, label_id, segments = self._location_items[location.key]
        color = STATUS_COLORS.get(statuses[0], 'gray55') if len(statuses) == 1 else 'gray55'
        self.canvas.itemconfigure(marker, state='normal', fill=color if len(statuses) == 1 and statuses[0] else 'white',
                                  outline='dodgerblue' if selected else color,
                                  width=3 if selected else 2)
        coords = x - radius, y - radius, x + radius, y + radius
        positions.extend((marker, *coords))
        # Conflicting assessments remain visible as a segmented ring.
        if len(statuses) > 1:
            while len(segments) < len(statuses):
                segments.append(self.canvas.create_arc(0, 0, 0, 0, style='arc', tags=tags))
            for index, segment in enumerate(segments):
                if index < len(statuses):
                    inset = min(3, radius / 4) if selected else 0
                    positions.extend((segment, x - radius + inset, y - radius + inset,
                                      x + radius - inset, y + radius - inset))
                    self.canvas.itemconfigure(segment, state='normal', start=index * 360 / len(statuses),
                                              extent=360 / len(statuses), width=2,
                                              outline=STATUS_COLORS.get(statuses[index], 'gray55'))
                else:
                    self.canvas.itemconfigure(segment, state='hidden')
        else:
            for segment in segments:
                self.canvas.itemconfigure(segment, state='hidden')
        if count and radius >= 9:
            if count_id is None:
                count_id = self.canvas.create_text(0, 0, font=('TkDefaultFont', 8, 'bold'), fill='gray20', tags=tags)
            self.canvas.itemconfigure(count_id, state='normal', text=str(count),
                                      fill='white' if len(statuses) == 1 and statuses[0] in ('Good', 'Bad') else 'gray20')
            texts.extend((count_id, x, y))
        elif count_id is not None:
            self.canvas.itemconfigure(count_id, state='hidden')
        if detailed:
            if label_id is None:
                label_id = self.canvas.create_text(0, 0, anchor='w', justify='left', font=('TkDefaultFont', 8),
                                                   fill='gray20', tags=tags)
            self.canvas.itemconfigure(label_id, state='normal', text=label_text)
            texts.extend((label_id, x + radius + 5, y))
        elif label_id is not None:
            self.canvas.itemconfigure(label_id, state='hidden')
        self._location_items[location.key] = [marker, count_id, label_id, segments]
        self.canvas.tag_raise(location.key)

    def _on_device_hover(self, event):
        current = self.canvas.find_withtag('current')
        if not current:
            return
        key = self.canvas.gettags(current[0])[2]
        if key in self._location_by_key:
            location = self._location_by_key[key]
            label, count, statuses = location_summary(location, self.annotations)
            details = label + (f'\n{count} measurements' if count else '')
            self._show_annotation(event, details)
        elif key in self._region_by_key:
            self._show_annotation(event, self._region_by_key[key].label)

    def _update_device_appearance(self, name, selected):
        # Bulk selection redraws once in _update_selection_label.
        pass

    def _target_at(self, x, y):
        transform = self._calculate_transform()
        hits = []
        for key, radius in self._visible_locations.items():
            location = self._location_by_key[key]
            cx, cy = transform(location.x, location.y)
            distance = (x - cx) ** 2 + (y - cy) ** 2
            if distance <= (radius + 4) ** 2:
                hits.append((distance, location))
        if hits:
            return min(hits, key=lambda hit: hit[0])[1]
        regions = [region for region in self._visible_regions
                   if self._bounds(region, transform)[0] <= x <= self._bounds(region, transform)[2]
                   and self._bounds(region, transform)[1] <= y <= self._bounds(region, transform)[3]]
        return min(regions, key=lambda region: (region.bounds[2] - region.bounds[0] + 128)
                   * (region.bounds[3] - region.bounds[1] + 128), default=None)

    def _handle_click(self, x, y, ctrl_held):
        target = self._target_at(x, y)
        if not ctrl_held:
            self.selected_devices.clear()
        if target:
            if ctrl_held and target.names <= self.selected_devices:
                self.selected_devices.difference_update(target.names)
            else:
                self.selected_devices.update(target.names)

    def _on_double_click(self, event):
        target = self._target_at(event.x, event.y)
        self._cancel_rectangle()
        if target is None:
            return 'break'
        if target.key in self._region_by_key:
            left, top, right, bottom = target.bounds
            scale = min(max(1, self.canvas_width - 120) / (right - left + 128),
                        max(1, self.canvas_height - 120) / (bottom - top + 128))
            self._view = (scale, self.canvas_width / 2 + (left + right) * scale / 2,
                          self.canvas_height / 2 - (top + bottom) * scale / 2)
            self._draw_devices()
        else:
            self._zoom_at(event.x, event.y, 2)
        return 'break'

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
        self._draw_devices()
        self.on_select(set(self.selected_devices))

    def _on_arrow_key(self, event):
        result = super()._on_arrow_key(event)
        self._draw_devices()
        return result

    def _on_pan_start(self, event):
        self._context_start = event.x, event.y
        return super()._on_pan_start(event)

    def _on_pan_end(self, event):
        super()._on_pan_end(event)
        self._draw_devices()
        if self._context_start is not None:
            x, y = self._context_start
            if abs(event.x - x) < 5 and abs(event.y - y) < 5:
                target = self._target_at(event.x, event.y)
                if target is None:
                    self.on_context('chip', None, event)
                elif target.key in self._location_by_key:
                    identities = tuple(item.identity for item in target.members)
                    self.on_context('devices', identities, event)
                else:
                    self.on_context('subsites' if target.subsites else 'site',
                                    (target.site, target.subsites) if target.subsites else target.site, event)
        self._context_start = None
        return 'break'
