"""Geometry and compact summaries for the whole-sample viewer."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property


@dataclass(frozen=True)
class Location:
    key: str
    members: tuple
    x: float
    y: float

    @cached_property
    def names(self):
        return frozenset(item.name for item in self.members)


@dataclass(frozen=True)
class Region:
    key: str
    site: str
    subsites: tuple
    members: tuple
    bounds: tuple
    spacing: float

    @cached_property
    def names(self):
        return frozenset(item.name for item in self.members)

    @property
    def label(self):
        return ', '.join(self.subsites) if self.subsites else self.site


def _region(key, site, subsites, members):
    points = {(item.x, item.y) for item in members}
    xs, ys = zip(*points)
    gaps = []
    for axis in (0, 1):
        values = sorted({point[axis] for point in points})
        gaps.extend(b - a for a, b in zip(values, values[1:]) if b > a)
    return Region(key, site, tuple(subsites), tuple(members),
                  (min(xs), min(ys), max(xs), max(ys)), min(gaps, default=160))


def build_geometry(items):
    """Merge exact coordinates; combine subsite outlines that share locations."""
    by_position, by_site = defaultdict(list), defaultdict(list)
    for item in items:
        if item.x is not None and item.y is not None:
            by_position[item.x, item.y].append(item)
            by_site[item.identity.site].append(item)
    locations = [Location(f'location:{index}', tuple(members), x, y)
                 for index, ((x, y), members) in enumerate(by_position.items())]
    sites, subsites = [], []
    for site, members in by_site.items():
        sites.append(_region(f'site:{site}', site, (), members))
        groups = []
        by_subsite = defaultdict(list)
        for item in members:
            by_subsite[item.identity.subsite].append(item)
        for name, devices in by_subsite.items():
            points = {(item.x, item.y) for item in devices}
            connected = [group for group in groups if group[2] & points]
            names, joined = [name], list(devices)
            for group in connected:
                groups.remove(group)
                names.extend(group[0])
                joined.extend(group[1])
                points.update(group[2])
            groups.append((names, joined, points))
        for index, (names, devices, _) in enumerate(groups):
            subsites.append(_region(f'subsite:{site}:{index}', site, sorted(names), devices))
    return locations, sites, subsites


def date_text(timestamp):
    """Accept the application's compact timestamps and ISO timestamps."""
    if not timestamp:
        return ''
    for pattern in ('%Y%m%d_%H%M%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(timestamp[:19] if '-' in timestamp else timestamp[:15], pattern).date().isoformat()
        except ValueError:
            pass
    return ''


def location_summary(location, annotations):
    names = ', '.join(dict.fromkeys(item.identity.device for item in location.members))
    types = ', '.join(dict.fromkeys(item.identity.subsite for item in location.members))
    values = [annotations.get(item.name, {}) for item in location.members]
    dates = [date_text(value.get('last_measurement', '')) for value in values]
    latest = max(dates, default='')
    notes = any(value.get('has_notes') for value in values)
    count = sum(value.get('measurement_count', 0) for value in values)
    statuses = tuple(dict.fromkeys(value.get('status', '') for value in values))
    label = f'{names}\n{types}' + (f'\n{latest}' if latest else '') + ('  ▤' if notes else '')
    return label, count, statuses
