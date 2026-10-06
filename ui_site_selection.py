"""Site selection on a chip map, bounded by actual device coordinates."""

from dataclasses import dataclass

from models import has_position
from ui_device_selection import DeviceSelectionDialog


def device_bounds(devices):
    points = [(device.absolute_x, device.absolute_y) for device in devices if has_position(device)]
    if not points:
        return None
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class SiteMapItem:
    name: str
    x: float | None
    y: float | None
    bounds: tuple | None
    selected_bounds: tuple | None


def site_map_items(sites, subsite_name, device_names):
    selected_names = set(device_names)
    items = []
    for site in sites:
        bounds = device_bounds(device for sub in site.subsites for device in sub.devices)
        selected_bounds = device_bounds(
            device for sub in site.subsites if sub.name == subsite_name
            for device in sub.devices if device.name in selected_names
        )
        x, y = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2) if bounds else (None, None)
        items.append(SiteMapItem(site.name, x, y, bounds, selected_bounds))
    return items


class SiteSelectionDialog(DeviceSelectionDialog):
    TITLE = "Site Selection"
    ITEM_KIND = "site"
    INSTRUCTIONS = (
        "Click a site box, drag to select sites, or Ctrl+Click to toggle. Selected sites are blue. "
        "Outer boxes cover all devices; dashed green boxes cover the selected devices in the chosen subsite."
    )
    SELECT_ALL_TOOLTIP = "Select every site on this chip."
    MANUAL_TOOLTIP = "Select sites whose devices have no known coordinates."

    def __init__(self, parent, sites, subsite_name, device_names, prober_position=None, initially_selected=None):
        items = site_map_items(sites, subsite_name, device_names)
        super().__init__(parent, items, prober_position, initially_selected)

    def _plot_points(self):
        return [point for item in self.devices
                for point in ((item.bounds[0], item.bounds[1]), (item.bounds[2], item.bounds[3]))]

    @staticmethod
    def _canvas_bounds(bounds, transform, padding=4):
        x0, y0 = transform(bounds[0], bounds[1])
        x1, y1 = transform(bounds[2], bounds[3])
        return min(x0, x1) - padding, min(y0, y1) - padding, max(x0, x1) + padding, max(y0, y1) + padding

    def _draw_device(self, item, transform):
        selected = item.name in self.selected_devices
        rect_id = self.canvas.create_rectangle(
            *self._canvas_bounds(item.bounds, transform),
            fill="lightblue" if selected else "gray95",
            outline="blue" if selected else "gray40", width=2,
        )
        if item.selected_bounds is not None:
            self.canvas.create_rectangle(
                *self._canvas_bounds(item.selected_bounds, transform, padding=1),
                outline="forestgreen", width=2, dash=(4, 3),
            )
        x, y = transform(item.x, item.y)
        text_id = self.canvas.create_text(
            x, y, text=item.name, font=("TkDefaultFont", 9, "bold"),
            fill="darkblue" if selected else "black",
        )
        return rect_id, text_id

    def _contains_point(self, item, transform, x, y):
        left, top, right, bottom = self._canvas_bounds(item.bounds, transform)
        return left <= x <= right and top <= y <= bottom

    def _update_device_appearance(self, name, selected):
        if name in self.device_items:
            rect_id, text_id = self.device_items[name]
            self.canvas.itemconfig(rect_id, fill="lightblue" if selected else "gray95",
                                   outline="blue" if selected else "gray40")
            self.canvas.itemconfig(text_id, fill="darkblue" if selected else "black")
