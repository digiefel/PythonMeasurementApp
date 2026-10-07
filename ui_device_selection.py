"""
Device Selection Dialog

Provides a visual interface for selecting devices on a 2D canvas.
Supports rectangle selection, Ctrl+click toggling, zooming, and panning.
"""

import sys
import tkinter as tk
from tkinter import ttk
from tooltip_helper import attach_tooltip
from data_management import STATUS_COLORS


class DeviceSelectionDialog:
    """Dialog for visual device selection on a 2D canvas."""
    TITLE = "Device Selection"
    ITEM_KIND = "device"
    INSTRUCTIONS = "Click + drag to select rectangle. Ctrl+Click to toggle individual devices. Selected devices shown in blue."
    SELECT_ALL_TOOLTIP = "Select every device in this subsite."
    MANUAL_TOOLTIP = "Select devices to position manually. The app asks you to position each one before measuring it."
    
    def __init__(self, parent, devices, prober_position=None, initially_selected=None, annotations=None):
        """
        Args:
            parent: Parent tk window
            devices: List of Device objects with .name, .x, .y attributes
            prober_position: Tuple (x, y) of current prober position, or None
            initially_selected: Set of device names that should be pre-selected
            annotations: Optional name-to-status/details mapping from device notes
        """
        self.parent = parent
        self.devices = [device for device in devices if device.x is not None and device.y is not None]
        self.unpositioned_devices = [device for device in devices if device.x is None or device.y is None]
        self.manual_list = None
        self.prober_position = prober_position
        self.selected_devices = set(initially_selected) if initially_selected else set()
        self.result = None  # Will be set to the selected device names on OK
        self.annotations = annotations or {}
        self._annotation_window = None
        
        # Canvas parameters
        self.canvas_width = 700
        self.canvas_height = 500
        self.margin = 60
        self.point_radius = 8
        self.label_offset = 6
        self._view = None  # (scale, canvas X offset, canvas Y offset)
        self._pan_start = None
        
        # Rectangle selection state
        self.drag_start = None
        self.selection_rect = None
        
        # Device canvas items mapping
        self.device_items = {}  # device.name -> (oval_id, text_id)
        
        self._create_dialog()
    
    def _create_dialog(self):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(self.TITLE)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Instructions
        instructions = ttk.Label(
            self.dialog,
            text=self.INSTRUCTIONS + " Scroll to zoom; right- or middle-drag to pan. Arrow keys pan; Shift moves faster.",
            wraplength=680,
            justify="left"
        )
        instructions.pack(padx=10, pady=(10, 5))

        if self.unpositioned_devices:
            manual_label = ttk.Label(self.dialog, text="Unknown coordinates (manual positioning)")
            manual_frame = ttk.LabelFrame(self.dialog, labelwidget=manual_label)
            manual_frame.pack(padx=10, pady=5, fill="x")
            self.manual_list = tk.Listbox(
                manual_frame, selectmode=tk.MULTIPLE, exportselection=False,
                height=min(6, len(self.unpositioned_devices)),
            )
            scrollbar = ttk.Scrollbar(manual_frame, command=self.manual_list.yview)
            scrollbar.pack(side="right", fill="y")
            self.manual_list.configure(yscrollcommand=scrollbar.set)
            self.manual_list.pack(side="left", fill="x", expand=True)
            for index, device in enumerate(self.unpositioned_devices):
                self.manual_list.insert(tk.END, device.name)
                if device.name in self.selected_devices:
                    self.manual_list.selection_set(index)
            self.manual_list.bind("<<ListboxSelect>>", self._update_manual_selection)
            attach_tooltip(manual_label, self.MANUAL_TOOLTIP)
        
        # Canvas frame
        canvas_frame = ttk.Frame(self.dialog)
        canvas_frame.pack(padx=10, pady=5, fill="both", expand=True)

        navigation = ttk.Frame(canvas_frame)
        navigation.pack(fill="x", pady=(0, 5))
        for text, command in (
            ("Fit View", self._fit_view),
            ("−", lambda: self._zoom_at(self.canvas_width / 2, self.canvas_height / 2, 1 / 1.2)),
            ("+", lambda: self._zoom_at(self.canvas_width / 2, self.canvas_height / 2, 1.2)),
        ):
            ttk.Button(navigation, text=text, command=command).pack(side="left", padx=(0, 5))
        
        self.canvas = tk.Canvas(
            canvas_frame,
            width=self.canvas_width,
            height=self.canvas_height,
            bg="white",
            highlightthickness=1,
            highlightbackground="gray"
        )
        self.canvas.pack(fill="both", expand=True)
        
        # Button frame
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(padx=10, pady=10, fill="x")
        
        select_all_button = ttk.Button(button_frame, text="Select All", command=self._select_all)
        select_all_button.pack(side="left", padx=5)
        attach_tooltip(select_all_button, self.SELECT_ALL_TOOLTIP)
        clear_button = ttk.Button(button_frame, text="Clear Selection", command=self._clear_selection)
        clear_button.pack(side="left", padx=5)
        attach_tooltip(clear_button, f"Clear the {self.ITEM_KIND} selection.")
        refresh_button = self.refresh_button = ttk.Button(button_frame, text="Refresh Prober Position", command=lambda: self._refresh_prober())
        refresh_button.pack(side="left", padx=5)
        attach_tooltip(refresh_button, "Read the current chuck position and update the red marker on the map.")
        
        self.selection_label = ttk.Label(button_frame, text="Selected: 0")
        self.selection_label.pack(side="left", padx=20)
        
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self._cancel)
        cancel_button.pack(side="right", padx=5)
        attach_tooltip(cancel_button, f"Discard your changes and close {self.TITLE}.")
        ok_button = ttk.Button(button_frame, text="OK", command=self._ok)
        ok_button.pack(side="right", padx=5)
        attach_tooltip(ok_button, f"Use the selected {self.ITEM_KIND}s for the next run.")
        
        self._bind_canvas_events()

        # Draw devices
        self._draw_devices()
        self._update_selection_label()

        # Center dialog
        self.dialog.update_idletasks()
        self._fit_view()
        self.canvas.focus_set()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

    def _bind_canvas_events(self):
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.configure(takefocus=True)
        for key in ('Left', 'Right', 'Up', 'Down'):
            self.canvas.bind(f'<{key}>', self._on_arrow_key)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Button-4>", self._on_mouse_wheel)
        self.canvas.bind("<Button-5>", self._on_mouse_wheel)
        for button in (2, 3):
            self.canvas.bind(f"<Button-{button}>", self._on_pan_start)
            self.canvas.bind(f"<B{button}-Motion>", self._on_pan_drag)
            self.canvas.bind(f"<ButtonRelease-{button}>", self._on_pan_end)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Destroy>", lambda event: self._hide_annotation(), add="+")
        self.canvas.tag_bind('device_hover', '<Enter>', self._on_device_hover)
        self.canvas.tag_bind('device_hover', '<Leave>', lambda event: self._hide_annotation())
    
    def _plot_points(self):
        return [(device.x, device.y) for device in self.devices]

    def _fitted_view(self):
        """Fit all device bounds and the prober marker to the current canvas."""
        points = self._plot_points()
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        
        # Include prober position in bounds if available
        if self.prober_position:
            xs.append(self.prober_position[0])
            ys.append(self.prober_position[1])
        if not xs:
            return 1.0, self.canvas_width / 2, self.canvas_height / 2
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Add small margin if all points are at same location
        if max_x == min_x:
            min_x -= 100
            max_x += 100
        if max_y == min_y:
            min_y -= 100
            max_y += 100
        
        # Available drawing area
        draw_width = max(1, self.canvas_width - 2 * self.margin)
        draw_height = max(1, self.canvas_height - 2 * self.margin)
        
        # Calculate scale (maintain aspect ratio)
        scale_x = draw_width / (max_x - min_x)
        scale_y = draw_height / (max_y - min_y)
        scale = min(scale_x, scale_y)
        
        # Center offset
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        
        return scale, self.canvas_width / 2 + center_x * scale, self.canvas_height / 2 - center_y * scale

    def _calculate_transform(self):
        """Use the same viewport for drawing and selection hit testing."""
        if self._view is None:
            self._view = self._fitted_view()
        scale, offset_x, offset_y = self._view
        # Prober axes: negative X goes right; positive Y goes down.
        return lambda x, y: (offset_x - x * scale, offset_y + y * scale)

    def _cancel_rectangle(self):
        if self.selection_rect is not None:
            self.canvas.delete(self.selection_rect)
        self.selection_rect = None
        self.drag_start = None

    def _fit_view(self):
        self._cancel_rectangle()
        self._view = self._fitted_view()
        self._draw_devices()

    def _zoom_at(self, x, y, factor):
        """Zoom around a canvas point, keeping the point under the cursor fixed."""
        self._calculate_transform()
        scale, offset_x, offset_y = self._view
        fit_scale = self._fitted_view()[0]
        new_scale = max(fit_scale / 20, min(fit_scale * 1000, scale * factor))
        ratio = new_scale / scale
        self._cancel_rectangle()
        self._view = new_scale, x + (offset_x - x) * ratio, y + (offset_y - y) * ratio
        self._draw_devices()

    def _on_mouse_wheel(self, event):
        self.canvas.focus_set()
        if event.num == 4:
            steps = 1
        elif event.num == 5:
            steps = -1
        else:
            steps = event.delta if sys.platform == "darwin" else event.delta / 120
        if steps:
            self._zoom_at(event.x, event.y, 1.1 ** max(-10, min(10, steps)))
        return "break"

    def _on_pan_start(self, event):
        self.canvas.focus_set()
        self._cancel_rectangle()
        self._pan_start = event.x, event.y
        self.canvas.configure(cursor="fleur")
        return "break"

    def _pan_by(self, dx, dy):
        self._calculate_transform()
        scale, offset_x, offset_y = self._view
        self._view = scale, offset_x + dx, offset_y + dy
        self._hide_annotation()
        self.canvas.move('map_content', dx, dy)

    def _on_arrow_key(self, event):
        if self._pan_start is not None:
            return 'break'
        self._cancel_rectangle()
        step = 160 if event.state & 0x1 else 40
        # Move the viewport toward the arrow, shifting the content oppositely.
        dx, dy = {'Left': (step, 0), 'Right': (-step, 0),
                  'Up': (0, step), 'Down': (0, -step)}[event.keysym]
        self._pan_by(dx, dy)
        return 'break'

    def _on_pan_drag(self, event):
        if self._pan_start is not None:
            x, y = self._pan_start
            self._pan_by(event.x - x, event.y - y)
            self._pan_start = event.x, event.y
        return "break"

    def _on_pan_end(self, event):
        self._pan_start = None
        self.canvas.configure(cursor="")
        return "break"

    def _on_canvas_resize(self, event):
        if event.width <= 1 or event.height <= 1:
            return
        if (event.width, event.height) == (self.canvas_width, self.canvas_height):
            return
        self._cancel_rectangle()
        if self._view is not None:
            scale, offset_x, offset_y = self._view
            self._view = (scale, offset_x + (event.width - self.canvas_width) / 2,
                          offset_y + (event.height - self.canvas_height) / 2)
        self.canvas_width, self.canvas_height = event.width, event.height
        self._draw_devices()
    
    def _draw_devices(self):
        """Draw all devices and prober position on canvas."""
        self._hide_annotation()
        self.canvas.delete("all")
        self.device_items.clear()
        
        transform = self._calculate_transform()
        
        # Draw axes/grid hint
        self.canvas.create_line(self.margin, self.canvas_height - self.margin,
                                 self.canvas_width - self.margin, self.canvas_height - self.margin,
                                 fill="lightgray", arrow="last")
        self.canvas.create_line(self.margin, self.canvas_height - self.margin,
                                 self.margin, self.margin,
                                 fill="lightgray", arrow="last")
        self.canvas.create_text(self.canvas_width - self.margin + 15, self.canvas_height - self.margin,
                                 text="X", fill="gray")
        self.canvas.create_text(self.margin, self.margin - 15,
                                 text="Y", fill="gray")
        
        # Draw devices
        for device in self.devices:
            self.device_items[device.name] = self._draw_device(device, transform)
        
        # Draw prober position (red X)
        if self.prober_position:
            px, py = transform(self.prober_position[0], self.prober_position[1])
            x_size = self.point_radius - 1
            # Draw X shape with two crossing lines
            self.canvas.create_line(
                px - x_size, py - x_size, px + x_size, py + x_size,
                fill="red", width=4, tags=("map_content", "prober")
            )
            self.canvas.create_line(
                px - x_size, py + x_size, px + x_size, py - x_size,
                fill="red", width=4, tags=("map_content", "prober")
            )
            # Label centered below the X
            self.canvas.create_text(
                px, py + x_size + 6,
                text="Prober", anchor="n", font=("TkDefaultFont", 8, "bold"),
                fill="red", tags=("map_content", "prober_label")
            )
    
    def _draw_device(self, device, transform):
        cx, cy = transform(device.x, device.y)
        selected = device.name in self.selected_devices
        annotation = self.annotations.get(device.name, {})
        status = annotation.get('status', '')
        color = STATUS_COLORS.get(status, 'black')
        oval_id = self.canvas.create_oval(
            cx - self.point_radius, cy - self.point_radius,
            cx + self.point_radius, cy + self.point_radius,
            fill=color if status else ("dodgerblue" if selected else "black"),
            outline="blue" if selected else color, width=3 if selected else 2,
            tags=("map_content", "device", device.name, "device_hover"),
        )
        text_id = self._create_device_label(device, transform) if self._label_visible(device) else None
        return oval_id, text_id

    def _label_visible(self, device):
        return True

    def _create_device_label(self, device, transform):
        cx, cy = transform(device.x, device.y)
        selected = device.name in self.selected_devices
        annotation = self.annotations.get(device.name, {})
        status = annotation.get('status', '')
        text_id = self.canvas.create_text(
            cx + self.label_offset, cy - self.label_offset,
            text=getattr(device, 'display_name', device.name) + (f' [{status}]' if status else '')
                 + (' *' if annotation.get('has_notes') else ''),
            anchor="sw", font=("TkDefaultFont", 8),
            fill="darkblue" if selected else "black", tags=("map_content", "device_label", device.name, "device_hover"),
        )
        return text_id

    def _on_device_hover(self, event):
        current = self.canvas.find_withtag('current')
        if current:
            name = self.canvas.gettags(current[0])[2]
            details = self.annotations.get(name, {}).get('details')
            if details:
                self._show_annotation(event, details)

    def _show_annotation(self, event, text):
        self._hide_annotation()
        self._annotation_window = window = tk.Toplevel(self.canvas)
        window.wm_overrideredirect(True)
        window.geometry(f'+{event.x_root + 12}+{event.y_root + 12}')
        tk.Label(window, text=text, justify='left', wraplength=400,
                 background='#ffffe0', foreground='black', relief='solid', borderwidth=1, padx=5, pady=5).pack()

    def _hide_annotation(self):
        if self._annotation_window is not None:
            self._annotation_window.destroy()
            self._annotation_window = None

    def _contains_point(self, device, transform, x, y):
        cx, cy = transform(device.x, device.y)
        return ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= self.point_radius + 4

    def _update_device_appearance(self, device_name, selected):
        """Update the visual appearance of a device."""
        if device_name not in self.device_items:
            return
        oval_id, text_id = self.device_items[device_name]
        status = self.annotations.get(device_name, {}).get('status', '')
        color = STATUS_COLORS.get(status, 'black')
        fill_color = color if status else ("dodgerblue" if selected else "black")
        outline_color = "blue" if selected else color
        text_color = "darkblue" if selected else "black"
        
        self.canvas.itemconfig(oval_id, fill=fill_color, outline=outline_color, width=3 if selected else 2)
        if text_id is not None:
            self.canvas.itemconfig(text_id, fill=text_color)
    
    def _update_selection_label(self):
        """Update the selection count label."""
        if self.manual_list is not None:
            self.manual_list.selection_clear(0, tk.END)
            for index, device in enumerate(self.unpositioned_devices):
                if device.name in self.selected_devices:
                    self.manual_list.selection_set(index)
        self.selection_label.config(text=f"Selected: {len(self.selected_devices)}")

    def _update_manual_selection(self, event=None):
        selected_indices = set(self.manual_list.curselection())
        for index, device in enumerate(self.unpositioned_devices):
            if index in selected_indices:
                self.selected_devices.add(device.name)
            else:
                self.selected_devices.discard(device.name)
        self._update_selection_label()
    
    def _on_mouse_down(self, event):
        """Handle mouse button press."""
        self.canvas.focus_set()
        if self._pan_start is not None:
            return
        self.drag_start = (event.x, event.y)
        self.selection_rect = None
    
    def _on_mouse_drag(self, event):
        """Handle mouse drag for rectangle selection."""
        if self.drag_start is None:
            return
        
        # Remove old rectangle
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
        
        # Draw new rectangle
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        self.selection_rect = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="blue", width=2, dash=(4, 4),
            tags="selection_rect"
        )
    
    def _on_mouse_up(self, event):
        """Handle mouse button release."""
        if self.drag_start is None:
            return
        
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        
        # Check if it was a click (small movement) or a drag
        is_click = abs(x1 - x0) < 5 and abs(y1 - y0) < 5
        ctrl_held = event.state & 0x4  # Check Ctrl key
        
        if is_click:
            # Single click - toggle device under cursor or handle Ctrl+click
            self._handle_click(event.x, event.y, ctrl_held)
        else:
            # Rectangle selection
            self._handle_rectangle_selection(x0, y0, x1, y1, ctrl_held)
        
        # Clean up
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
            self.selection_rect = None
        self.drag_start = None
        self._update_selection_label()
    
    def _device_at(self, x, y):
        transform = self._calculate_transform()
        candidates = [device for device in reversed(self.devices) if self._contains_point(device, transform, x, y)]
        return min(candidates, key=lambda device: (transform(device.x, device.y)[0] - x) ** 2
                   + (transform(device.x, device.y)[1] - y) ** 2, default=None)

    def _handle_click(self, x, y, ctrl_held):
        """Select the nearest marker, with the topmost marker winning shared positions."""
        clicked_device = self._device_at(x, y)
        
        if clicked_device:
            if ctrl_held:
                # Toggle individual device
                if clicked_device.name in self.selected_devices:
                    self.selected_devices.discard(clicked_device.name)
                    self._update_device_appearance(clicked_device.name, False)
                else:
                    self.selected_devices.add(clicked_device.name)
                    self._update_device_appearance(clicked_device.name, True)
            else:
                # Non-ctrl click: select only this device
                for name in list(self.selected_devices):
                    self.selected_devices.discard(name)
                    self._update_device_appearance(name, False)
                self.selected_devices.add(clicked_device.name)
                self._update_device_appearance(clicked_device.name, True)
        else:
            # Clicked on empty space without ctrl - clear selection
            if not ctrl_held:
                for name in list(self.selected_devices):
                    self.selected_devices.discard(name)
                    self._update_device_appearance(name, False)
    
    def _handle_rectangle_selection(self, x0, y0, x1, y1, ctrl_held):
        """Handle rectangle selection."""
        # Normalize coordinates
        rect_left = min(x0, x1)
        rect_right = max(x0, x1)
        rect_top = min(y0, y1)
        rect_bottom = max(y0, y1)
        
        transform = self._calculate_transform()
        
        # If not ctrl, clear existing selection first
        if not ctrl_held:
            for name in list(self.selected_devices):
                self.selected_devices.discard(name)
                self._update_device_appearance(name, False)
        
        # Select devices within rectangle
        for device in self.devices:
            cx, cy = transform(device.x, device.y)
            if rect_left <= cx <= rect_right and rect_top <= cy <= rect_bottom:
                self.selected_devices.add(device.name)
                self._update_device_appearance(device.name, True)
    
    def _select_all(self):
        """Select all devices."""
        for device in self.devices + self.unpositioned_devices:
            self.selected_devices.add(device.name)
            self._update_device_appearance(device.name, True)
        self._update_selection_label()
    
    def _clear_selection(self):
        """Clear all selections."""
        for name in list(self.selected_devices):
            self.selected_devices.discard(name)
            self._update_device_appearance(name, False)
        self._update_selection_label()
    
    def _refresh_prober(self):
        """Placeholder for refreshing prober position - will be overridden."""
        pass  # Will be set by caller
    
    def set_refresh_callback(self, callback):
        """Set callback for refreshing prober position."""
        self._refresh_prober = callback
    
    def update_prober_position(self, position):
        """Update the prober position and redraw."""
        self.prober_position = position
        self._draw_devices()
    
    def _ok(self):
        """Confirm selection and close."""
        self.result = self.selected_devices.copy()
        self.dialog.destroy()
    
    def _cancel(self):
        """Cancel and close without saving."""
        self.result = None
        self.dialog.destroy()
    
    def show(self):
        """Show dialog and wait for result."""
        self.dialog.wait_window()
        return self.result
