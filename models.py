import csv
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


class DeviceCsvError(ValueError):
    """Raised when a devices CSV cannot be compiled into a device tree."""

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


class Device:
    def __init__(
        self,
        name: str,
        x: float,
        y: float,
        tags: Optional[Iterable[str]] = None,
        absolute_x: Optional[float] = None,
        absolute_y: Optional[float] = None,
        source_rows: Optional[Iterable[int]] = None,
    ):
        self.name = name
        self.x = x
        self.y = y
        self.tags = set(tags or [])
        self.absolute_x = x if absolute_x is None else absolute_x
        self.absolute_y = y if absolute_y is None else absolute_y
        self.source_rows = tuple(source_rows or ())


class Subsite:
    def __init__(
        self,
        name: str,
        devices: Optional[List[Device]] = None,
        x: float = 0.0,
        y: float = 0.0,
        tags: Optional[Iterable[str]] = None,
        absolute_x: Optional[float] = None,
        absolute_y: Optional[float] = None,
        source_rows: Optional[Iterable[int]] = None,
    ):
        self.name = name
        self.devices = devices or []
        self.x = x
        self.y = y
        self.tags = set(tags or [])
        self.absolute_x = x if absolute_x is None else absolute_x
        self.absolute_y = y if absolute_y is None else absolute_y
        self.source_rows = tuple(source_rows or ())


class Site:
    def __init__(
        self,
        name: str,
        subsites: Optional[List[Subsite]] = None,
        x: float = 0.0,
        y: float = 0.0,
        tags: Optional[Iterable[str]] = None,
        source_rows: Optional[Iterable[int]] = None,
    ):
        self.name = name
        self.subsites = subsites or []
        self.x = x
        self.y = y
        self.tags = set(tags or [])
        self.source_rows = tuple(source_rows or ())


@dataclass
class CsvDefinition:
    kind: str
    row: int
    site: str
    subsite: str
    device: str
    x: float
    y: float
    tags: set[str] = field(default_factory=set)

    @property
    def coords(self) -> tuple[float, float]:
        return self.x, self.y


@dataclass
class MergedDefinition:
    kind: str
    key: tuple[Optional[str], Optional[str], Optional[str]]
    x: float
    y: float
    tags: set[str]
    rows: list[int]

    @property
    def coords(self) -> tuple[float, float]:
        return self.x, self.y


@dataclass
class ResolvedDefinition:
    x: float
    y: float
    tags: set[str]
    rows: list[int]
    source: Optional[MergedDefinition]

    @property
    def coords(self) -> tuple[float, float]:
        return self.x, self.y


@dataclass
class DeviceCsvCompilation:
    csv_path: str
    sites: List[Site]
    definitions: list[CsvDefinition]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)
    shared_positions: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def load_devices_csv(csv_path: str) -> List[Site]:
    compilation = compile_devices_csv(csv_path, raise_on_error=True)
    return compilation.sites


def compile_devices_csv(csv_path: str, raise_on_error: bool = False) -> DeviceCsvCompilation:
    compiler = DeviceCsvCompiler(csv_path)
    compilation = compiler.compile()
    if raise_on_error and compilation.errors:
        raise DeviceCsvError(compilation.errors)
    return compilation


class DeviceCsvCompiler:
    REQUIRED_COLUMNS = ("Site", "Subsite", "Device", "X", "Y")
    OPTIONAL_COLUMNS = ("Tags",)

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.definitions: list[CsvDefinition] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.decisions: list[str] = []
        self.overrides: list[str] = []
        self.shared_positions: list[str] = []
        self.definitions_by_path: OrderedDict[tuple[Optional[str], Optional[str], Optional[str]], MergedDefinition] = OrderedDict()

    def compile(self) -> DeviceCsvCompilation:
        self._read_definitions()
        if self.definitions:
            self._merge_definitions()
        sites = [] if self.errors else self._build_tree()
        stats = self._stats(sites)
        return DeviceCsvCompilation(
            csv_path=self.csv_path,
            sites=sites,
            definitions=self.definitions,
            errors=self.errors,
            warnings=self.warnings,
            decisions=self.decisions,
            overrides=self.overrides,
            shared_positions=self.shared_positions,
            stats=stats,
        )

    def _read_definitions(self):
        try:
            with open(self.csv_path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                columns = self._map_columns(reader.fieldnames or [])
                if self.errors:
                    return
                for row_num, row in enumerate(reader, start=2):
                    self._read_row(row_num, row, columns)
        except FileNotFoundError:
            self.errors.append(f"File not found: {self.csv_path}")
        except OSError as exc:
            self.errors.append(f"Could not read {self.csv_path}: {exc}")

    def _map_columns(self, fieldnames: list[str]) -> dict[str, str]:
        normalized = {name.strip().lower(): name for name in fieldnames if name is not None}
        missing = [col for col in self.REQUIRED_COLUMNS if col.lower() not in normalized]
        if missing:
            self.errors.append(
                "Missing required column(s): " + ", ".join(missing)
            )
        return {
            col: normalized[col.lower()]
            for col in (*self.REQUIRED_COLUMNS, *self.OPTIONAL_COLUMNS)
            if col.lower() in normalized
        }

    def _read_row(self, row_num: int, row: dict, columns: dict[str, str]):
        site = self._cell(row, columns, "Site")
        subsite = self._cell(row, columns, "Subsite")
        device = self._cell(row, columns, "Device")
        x_raw = self._cell(row, columns, "X")
        y_raw = self._cell(row, columns, "Y")
        tags = self._parse_tags(self._cell(row, columns, "Tags"))

        if not any((site, subsite, device, x_raw, y_raw, tags)):
            return

        if device and not subsite:
            self.errors.append(
                f"Row {row_num}: Device '{device}' has no Subsite. Devices must belong to a subsite."
            )
            return
        if not any((site, subsite, device)):
            self.errors.append(f"Row {row_num}: X/Y coordinates were provided without a Site, Subsite, or Device.")
            return

        coords = self._parse_coords(row_num, x_raw, y_raw)
        if coords is None:
            return
        x, y = coords

        if site and not subsite and not device:
            kind = "site"
        elif not site and subsite and not device:
            kind = "subsite_template"
        elif site and subsite and not device:
            kind = "subsite"
        elif not site and subsite and device:
            kind = "device_template"
        elif site and subsite and device:
            kind = "device"
        else:
            self.errors.append(f"Row {row_num}: Unsupported row shape.")
            return

        self.definitions.append(CsvDefinition(kind, row_num, site, subsite, device, x, y, tags))

    @staticmethod
    def _cell(row: dict, columns: dict[str, str], name: str) -> str:
        column = columns.get(name)
        if column is None:
            return ""
        value = row.get(column, "")
        return "" if value is None else str(value).strip()

    @staticmethod
    def _parse_tags(value: str) -> set[str]:
        if not value:
            return set()
        return {part.strip() for part in value.split(";") if part.strip()}

    def _parse_coords(self, row_num: int, x_raw: str, y_raw: str) -> Optional[tuple[float, float]]:
        if not x_raw or not y_raw:
            self.errors.append(f"Row {row_num}: X and Y are required.")
            return None
        try:
            return -float(x_raw), -float(y_raw)
        except ValueError:
            self.errors.append(f"Row {row_num}: X and Y must be numeric. Got X={x_raw!r}, Y={y_raw!r}.")
            return None

    def _merge_definitions(self):
        for definition in self.definitions:
            self._upsert(self._definition_path(definition), definition)

    def _upsert(self, path: tuple[Optional[str], Optional[str], Optional[str]], definition: CsvDefinition):
        current = self.definitions_by_path.get(path)
        if current is None:
            self.definitions_by_path[path] = MergedDefinition(
                kind=definition.kind,
                key=path,
                x=definition.x,
                y=definition.y,
                tags=set(definition.tags),
                rows=[definition.row],
            )
            self.decisions.append(
                f"Row {definition.row}: remembered {self._kind_label(definition.kind)} {self._key_label(definition.kind, path)} at {self._coords(definition.coords)}"
            )
            return

        if current.coords != definition.coords:
            self.errors.append(
                f"Rows {current.rows[0]} and {definition.row}: conflicting {self._kind_label(definition.kind)} "
                f"{self._key_label(definition.kind, path)} coordinates "
                f"{self._coords(current.coords)} vs {self._coords(definition.coords)}."
            )
            return

        current.tags.update(definition.tags)
        current.rows.append(definition.row)
        self.decisions.append(
            f"Row {definition.row}: merged duplicate {self._kind_label(definition.kind)} "
            f"{self._key_label(definition.kind, path)} with row {current.rows[0]}"
        )

    @staticmethod
    def _definition_path(definition: CsvDefinition) -> tuple[Optional[str], Optional[str], Optional[str]]:
        return (
            definition.site or None,
            definition.subsite or None,
            definition.device or None,
        )

    def _build_tree(self) -> list[Site]:
        site_names = self._concrete_site_names()
        subsite_names_by_site = self._concrete_subsite_names_by_site()

        sites = []
        for site_name in site_names:
            site = self._make_site(site_name)
            for subsite_name in subsite_names_by_site.get(site_name, {}):
                subsite = self._make_subsite(site, subsite_name)
                self._add_devices(site, subsite)
                site.subsites.append(subsite)
            sites.append(site)

        self._record_unused_templates(sites)
        self._record_shared_positions(sites)
        return sites

    def _concrete_site_names(self) -> OrderedDict[str, None]:
        names = OrderedDict()
        for site_name, _subsite_name, _device_name in self.definitions_by_path:
            if site_name is not None:
                names.setdefault(site_name, None)
        return names

    def _concrete_subsite_names_by_site(self) -> dict[str, OrderedDict[str, None]]:
        names_by_site: dict[str, OrderedDict[str, None]] = defaultdict(OrderedDict)
        for site_name, subsite_name, _device_name in self.definitions_by_path:
            if site_name is not None and subsite_name is not None:
                names_by_site[site_name].setdefault(subsite_name, None)
        return names_by_site

    def _make_site(self, site_name: str) -> Site:
        resolved = self._resolve_path((site_name, None, None), f"site {site_name}")
        if resolved.source is None:
            self.decisions.append(f"Created site {site_name} at default position (0, 0)")
            return Site(site_name, x=0.0, y=0.0)
        self.decisions.append(
            f"Created site {site_name} at {self._coords(resolved.coords)} from row(s) {self._rows(resolved.rows)}"
        )
        return Site(site_name, x=resolved.x, y=resolved.y, tags=resolved.tags, source_rows=resolved.rows)

    def _make_subsite(self, site: Site, subsite_name: str) -> Subsite:
        path = (site.name, subsite_name, None)
        resolved = self._resolve_path(path, f"{site.name}/{subsite_name}")
        source_text = (
            f"from row(s) {self._rows(resolved.rows)}"
            if resolved.source is not None
            else "at default position"
        )
        self.decisions.append(
            f"Created subsite {site.name}/{subsite_name} at {self._coords(resolved.coords)} {source_text}"
        )
        return Subsite(
            subsite_name,
            x=resolved.x,
            y=resolved.y,
            tags=resolved.tags,
            absolute_x=site.x + resolved.x,
            absolute_y=site.y + resolved.y,
            source_rows=resolved.rows,
        )

    def _add_devices(self, site: Site, subsite: Subsite):
        for device_name in self._device_names(site.name, subsite.name):
            path = (site.name, subsite.name, device_name)
            resolved = self._resolve_path(path, f"{site.name}/{subsite.name}/{device_name}")
            self.decisions.append(
                f"Created device {site.name}/{subsite.name}/{device_name} at "
                f"{self._coords(resolved.coords)} from row(s) {self._rows(resolved.rows)}"
            )
            device = Device(
                device_name,
                resolved.x,
                resolved.y,
                tags=resolved.tags,
                absolute_x=subsite.absolute_x + resolved.x,
                absolute_y=subsite.absolute_y + resolved.y,
                source_rows=resolved.rows,
            )
            subsite.devices.append(device)

    def _device_names(self, site_name: str, subsite_name: str) -> OrderedDict[str, None]:
        names = OrderedDict()
        for site, subsite, device in self.definitions_by_path:
            if site is None and subsite == subsite_name and device is not None:
                names.setdefault(device, None)
        for site, subsite, device in self.definitions_by_path:
            if site == site_name and subsite == subsite_name and device is not None:
                names.setdefault(device, None)
        return names

    def _resolve_path(self, path: tuple[str, Optional[str], Optional[str]], label: str) -> ResolvedDefinition:
        candidates = self._matching_definitions(path)
        if not candidates:
            return ResolvedDefinition(0.0, 0.0, set(), [], None)

        tags = set()
        rows = []
        for definition in candidates:
            tags.update(definition.tags)
            rows.extend(definition.rows)

        chosen = candidates[-1]
        if len(candidates) > 1 and candidates[0].coords != chosen.coords:
            self.overrides.append(
                f"{label}: row(s) {self._rows(chosen.rows)} override "
                f"row(s) {self._rows(candidates[0].rows)} "
                f"from {self._coords(candidates[0].coords)} to {self._coords(chosen.coords)}"
            )
        return ResolvedDefinition(chosen.x, chosen.y, tags, rows, chosen)

    def _matching_definitions(self, path: tuple[str, Optional[str], Optional[str]]) -> list[MergedDefinition]:
        site_name, subsite_name, device_name = path
        paths = []
        if subsite_name is None:
            paths.append((site_name, None, None))
        elif device_name is None:
            paths.extend([
                (None, subsite_name, None),
                (site_name, subsite_name, None),
            ])
        else:
            paths.extend([
                (None, subsite_name, device_name),
                (site_name, subsite_name, device_name),
            ])
        return [self.definitions_by_path[p] for p in paths if p in self.definitions_by_path]

    def _record_unused_templates(self, sites: list[Site]):
        concrete_subsite_names = {subsite.name for site in sites for subsite in site.subsites}
        for path, definition in self.definitions_by_path.items():
            site_name, subsite_name, device_name = path
            if site_name is None and subsite_name is not None and device_name is None and subsite_name not in concrete_subsite_names:
                self.warnings.append(
                    f"Reusable subsite '{subsite_name}' from row(s) {self._rows(definition.rows)} did not match any concrete subsite."
                )
            if site_name is None and subsite_name is not None and device_name is not None and subsite_name not in concrete_subsite_names:
                self.warnings.append(
                    f"Reusable device '{subsite_name}/{device_name}' from row(s) {self._rows(definition.rows)} did not match any concrete subsite."
                )

    def _record_shared_positions(self, sites: list[Site]):
        positions = defaultdict(list)
        for site in sites:
            for subsite in site.subsites:
                for device in subsite.devices:
                    positions[(device.absolute_x, device.absolute_y)].append(
                        f"{site.name}/{subsite.name}/{device.name}"
                    )
        for coords, paths in positions.items():
            if len(paths) > 1:
                self.shared_positions.append(
                    f"{len(paths)} measurement targets share absolute position {self._coords(coords)}: "
                    + ", ".join(paths)
                )

    def _stats(self, sites: list[Site]) -> dict[str, int]:
        subsite_count = sum(len(site.subsites) for site in sites)
        device_count = sum(len(subsite.devices) for site in sites for subsite in site.subsites)
        return {
            "rows": len(self.definitions),
            "sites": len(sites),
            "subsites": subsite_count,
            "devices": device_count,
            "site_rows": self._definition_count("site"),
            "subsite_template_rows": self._definition_count("subsite_template"),
            "subsite_rows": self._definition_count("subsite"),
            "device_template_rows": self._definition_count("device_template"),
            "device_rows": self._definition_count("device"),
            "overrides": len(self.overrides),
            "warnings": len(self.warnings),
            "shared_positions": len(self.shared_positions),
            "errors": len(self.errors),
        }

    def _definition_count(self, kind: str) -> int:
        return sum(1 for definition in self.definitions if definition.kind == kind)

    @staticmethod
    def _kind_label(kind: str) -> str:
        if kind == "subsite_template":
            return "reusable subsite"
        if kind == "device_template":
            return "reusable device"
        return kind.replace("_", " ")

    @staticmethod
    def _key_label(kind: str, key: tuple[Optional[str], Optional[str], Optional[str]]) -> str:
        site_name, subsite_name, device_name = key
        if kind == "site":
            return site_name or ""
        if kind == "subsite_template":
            return subsite_name or ""
        if kind == "subsite":
            return f"{site_name}/{subsite_name}"
        if kind == "device_template":
            return f"{subsite_name}/{device_name}"
        if kind == "device":
            return f"{site_name}/{subsite_name}/{device_name}"
        return "/".join(part or "" for part in key)

    @staticmethod
    def _coords(coords: tuple[float, float]) -> str:
        return f"({coords[0]:g}, {coords[1]:g})"

    @staticmethod
    def _rows(rows: Iterable[int]) -> str:
        return ", ".join(str(row) for row in rows)
