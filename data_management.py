"""Folder-backed measurement browsing, device assessments, and identity correction."""

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import tempfile
import os

IDENTITY_KEYS = ('Chip', 'Site', 'Subsite', 'Device')
STATUSES = ('', 'Good', 'OK', 'Bad')
STATUS_COLORS = {'Good': 'forestgreen', 'OK': 'gold', 'Bad': 'firebrick'}
_IDENTITY_LINE = re.compile(rb'^# (Chip|Site|Subsite|Device):[^\r\n]*')


def validate_name(value):
    if (not value or value in ('.', '..') or '/' in value or '\\' in value
            or any(ord(char) < 32 for char in value)):
        raise ValueError('Names must be nonempty single directory names without slashes or control characters.')
    return value


@dataclass(frozen=True, order=True)
class Identity:
    chip: str
    site: str
    subsite: str
    device: str

    @property
    def parts(self):
        return self.chip, self.site, self.subsite, self.device

    @property
    def label(self):
        return ' / '.join(self.parts)

    def directory(self, root):
        for part in self.parts:
            validate_name(part)
        path = Path(root).joinpath(*self.parts)
        ensure_local(root, path)
        return path

    def corrected(self, changes):
        return Identity(*(validate_name(changes.get(key) or old)
                          for key, old in zip(IDENTITY_KEYS, self.parts)))


def ensure_local(root, path):
    """Do not follow folder symlinks outside (or within) the data directory."""
    root, path = Path(root).absolute(), Path(path).absolute()
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f'Symbolic links cannot be edited: {current}')


def read_metadata(path):
    metadata = {}
    with Path(path).open('r', encoding='utf-8-sig') as stream:
        for line in stream:
            if not line.startswith('#'):
                break
            # Only top-level fields: procedure parameters have indented keys.
            match = re.match(r'^# ([A-Za-z_]+):\s*(.*)', line)
            if match:
                metadata[match[1]] = match[2].strip()
    return metadata


def metadata_identity(metadata):
    if all(metadata.get(key) for key in IDENTITY_KEYS):
        return Identity(*(metadata[key] for key in IDENTITY_KEYS))
    return None


def read_notes(root, identity):
    path = identity.directory(root) / 'notes.txt'
    ensure_local(root, path)
    if not path.exists():
        return '', ''
    text = path.read_text(encoding='utf-8')
    first, separator, rest = text.partition('\n')
    if first.startswith('Status: ') and first[8:].strip() in STATUSES:
        return first[8:].strip(), rest.removeprefix('\n') if separator else ''
    return '', text  # Existing arbitrary notes are never interpreted as a status.


def write_notes(root, identity, status, text):
    if status not in STATUSES:
        raise ValueError('Status must be Good, OK, Bad, or cleared.')
    directory = identity.directory(root)
    path = directory / 'notes.txt'
    ensure_local(root, path)
    if not path.exists() and not status and not text:
        return
    directory.mkdir(parents=True, exist_ok=True)
    contents = f'Status: {status}\n\n{text}'
    handle, temporary = tempfile.mkstemp(prefix='.notes-', dir=directory)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='') as stream:
            stream.write(contents)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(frozen=True)
class Measurement:
    identity: Identity
    name: str
    files: tuple[Path, ...]
    metadata: dict
    warnings: tuple[str, ...] = ()

    @property
    def data_files(self):
        return tuple(path for path in self.files if path.suffix.lower() == '.csv')

    @property
    def plot_files(self):
        return tuple(path for path in self.files if path.suffix.lower() == '.png')

    @property
    def timestamp(self):
        match = re.search(r'\d{8}_\d{6}', self.name)
        return self.metadata.get('Timestamp', match[0] if match else '')


def measurement_base(path):
    stem = path.stem
    if path.suffix.lower() == '.png':
        return stem.removesuffix('_plot')
    # WGFMU sampling writes several combination CSVs and one shared plot.
    return re.sub(r'_c\d+$', '', stem)


def chips_in(root):
    root = Path(root)
    if not root.exists():
        return []
    return sorted((path.name for path in root.iterdir()
                   if path.is_dir() and not path.is_symlink() and not path.name.startswith('.')), key=str.casefold)


def scan_chip(root, chip):
    """Return device folders and measurement groups without reading numeric data."""
    chip_dir = Path(root) / validate_name(chip)
    ensure_local(root, chip_dir)
    identities, measurements = [], []
    if not chip_dir.exists():
        return identities, measurements
    for site in sorted(chip_dir.iterdir()):
        if not site.is_dir() or site.is_symlink():
            continue
        for subsite in sorted(site.iterdir()):
            if not subsite.is_dir() or subsite.is_symlink():
                continue
            for device in sorted(subsite.iterdir()):
                if not device.is_dir() or device.is_symlink():
                    continue
                identity = Identity(chip, site.name, subsite.name, device.name)
                identities.append(identity)
                groups = {}
                for path in sorted(device.iterdir()):
                    if path.is_file() and not path.is_symlink() and path.suffix.lower() in ('.csv', '.png'):
                        groups.setdefault(measurement_base(path), []).append(path)
                for name, files in groups.items():
                    metadata, warnings = {}, []
                    for path in files:
                        if path.suffix.lower() != '.csv':
                            continue
                        try:
                            header = read_metadata(path)
                            metadata = metadata or header
                            saved = metadata_identity(header)
                            if saved != identity:
                                warnings.append(f'{path.name}\nFolder: {identity.label}\nHeader: '
                                                + (saved.label if saved else 'identity metadata missing'))
                        except (OSError, UnicodeError) as exc:
                            warnings.append(f'{path.name}: {exc}')
                    measurements.append(Measurement(identity, name, tuple(files), metadata, tuple(warnings)))
    measurements.sort(key=lambda item: (item.timestamp, item.name), reverse=True)
    return identities, measurements


def layout_devices(sites, chip):
    return {Identity(chip, site.name, sub.name, device.name): device
            for site in sites for sub in site.subsites for device in sub.devices}


def selection_annotations(root, chip, sites, subsite_name, device_names):
    """Assessments belong to a physical chip/site device, independently of CSV layout tags."""
    if not chip:
        return {}
    result = {}
    for name in device_names:
        assessments, details, has_notes = [], [], False
        for site in sites:
            if not any(sub.name == subsite_name and any(device.name == name for device in sub.devices)
                       for sub in site.subsites):
                continue
            identity = Identity(chip, site.name, subsite_name, name)
            status, notes = read_notes(root, identity)
            assessments.append(status)
            has_notes |= bool(notes)
            details.append(identity.label + (f'\nStatus: {status}' if status else '\nStatus: unassigned')
                           + (f'\n{notes}' if notes else ''))
        if has_notes or any(assessments):
            distinct = set(assessments)
            result[name] = {'status': next(iter(distinct)) if len(distinct) == 1 else 'Mixed',
                            'has_notes': has_notes, 'details': '\n\n'.join(details)}
    return result


def missing_geometry(layout, identities):
    """A complete map includes layout devices with no measurements yet."""
    from models import has_position
    return [identity for identity in sorted(set(layout) | set(identities))
            if identity not in layout or not has_position(layout[identity])]


def rewrite_csv_identity(source, destination, identity):
    """Change top-level identity comments; preserve all numeric bytes and other metadata."""
    with Path(source).open('rb') as reader, Path(destination).open('wb') as writer:
        header, seen, bom = [], set(), b''
        line = reader.readline()
        if line.startswith(b'\xef\xbb\xbf'):
            bom, line = b'\xef\xbb\xbf', line[3:]
        newline = b'\r\n' if line.endswith(b'\r\n') else b'\n'
        while line.startswith(b'#'):
            match = _IDENTITY_LINE.match(line)
            if match:
                key = match[1].decode()
                value = identity.parts[IDENTITY_KEYS.index(key)]
                line = f'# {key}: {value}'.encode('utf-8') + newline
                seen.add(key)
            header.append(line)
            line = reader.readline()
        writer.write(bom)
        for line_header in header:
            writer.write(line_header if line_header.endswith(b'\n') else line_header + newline)
        for key, value in zip(IDENTITY_KEYS, identity.parts):
            if key not in seen:
                writer.write(f'# {key}: {value}'.encode('utf-8') + newline)
        writer.write(line)
        shutil.copyfileobj(reader, writer)


@dataclass(frozen=True)
class FileCorrection:
    source: Path
    destination: Path
    identity: Identity
    signature: tuple

    @property
    def is_csv(self):
        return self.source.suffix.lower() == '.csv'


def file_signature(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def corrected_filename(path, old, new, header_identity=None):
    for candidate in (old, header_identity):
        if candidate:
            prefix = '_'.join(candidate.parts) + '_'
            if path.name.startswith(prefix):
                return '_'.join(new.parts) + '_' + path.name[len(prefix):]
    # Standard timestamps allow recovery even when folder, header, and filename disagree.
    match = re.search(r'_\d{8}_\d{6}(?=_|\.)', path.name)
    if match:
        return '_'.join(new.parts) + path.name[match.start():]
    return path.name


def plan_correction(root, measurements=(), folders=(), changes=None):
    """Folder scopes are relative chip/site/subsite/device prefixes; blank fields retain identity."""
    root = Path(root).absolute()
    changes = changes or {}
    for key, value in changes.items():
        if key not in IDENTITY_KEYS:
            raise ValueError(f'Unknown identity field: {key}')
        if value:
            validate_name(value)
    files = {}
    for measurement in measurements:
        saved = metadata_identity(measurement.metadata)
        for path in measurement.files:
            files[path.absolute()] = saved
    for folder in folders:
        parts = tuple(folder)
        if not 1 <= len(parts) <= 4:
            raise ValueError('Choose a chip, site, subsite, or device folder.')
        for part in parts:
            validate_name(part)
        source_dir = root.joinpath(*parts)
        ensure_local(root, source_dir)
        # Include notes and other device-folder contents for whole-folder corrections.
        for path in source_dir.rglob('*'):
            ensure_local(root, path)
            if path.is_file():
                files.setdefault(path.absolute(), None)
    plan, destinations = [], set()
    for source, saved in sorted(files.items()):
        ensure_local(root, source)
        relative = source.relative_to(root)
        if len(relative.parts) < 5:
            raise ValueError(f'File is outside a device directory: {relative}')
        old = Identity(*relative.parts[:4])
        new = old.corrected(changes)
        destination = new.directory(root).joinpath(*relative.parts[4:-1],
                                                   corrected_filename(source, old, new, saved))
        ensure_local(root, destination)
        if destination in destinations:
            raise ValueError(f'Two files would have the same destination: {destination}')
        if destination != source and destination.exists():
            raise FileExistsError(f'Destination already exists: {destination}')
        destinations.add(destination)
        plan.append(FileCorrection(source, destination, new, file_signature(source)))
    return tuple(plan)


def apply_correction(root, plan):
    """Stage originals and rewritten headers, then install; roll back a failed batch."""
    root = Path(root).absolute()
    if not plan:
        return
    for item in plan:
        ensure_local(root, item.source)
        ensure_local(root, item.destination)
        if file_signature(item.source) != item.signature:
            raise ValueError(f'File changed since preview; refresh first: {item.source}')
        if item.destination != item.source and item.destination.exists():
            raise FileExistsError(f'Destination already exists: {item.destination}')
    staging = Path(tempfile.mkdtemp(prefix='.assignment-', dir=root))
    installed, removed, backups = [], [], []
    created_directories = set()
    cleanup = True
    try:
        for index, item in enumerate(plan):
            backup, output = staging / f'{index}.original', staging / f'{index}.corrected'
            shutil.copy2(item.source, backup)
            backups.append(backup)
            if item.is_csv:
                rewrite_csv_identity(backup, output, item.identity)
                shutil.copystat(backup, output)
            else:
                shutil.copy2(backup, output)
        for item in plan:
            if file_signature(item.source) != item.signature:
                raise ValueError(f'File changed during correction: {item.source}')
        for index, item in enumerate(plan):
            ensure_local(root, item.source)
            ensure_local(root, item.destination)
            if file_signature(item.source) != item.signature:
                raise ValueError(f'File changed during correction: {item.source}')
            parent = item.destination.parent
            while not parent.exists():
                created_directories.add(parent)
                parent = parent.parent
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            if item.destination == item.source:
                os.replace(staging / f'{index}.corrected', item.destination)
            else:
                # Exclusive creation also works on network drives without hard-link support.
                with item.destination.open('xb') as writer:
                    installed.append(index)
                    with (staging / f'{index}.corrected').open('rb') as reader:
                        shutil.copyfileobj(reader, writer)
                shutil.copystat(staging / f'{index}.corrected', item.destination)
                continue
            installed.append(index)
        for index, item in enumerate(plan):
            if item.source != item.destination:
                if file_signature(item.source) != item.signature:
                    raise ValueError(f'File changed during correction: {item.source}')
                item.source.unlink()
                removed.append(index)
    except Exception as exc:
        try:
            for index in removed:
                shutil.copy2(backups[index], plan[index].source)
            for index in reversed(installed):
                item = plan[index]
                if item.source == item.destination:
                    shutil.copy2(backups[index], item.source)
                else:
                    item.destination.unlink()
            for directory in sorted(created_directories, key=lambda path: len(path.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        except Exception as rollback_error:
            cleanup = False
            raise RuntimeError(f'{exc}\nRecovery failed: {rollback_error}\nOriginal backups: {staging}') from exc
        raise
    finally:
        if cleanup:
            shutil.rmtree(staging)
    # Only remove directories that became empty; partial corrections retain their notes.
    for item in plan:
        parent = item.source.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
