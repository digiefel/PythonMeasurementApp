"""
Device Selection Dialog

Provides a visual interface for selecting devices on a 2D canvas.
Supports rectangle selection and Ctrl+click for individual device toggling.
"""

import tkinter as tk
from tkinter import ttk


class DeviceSelectionDialog:
    """Dialog for visual device selection on a 2D canvas."""
    
    def __init__(self, parent, devices, prober_position=None, initially_selected=None):
        """
        Args:
            parent: Parent tk window
            devices: List of Device objects with .name, .x, .y attributes
            prober_position: Tuple (x, y) of current prober position, or None
            initially_selected: Set of device names that should be pre-selected
        """
        self.parent = parent
        self.devices = devices
        self.prober_position = prober_position
        self.selected_devices = set(initially_selected) if initially_selected else set()
        self.result = None  # Will be set to the selected device names on OK
        
        # Canvas parameters
        self.canvas_width = 700
        self.canvas_height = 500
        self.margin = 60
        self.point_radius = 8
        self.label_offset = 6
        
        # Rectangle selection state
        self.drag_start = None
        self.selection_rect = None
        
        # Device canvas items mapping
        self.device_items = {}  # device.name -> (oval_id, text_id)
        
        self._create_dialog()
    
    def _create_dialog(self):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Device Selection")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Instructions
        instructions = ttk.Label(
            self.dialog,
            text="Click + drag to select rectangle. Ctrl+Click to toggle individual devices. Selected devices shown in blue.",
            wraplength=680,
            justify="left"
        )
        instructions.pack(padx=10, pady=(10, 5))
        
        # Canvas frame
        canvas_frame = ttk.Frame(self.dialog)
        canvas_frame.pack(padx=10, pady=5, fill="both", expand=True)
        
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
        
        ttk.Button(button_frame, text="Select All", command=self._select_all).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Clear Selection", command=self._clear_selection).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Refresh Prober Position", command=self._refresh_prober).pack(side="left", padx=5)
        
        self.selection_label = ttk.Label(button_frame, text="Selected: 0")
        self.selection_label.pack(side="left", padx=20)
        
        ttk.Button(button_frame, text="Cancel", command=self._cancel).pack(side="right", padx=5)
        ttk.Button(button_frame, text="OK", command=self._ok).pack(side="right", padx=5)
        
        # Bind events
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        
        # Draw devices
        self._draw_devices()
        self._update_selection_label()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def _calculate_transform(self):
        """Calculate transformation from device coordinates to canvas coordinates."""
        if not self.devices:
            return lambda x, y: (self.canvas_width // 2, self.canvas_height // 2)
        
        xs = [d.x for d in self.devices]
        ys = [d.y for d in self.devices]
        
        # Include prober position in bounds if available
        if self.prober_position:
            xs.append(self.prober_position[0])
            ys.append(self.prober_position[1])
        
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
        draw_width = self.canvas_width - 2 * self.margin
        draw_height = self.canvas_height - 2 * self.margin
        
        # Calculate scale (maintain aspect ratio)
        scale_x = draw_width / (max_x - min_x)
        scale_y = draw_height / (max_y - min_y)
        scale = min(scale_x, scale_y)
        
        # Center offset
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        
        def transform(x, y):
            # Transform to canvas coordinates
            # Invert X: more negative device X -> right side of canvas (prober moves right)
            # Invert Y: more positive device Y -> bottom of canvas (prober moves down)
            cx = self.margin + draw_width / 2 - (x - center_x) * scale  # Invert X
            cy = self.margin + draw_height / 2 + (y - center_y) * scale  # Invert Y
            return cx, cy
        
        return transform
    
    def _draw_devices(self):
        """Draw all devices and prober position on canvas."""
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
            cx, cy = transform(device.x, device.y)
            is_selected = device.name in self.selected_devices
            fill_color = "dodgerblue" if is_selected else "black"
            outline_color = "blue" if is_selected else "black"
            
            oval_id = self.canvas.create_oval(
                cx - self.point_radius, cy - self.point_radius,
                cx + self.point_radius, cy + self.point_radius,
                fill=fill_color, outline=outline_color, width=2,
                tags=("device", device.name)
            )
            text_id = self.canvas.create_text(
                cx + self.label_offset, cy - self.label_offset,
                text=device.name, anchor="sw", font=("TkDefaultFont", 8),
                fill="darkblue" if is_selected else "black",
                tags=("device_label", device.name)
            )
            self.device_items[device.name] = (oval_id, text_id)
        
        # Draw prober position (red X)
        if self.prober_position:
            px, py = transform(self.prober_position[0], self.prober_position[1])
            x_size = self.point_radius - 1
            # Draw X shape with two crossing lines
            self.canvas.create_line(
                px - x_size, py - x_size, px + x_size, py + x_size,
                fill="red", width=4, tags="prober"
            )
            self.canvas.create_line(
                px - x_size, py + x_size, px + x_size, py - x_size,
                fill="red", width=4, tags="prober"
            )
            # Label centered below the X
            self.canvas.create_text(
                px, py + x_size + 6,
                text="Prober", anchor="n", font=("TkDefaultFont", 8, "bold"),
                fill="red", tags="prober_label"
            )
    
    def _update_device_appearance(self, device_name, selected):
        """Update the visual appearance of a device."""
        if device_name not in self.device_items:
            return
        oval_id, text_id = self.device_items[device_name]
        fill_color = "dodgerblue" if selected else "black"
        outline_color = "blue" if selected else "black"
        text_color = "darkblue" if selected else "black"
        
        self.canvas.itemconfig(oval_id, fill=fill_color, outline=outline_color)
        self.canvas.itemconfig(text_id, fill=text_color)
    
    def _update_selection_label(self):
        """Update the selection count label."""
        self.selection_label.config(text=f"Selected: {len(self.selected_devices)}")
    
    def _on_mouse_down(self, event):
        """Handle mouse button press."""
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
    
    def _handle_click(self, x, y, ctrl_held):
        """Handle a click at (x, y)."""
        # Find device under cursor
        transform = self._calculate_transform()
        clicked_device = None
        
        for device in self.devices:
            cx, cy = transform(device.x, device.y)
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if dist <= self.point_radius + 4:  # Small tolerance
                clicked_device = device
                break
        
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
        for device in self.devices:
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
