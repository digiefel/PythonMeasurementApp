"""Whole-sample data browser, plot gallery, and device notes."""

from pathlib import Path
from types import SimpleNamespace
from collections import defaultdict
import math
import re
from datetime import datetime
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from data_management import (
    IDENTITY_KEYS, STATUSES, STATUS_COLORS, chips_in, scan_chip,
    layout_devices, missing_geometry, read_notes, write_notes, plan_correction, apply_correction,
)
from ui_sample_view import SampleMap
from models import has_position
from sample_map_model import date_text
from tooltip_helper import attach_tooltip
from measurement_query import MeasurementQuery, find_devices
from ui_measurement_filter import MeasurementFilterDialog


def open_file(path):
    """Open a saved artifact with the platform's associated application."""
    path = str(Path(path).absolute())
    if sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    elif os.name == 'nt':
        os.startfile(path)
    else:
        subprocess.Popen(['xdg-open', path])


class DataManagementWindow:
    PAGE_SIZE = 30
    MIN_CARD_WIDTH = 180

    def __init__(self, parent, data_root, sites, chip='', is_running=lambda: False):
        self.data_root, self.sites = Path(data_root).absolute(), sites
        self.is_running = is_running
        self.chip = chip
        self.measurements, self.identities, self.selected_identities = [], [], set()
        self.gallery_items, self.gallery_selection, self.cards, self.photos = [], set(), {}, []
        self.gallery_anchor, self.page = None, 0
        self.map = self.device_list = None
        self._notes_identity, self._notes_job = None, None
        self._notes_dirty = self._loading_notes = False
        self.query = MeasurementQuery()
        self._find_job = None
        self._warned = set()
        self._sash_set = False
        self._gallery_width = 360
        self._gallery_columns = 1
        self._gallery_resize_job = None
        self._thumbnail_size = None
        self._gallery_sources, self._pictures = {}, {}
        self._captions = {}
        self.window = tk.Toplevel(parent)
        self.window.title('Data Management')
        self.window.geometry('1250x800')
        self.window.minsize(900, 600)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self._build()
        self._refresh_chips()
        self.refresh()
        self.window.after(100, self._maximize)

    def _maximize(self):
        try:
            self.window.state('zoomed')
        except tk.TclError:
            self.window.attributes('-zoomed', True)
        self.window.after_idle(self._fit_initial_map)

    def _fit_initial_map(self):
        if self.map and not self.device_search.get().strip():
            self.map._fit_view()

    def _build(self):
        toolbar = ttk.Frame(self.window)
        toolbar.pack(fill='x', padx=8, pady=6)
        ttk.Label(toolbar, text=str(self.data_root)).pack(side='left')
        ttk.Button(toolbar, text='Refresh', command=self.refresh).pack(side='right')
        panes = self.panes = ttk.Panedwindow(self.window, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=1)
        panes.bind('<Configure>', self._position_panes)

        header = ttk.Frame(left)
        header.pack(fill='x')
        ttk.Label(header, text='Chip').pack(side='left', padx=(4, 4))
        self.chip_button = ttk.Button(header, text=self.chip or 'Select…', command=self._show_chip_picker)
        self.chip_button.pack(side='left', pady=2)
        picker = self.chip_picker = tk.Toplevel(self.window)
        picker.withdraw()
        picker.transient(self.window)
        picker.overrideredirect(True)
        self.search = tk.StringVar()
        self.chip_search = ttk.Entry(picker, textvariable=self.search, width=24)
        self.chip_search.pack(fill='x', padx=4, pady=4)
        self.chip_search.bind('<Return>', self._choose_chip)
        self.chip_list = tk.Listbox(picker, height=6, width=24, exportselection=False)
        self.chip_list.pack(fill='x', padx=4, pady=(0, 4))
        self.search.trace_add('write', lambda *_: self._filter_chips())
        self.chip_list.bind('<<ListboxSelect>>', self._choose_chip)
        self.chip_list.bind('<Return>', self._choose_chip)
        picker.bind('<Escape>', lambda event: picker.withdraw())
        picker.bind('<FocusOut>', lambda event: picker.after_idle(self._dismiss_chip_picker))
        self.window.bind('<ButtonPress>', lambda event: picker.withdraw(), add='+')
        finder = ttk.Frame(header)
        finder.pack(side='left', padx=8, pady=2)
        ttk.Label(finder, text='Find').pack(side='left', padx=(0, 4))
        self.device_search = tk.StringVar()
        name_entry = ttk.Entry(finder, textvariable=self.device_search, width=26)
        name_entry.pack(side='left')
        self.find_count = ttk.Label(finder)
        self.find_count.pack(side='left', padx=4)
        attach_tooltip(name_entry, 'Find a site, subsite, or device by name. Exact names match first.\n'
                       'Search moves the map and highlights matches without changing your selection.')
        self.device_search.trace_add('write', self._schedule_find)
        name_entry.bind('<Return>', lambda event: self._find_devices())
        self.view_toggle = ttk.Button(header, text='List View', command=self._toggle_view)
        self.view_toggle.pack(side='right', padx=4, pady=2)
        self.view_frame = ttk.Frame(left)
        self.view_frame.pack(fill='both', expand=True)

        self.notes_frame = ttk.LabelFrame(right, text='Device Notes')
        self.notes_frame.pack(fill='x', padx=5, pady=5)
        self.notes_identity_label = ttk.Label(self.notes_frame, wraplength=320)
        self.notes_identity_label.pack(fill='x', padx=5, pady=4)
        self.notes_member = tk.StringVar()
        self.notes_member_box = ttk.Combobox(self.notes_frame, textvariable=self.notes_member, state='readonly')
        self.notes_member_box.bind('<<ComboboxSelected>>', self._choose_notes_member)

        controls = ttk.Frame(self.notes_frame)
        controls.pack(fill='x', padx=5, pady=4)
        ttk.Label(controls, text='Status').pack(side='left')
        self.status = tk.StringVar()
        self.status_box = ttk.Combobox(controls, textvariable=self.status, values=STATUSES, width=10, state='disabled')
        self.status_box.pack(side='left', padx=6)
        self.status_box.bind('<<ComboboxSelected>>', self._status_changed)
        attach_tooltip(self.status_box, 'Good: green. OK: yellow. Bad: red.\nStatus and notes save automatically.')
        self.clear_status_button = ttk.Button(controls, text='Clear', command=self._clear_status, state='disabled')
        self.clear_status_button.pack(side='left')
        self.save_label = ttk.Label(controls)
        self.save_label.pack(side='right')
        self.notes = tk.Text(self.notes_frame, width=1, height=3, wrap='word', undo=True, state='disabled')
        self.notes.pack(fill='x', padx=5, pady=(0, 5))
        self.notes.bind('<<Modified>>', self._notes_changed)
        self.notes.bind('<FocusOut>', lambda event: self.save_notes())

        gallery_header = self.gallery_header = ttk.Frame(right)
        gallery_header.pack(fill='x', padx=5, pady=3)
        self.gallery_label = ttk.Label(gallery_header, text='Measurements', justify='left')
        self.gallery_label.pack(side='left')
        ttk.Button(gallery_header, text='›', width=2, command=lambda: self._change_page(1)).pack(side='right')
        self.page_label = ttk.Label(gallery_header)
        self.page_label.pack(side='right', padx=4)
        ttk.Button(gallery_header, text='‹', width=2, command=lambda: self._change_page(-1)).pack(side='right')
        gallery_actions = ttk.Frame(right)
        gallery_actions.pack(side='bottom', fill='x', padx=5, pady=5)
        self.filter_button = ttk.Button(gallery_actions, text='Find / Filter…', command=self._open_filter)
        self.filter_button.pack(side='left')
        ttk.Button(gallery_actions, text='Correct Assignment…', command=self._correct_measurements).pack(side='right')
        self.gallery_canvas = tk.Canvas(right, highlightthickness=0, background='#f4f5f7')
        scroll = ttk.Scrollbar(right, orient='vertical', command=self.gallery_canvas.yview)
        scroll.pack(side='right', fill='y')
        self.gallery_canvas.pack(fill='both', expand=True, padx=5, pady=5)
        self.gallery_canvas.configure(yscrollcommand=scroll.set)
        self.gallery_frame = ttk.Frame(self.gallery_canvas)
        self.gallery_window = self.gallery_canvas.create_window(0, 0, window=self.gallery_frame, anchor='nw')
        self.gallery_frame.bind('<Configure>', lambda event: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox('all')))
        self.gallery_canvas.bind('<Configure>', self._resize_gallery)
        self.gallery_canvas.bind('<MouseWheel>', self._scroll_gallery)
        self.gallery_canvas.bind('<Button-4>', self._scroll_gallery)
        self.gallery_canvas.bind('<Button-5>', self._scroll_gallery)
        self.gallery_canvas.bind('<Control-a>', self._select_all_measurements)
        self.window.bind('<Control-f>', lambda event: self._open_filter())
        if sys.platform == 'darwin':
            self.gallery_canvas.bind('<Command-a>', self._select_all_measurements)
            self.window.bind('<Command-f>', lambda event: self._open_filter())

    def _resize_gallery(self, event):
        if event.width <= 1:
            return
        self._gallery_width = event.width
        self.gallery_canvas.itemconfigure(self.gallery_window, width=event.width)
        self.gallery_label.configure(wraplength=max(80, event.width - 150))
        self._layout_gallery()
        if self._gallery_resize_job:
            self.window.after_cancel(self._gallery_resize_job)
        self._gallery_resize_job = self.window.after(120, self._resize_thumbnails)

    def _layout_gallery(self):
        columns = max(1, self._gallery_width // self.MIN_CARD_WIDTH)
        for column in range(max(columns, self._gallery_columns)):
            self.gallery_frame.columnconfigure(column, weight=1 if column < columns else 0,
                                               uniform='gallery' if column < columns else '')
        self._gallery_columns = columns
        width = max(1, self._gallery_width // columns - 6)
        for order, (index, card) in enumerate(self.cards.items()):
            card.grid(row=order // columns, column=order % columns, sticky='nw', padx=1, pady=1)
            for label in self._captions[index]:
                label.configure(wraplength=width)

    def _resize_thumbnails(self):
        self._gallery_resize_job = None
        width = max(1, self._gallery_width // self._gallery_columns - 6)
        if width == self._thumbnail_size:
            return
        self._thumbnail_size = width
        self.photos = []
        for index, source in self._gallery_sources.items():
            height = max(1, round(source.height * width / source.width))
            thumbnail = source.resize((width, height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumbnail, master=self.window)
            self.photos.append(photo)
            self._pictures[index].configure(image=photo)

    def _position_panes(self, event):
        if not self._sash_set and event.width > 1:
            self._sash_set = True
            self.panes.sashpos(0, event.width * 2 // 3)

    def _schedule_find(self, *_):
        if self._find_job:
            self.window.after_cancel(self._find_job)
        self._find_job = self.window.after(200, self._find_devices)

    def _find_devices(self):
        if self._find_job:
            self.window.after_cancel(self._find_job)
            self._find_job = None
        text = self.device_search.get().strip()
        matches = find_devices(self.all_identities, text)
        keys = {self._key(identity) for identity in matches}
        self.find_count.configure(text=str(len(matches)) if text else '')
        if self.map:
            self.map.focus_matches(keys)
        if self.device_list:
            self.device_list.tag_configure('found', background='#fff0c2')
            for identity in self.all_identities:
                key = self._key(identity)
                status = self.annotations[key]['status']
                self.device_list.item(key, tags=(status, 'found') if identity in matches else (status,))
            if matches:
                self.device_list.see(self._key(sorted(matches)[0]))

    def _open_filter(self):
        if self.save_notes():
            MeasurementFilterDialog(self.window, self.query, self.measurements, self._apply_query)
        return 'break'

    def _apply_query(self, query):
        if not self.save_notes():
            return False
        self.query = query
        self._filter_gallery()
        return True

    def _filter_gallery(self):
        self.gallery_items = [item for item in self.measurements
                              if (not self.selected_identities or item.identity in self.selected_identities)
                              and (not self.query.active or self.query.matches(item, self.annotations.get(self._key(item.identity), {})))]
        self.gallery_selection.clear()
        self.gallery_anchor, self.page = None, 0
        self.filter_button.configure(text='Find / Filter ●' if self.query.active else 'Find / Filter…')
        self._render_gallery()
        self._warn_mismatches()

    def _refresh_chips(self):
        self.chips = chips_in(self.data_root)
        if self.chip and self.chip not in self.chips:
            self.chips.append(self.chip)
        self.chips.sort(key=str.casefold)
        self._filter_chips()

    def _show_chip_picker(self):
        self.search.set('')
        self.chip_picker.geometry(f'+{self.chip_button.winfo_rootx()}+{self.chip_button.winfo_rooty() + self.chip_button.winfo_height()}')
        self.chip_picker.deiconify()
        self.chip_picker.lift()
        self.chip_search.focus_set()

    def _dismiss_chip_picker(self):
        focus = self.chip_picker.focus_get()
        if focus is None or focus.winfo_toplevel() != self.chip_picker:
            self.chip_picker.withdraw()

    def _filter_chips(self):
        self.visible_chips = [chip for chip in self.chips if self.search.get().casefold() in chip.casefold()]
        self.chip_list.delete(0, 'end')
        for index, chip in enumerate(self.visible_chips):
            self.chip_list.insert('end', chip)
            if chip == self.chip:
                self.chip_list.selection_set(index)
        if len(self.visible_chips) == 1:
            self.chip_list.selection_set(0)
        self.chip_button.configure(text=self.chip or 'Select…')

    def _choose_chip(self, event=None):
        selected = self.chip_list.curselection()
        if selected:
            if not self.save_notes():
                self._filter_chips()
                return
            chip = self.visible_chips[selected[0]]
            self.chip_picker.withdraw()
            if chip != self.chip:
                self.chip = chip
                self.selected_identities.clear()
                self.refresh()

    def refresh(self):
        if not self.save_notes():
            return
        try:
            self._refresh_chips()
            if not self.chip:
                self.chip = self.chips[0] if self.chips else ''
                self._filter_chips()
            self.identities, self.measurements = scan_chip(self.data_root, self.chip) if self.chip else ([], [])
            self.layout = layout_devices(self.sites, self.chip) if self.chip else {}
            self.all_identities = sorted(set(self.layout) | set(self.identities))
            self.selected_identities.intersection_update(self.all_identities)
            self.missing = missing_geometry(self.layout, self.identities)
            self.annotations = {}
            history = defaultdict(list)
            for measurement in self.measurements:
                history[measurement.identity].append(measurement)
            for identity in self.all_identities:
                status, notes = read_notes(self.data_root, identity)
                self.annotations[self._key(identity)] = {
                    **self._annotation(identity, status, notes),
                    'measurement_count': len(history[identity]),
                    'last_measurement': max((date_text(item.timestamp) for item in history[identity]), default=''),
                }
            self._show_view(as_list=not any(has_position(device) for device in self.layout.values()))
            self._selection_changed({self._key(identity) for identity in self.selected_identities}, force=True)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror('Data Management', str(exc), parent=self.window)

    @staticmethod
    def _key(identity):
        return '/'.join(identity.parts[1:])

    @staticmethod
    def _annotation(identity, status, notes):
        return {'status': status, 'has_notes': bool(notes), 'notes': notes,
                'details': identity.label + (f'\nStatus: {status}' if status else '') + (f'\n\n{notes}' if notes else '')}

    def _show_view(self, as_list=False):
        for child in self.view_frame.winfo_children():
            child.destroy()
        self.map = self.device_list = None
        drawable = any(has_position(device) for device in self.layout.values())
        self.view_toggle.configure(text='Map View' if as_list else 'List View', state='normal' if drawable else 'disabled')
        if as_list:
            self.device_list = ttk.Treeview(self.view_frame, columns=('site', 'subsite', 'device', 'status'), show='headings', selectmode='extended')
            for column in ('site', 'subsite', 'device', 'status'):
                self.device_list.heading(column, text=column.title())
                self.device_list.column(column, width=110, stretch=True)
            for status, color in STATUS_COLORS.items():
                self.device_list.tag_configure(status, foreground=color)
            scroll = ttk.Scrollbar(self.view_frame, command=self.device_list.yview)
            scroll.pack(side='right', fill='y')
            self.device_list.configure(yscrollcommand=scroll.set)
            self.device_list.pack(fill='both', expand=True)
            for identity in self.all_identities:
                key = self._key(identity)
                status = self.annotations[key]['status']
                self.device_list.insert('', 'end', iid=key, values=(*identity.parts[1:], status), tags=(status,))
            self.device_list.selection_set(*(self._key(identity) for identity in self.selected_identities))
            self.device_list.bind('<<TreeviewSelect>>', lambda event: self._selection_changed(set(self.device_list.selection())))
            self.device_list.bind('<Button-3>', self._list_menu)
            self.device_list.bind('<Button-2>', self._list_menu)
        else:
            items = []
            for identity in self.all_identities:
                device = self.layout.get(identity)
                x, y = (device.absolute_x, device.absolute_y) if device and has_position(device) else (None, None)
                items.append(SimpleNamespace(name=self._key(identity), display_name=f'{identity.subsite}/{identity.device}',
                                             identity=identity, x=x, y=y))
            self.map = SampleMap(self.view_frame, items, self.annotations,
                                 {self._key(identity) for identity in self.selected_identities},
                                 self._selection_changed, self._map_menu)
        self.view_frame.after_idle(self._find_devices)

    def _toggle_view(self):
        if self.save_notes():
            self._show_view(as_list=self.map is not None)

    def _selection_changed(self, keys, force=False):
        if not self.save_notes():
            # Preserve the previous selection if its notes could not be saved.
            previous = {self._key(identity) for identity in self.selected_identities}
            if self.map:
                self.map.selected_devices = previous
                self.map._draw_devices()
            if self.device_list:
                self.device_list.selection_set(*previous)
            return
        selected = {identity for identity in self.all_identities if self._key(identity) in keys}
        if not force and selected == self.selected_identities and self._notes_identity is not None:
            return
        try:
            positions = [self.layout.get(identity) for identity in selected]
            merged = (len(selected) > 1 and all(device and has_position(device) for device in positions)
                      and len({(device.absolute_x, device.absolute_y) for device in positions}) == 1)
            self._notes_members = {self._key(identity): identity for identity in sorted(selected)} if merged else {}
            if merged:
                self.notes_member_box.configure(values=list(self._notes_members))
                self.notes_member.set(next(iter(self._notes_members)))
                self.notes_member_box.pack(fill='x', padx=5, pady=(0, 4), before=self.notes)
            else:
                self.notes_member_box.pack_forget()
            self._load_notes(next(iter(self._notes_members.values())) if merged
                             else next(iter(selected)) if len(selected) == 1 else None)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror('Could not read device notes', str(exc), parent=self.window)
            return
        self.selected_identities = selected
        self._filter_gallery()

    def _choose_notes_member(self, event=None):
        if self.save_notes():
            self._load_notes(self._notes_members[self.notes_member.get()])
        elif self._notes_identity:
            self.notes_member.set(self._key(self._notes_identity))

    def _load_notes(self, identity):
        status, notes = read_notes(self.data_root, identity) if identity else ('', '')
        self._loading_notes = True
        if identity:
            self.notes_frame.pack(fill='x', padx=5, pady=4, before=self.gallery_header)
        else:
            self.notes_frame.pack_forget()
        self._notes_identity = identity
        self.notes_identity_label.configure(text=identity.label if identity else '')
        self.notes.configure(state='normal')
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', notes)
        self.notes.edit_reset()
        self.notes.edit_modified(False)
        self.notes.configure(state='normal' if identity else 'disabled')
        self.status.set(status)
        self.status_box.configure(state='readonly' if identity else 'disabled')
        self.clear_status_button.configure(state='normal' if identity else 'disabled')
        self.save_label.configure(text='')
        self._notes_dirty = self._loading_notes = False

    def _notes_changed(self, event=None):
        if self.notes.edit_modified():
            self.notes.edit_modified(False)
            if not self._loading_notes and self._notes_identity:
                self._schedule_save()

    def _status_changed(self, event=None):
        self._notes_dirty = True
        self.save_notes()

    def _clear_status(self):
        self.status.set('')
        self._status_changed()

    def _schedule_save(self):
        self._notes_dirty = True
        self.save_label.configure(text='Saving…')
        if self._notes_job:
            self.window.after_cancel(self._notes_job)
        self._notes_job = self.window.after(600, self.save_notes)

    def save_notes(self):
        if self._notes_job:
            self.window.after_cancel(self._notes_job)
            self._notes_job = None
        if not self._notes_dirty or not self._notes_identity:
            return True
        identity = self._notes_identity
        try:
            text = self.notes.get('1.0', 'end-1c')
            write_notes(self.data_root, identity, self.status.get(), text)
            key = self._key(identity)
            self.annotations.setdefault(key, {}).update(self._annotation(identity, self.status.get(), text))
            if self.map:
                self.map._draw_devices()
            if self.device_list:
                self.device_list.item(key, values=(*identity.parts[1:], self.status.get()), tags=(self.status.get(),))
            self._notes_dirty = False
            self.save_label.configure(text='')
            return True
        except (OSError, ValueError, UnicodeError) as exc:
            self.save_label.configure(text='Not saved')
            messagebox.showerror('Could not save device notes', str(exc), parent=self.window)
            return False

    def _warn_mismatches(self):
        messages = []
        for item in self.gallery_items:
            for warning in item.warnings:
                key = (item.identity, warning)
                if key not in self._warned:
                    messages.append(warning)
                    self._warned.add(key)
        if messages:
            WarningPopup(self.window, messages)

    def _render_gallery(self):
        if self._gallery_resize_job:
            self.window.after_cancel(self._gallery_resize_job)
            self._gallery_resize_job = None
        for child in self.gallery_frame.winfo_children():
            child.destroy()
        self.cards, self.photos, self._captions = {}, [], {}
        self._gallery_sources, self._pictures = {}, {}
        self._thumbnail_size = None
        pages = max(1, math.ceil(len(self.gallery_items) / self.PAGE_SIZE))
        self.page = min(self.page, pages - 1)
        self.page_label.configure(text=f'{self.page + 1} / {pages}')
        self.gallery_label.configure(text=f'{len(self.gallery_items)} measurements · {len(self.gallery_selection)} selected')
        first = self.page * self.PAGE_SIZE
        for index in range(first, min(len(self.gallery_items), first + self.PAGE_SIZE)):
            item = self.gallery_items[index]
            card = tk.Frame(self.gallery_frame, background='white', highlightthickness=1, highlightbackground='gray85')
            self.cards[index] = card
            source = None
            if item.plot_files:
                try:
                    with Image.open(item.plot_files[0]) as original:
                        original.thumbnail((480, 320), Image.Resampling.LANCZOS)
                        source = self._gallery_sources[index] = original.copy()
                except (OSError, ValueError):
                    pass
            title = item.metadata.get('Procedure', item.name)
            # Standard filenames repeat identity and timestamp; keep their procedure suffix.
            if 'Procedure' not in item.metadata:
                title = re.sub(r'^.*?\d{8}_\d{6}_?', '', title)
            timestamp = item.timestamp
            if timestamp:
                try:
                    timestamp = datetime.strptime(timestamp[:15], '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
            display_date = date_text(item.timestamp)
            if display_date and len(timestamp) >= 16:
                display_date += ' ' + timestamp[11:16]
            title_label = tk.Label(card, text=title + (' ⚠' if item.warnings else ''),
                                   anchor='w', justify='left', wraplength=220,
                                   font=('TkDefaultFont', 8), background='white', foreground='gray30', padx=0, pady=0)
            title_label.pack(fill='x', padx=1)
            picture = self._pictures[index] = tk.Label(card, text='' if source else 'No plot',
                               background='white', foreground='gray45', borderwidth=0, padx=0, pady=0)
            picture.pack(fill='x', padx=1)
            caption = tk.Frame(card, background='white')
            caption.pack(fill='x', padx=1)
            date_label = tk.Label(caption, text=display_date, anchor='w',
                                 font=('TkDefaultFont', 8), background='white', foreground='gray30', padx=0, pady=0)
            date_label.pack(side='left')
            device_label = tk.Label(caption, text=item.identity.device, anchor='e', width=1,
                                   font=('TkDefaultFont', 8), background='white', foreground='gray30', padx=0, pady=0)
            device_label.pack(side='right', fill='x', expand=True)
            labels = [title_label, date_label, device_label]
            self._captions[index] = [title_label]
            detail = '\n'.join(filter(None, (title, timestamp, item.identity.label, *item.warnings)))
            for widget in (card, picture, caption, *labels):
                attach_tooltip(widget, detail)
                widget.bind('<Button-1>', lambda event, i=index: self._gallery_click(i, event))
                widget.bind('<Double-Button-1>', lambda event, i=index: self._gallery_open(i, event))
                widget.bind('<Button-3>', lambda event, i=index: self._gallery_menu(i, event))
                widget.bind('<Button-2>', lambda event, i=index: self._gallery_menu(i, event))
                widget.bind('<MouseWheel>', self._scroll_gallery)
                widget.bind('<Button-4>', self._scroll_gallery)
                widget.bind('<Button-5>', self._scroll_gallery)
                widget.bind('<Control-a>', self._select_all_measurements)
                widget.bind('<Control-f>', lambda event: self._open_filter())
                if sys.platform == 'darwin':
                    widget.bind('<Command-Button-1>', lambda event, i=index: self._gallery_click(i, event, additive=True))
                    widget.bind('<Command-a>', self._select_all_measurements)
                    widget.bind('<Command-f>', lambda event: self._open_filter())
        if not self.gallery_items:
            ttk.Label(self.gallery_frame, text='No saved measurements for this selection.').grid(padx=10, pady=20)
        self._layout_gallery()
        self._resize_thumbnails()
        self.gallery_canvas.yview_moveto(0)
        self._paint_gallery_selection()

    def _scroll_gallery(self, event):
        if event.num in (4, 5):
            amount = -1 if event.num == 4 else 1
        else:
            amount = -int(event.delta if sys.platform == 'darwin' else event.delta / 120)
        self.gallery_canvas.yview_scroll(amount, 'units')
        return 'break'

    def _gallery_click(self, index, event, additive=False):
        if not self.save_notes():
            return
        self.gallery_canvas.focus_set()
        ctrl, shift = additive or bool(event.state & 0x4), bool(event.state & 0x1)
        if shift and self.gallery_anchor is not None:
            selected = set(range(min(index, self.gallery_anchor), max(index, self.gallery_anchor) + 1))
            self.gallery_selection = self.gallery_selection | selected if ctrl else selected
        elif ctrl:
            self.gallery_selection.symmetric_difference_update({index})
            self.gallery_anchor = index
        else:
            self.gallery_selection = {index}
            self.gallery_anchor = index
        self._paint_gallery_selection()

    def _gallery_open(self, index, event=None):
        if not self.save_notes():
            return 'break'
        self.gallery_selection = {index}
        self.gallery_anchor = index
        self._paint_gallery_selection()
        self._open_artifacts(self.gallery_items[index].plot_files)
        return 'break'

    def _select_all_measurements(self, event=None):
        if self.save_notes():
            self.gallery_selection = set(range(len(self.gallery_items)))
            self._paint_gallery_selection()
        return 'break'

    def _paint_gallery_selection(self):
        for index, card in self.cards.items():
            card.configure(highlightbackground='dodgerblue' if index in self.gallery_selection else 'gray85',
                           highlightthickness=2 if index in self.gallery_selection else 1)
        self.gallery_label.configure(text=f'{len(self.gallery_items)} measurements · {len(self.gallery_selection)} selected')

    def _change_page(self, step):
        pages = max(1, math.ceil(len(self.gallery_items) / self.PAGE_SIZE))
        if self.save_notes():
            self.page = max(0, min(pages - 1, self.page + step))
            self._render_gallery()

    def _open_artifacts(self, paths):
        if not self.save_notes():
            return
        try:
            for path in paths:
                open_file(path)
        except OSError as exc:
            messagebox.showerror('Open file', str(exc), parent=self.window)

    def _gallery_menu(self, index, event):
        if not self.save_notes():
            return
        if index not in self.gallery_selection:
            self.gallery_selection = {index}
            self.gallery_anchor = index
            self._paint_gallery_selection()
        items = [self.gallery_items[i] for i in sorted(self.gallery_selection)]
        menu = tk.Menu(self.window, tearoff=False)
        data = [path for item in items for path in item.data_files]
        plots = [path for item in items for path in item.plot_files]
        menu.add_command(label='Open Data', command=lambda: self._open_artifacts(data), state='normal' if data else 'disabled')
        menu.add_command(label='Open Plot', command=lambda: self._open_artifacts(plots), state='normal' if plots else 'disabled')
        menu.add_separator()
        menu.add_command(label='Correct Assignment…', command=self._correct_measurements)
        if any(item.warnings for item in items):
            menu.add_command(label='Show Warning…', command=lambda: WarningPopup(self.window, [warning for item in items for warning in item.warnings]))
        self._popup(menu, event)

    @staticmethod
    def _popup(menu, event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _list_menu(self, event):
        key = self.device_list.identify_row(event.y)
        identity = next((identity for identity in self.all_identities if self._key(identity) == key), None)
        if identity:
            self._map_menu('device', identity, event)

    def _map_menu(self, scope, value, event):
        identities = value if scope == 'devices' else (value,) if scope == 'device' else ()
        if not identities or not self.save_notes():
            return
        menu = tk.Menu(self.window, tearoff=False)
        for identity in identities:
            menu.add_command(label=f'Notes / Tag: {identity.subsite}/{identity.device}',
                             command=lambda identity=identity: self._select_notes_identity(identity))
        self._popup(menu, event)

    def _select_notes_identity(self, identity):
        if not self.save_notes():
            return
        self.notes_member.set(self._key(identity))
        self._load_notes(identity)

    def _correct_measurements(self):
        self._correct(measurements=[self.gallery_items[index] for index in sorted(self.gallery_selection)])

    def _correct(self, measurements=()):
        if not self.save_notes():
            return
        if not measurements:
            messagebox.showinfo('Correct Assignment', 'Select measurements first.', parent=self.window)
            return
        if self.is_running():
            messagebox.showinfo('Correct Assignment', 'Wait for the measurement run to finish before correcting saved files.', parent=self.window)
            return
        CorrectionDialog(self, measurements)

    def close(self):
        if not self.save_notes():
            return False
        if self._gallery_resize_job:
            self.window.after_cancel(self._gallery_resize_job)
            self._gallery_resize_job = None
        if self._find_job:
            self.window.after_cancel(self._find_job)
            self._find_job = None
        self.window.destroy()
        return True


class WarningPopup:
    def __init__(self, parent, warnings):
        window = tk.Toplevel(parent)
        window.title('Measurement metadata warning')
        window.transient(parent)
        ttk.Label(window, text='Directory paths and file metadata disagree, or identity metadata is missing.', wraplength=650).pack(padx=10, pady=10)
        frame = ttk.Frame(window)
        frame.pack(fill='both', expand=True, padx=10)
        text = tk.Text(frame, width=85, height=min(20, max(6, len(warnings) * 5)), wrap='word')
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side='right', fill='y')
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill='both', expand=True)
        text.insert('1.0', '\n\n'.join(warnings))
        text.configure(state='disabled')
        ttk.Label(window, text='Select the affected measurements and use Correct Assignment… to fix them.').pack(padx=10, pady=8)
        ttk.Button(window, text='Close', command=window.destroy).pack(pady=(0, 10))


class CorrectionDialog:
    def __init__(self, browser, measurements):
        self.browser, self.measurements = browser, measurements
        self.plan = ()
        self.window = tk.Toplevel(browser.window)
        self.window.title('Correct Assignment')
        self.window.transient(browser.window)
        self.window.grab_set()
        scope = f'{len(measurements)} selected measurement(s)'
        ttk.Label(self.window, text=f'Apply to: {scope}\nBlank fields keep their current values.', wraplength=750).pack(padx=10, pady=10)
        fields = ttk.Frame(self.window)
        fields.pack(fill='x', padx=10)
        identities = [item.identity for item in measurements]
        self.variables = {}
        for row, key in enumerate(IDENTITY_KEYS):
            values = {identity.parts[row] for identity in identities}
            initial = next(iter(values)) if len(values) == 1 else ''
            ttk.Label(fields, text=key).grid(row=row, column=0, sticky='w', pady=3)
            variable = self.variables[key] = tk.StringVar(value=initial)
            ttk.Entry(fields, textvariable=variable, width=45).grid(row=row, column=1, sticky='ew', padx=8, pady=3)
            variable.trace_add('write', lambda *_: self._invalidate())
        fields.columnconfigure(1, weight=1)
        frame = ttk.Frame(self.window)
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.preview = tk.Text(frame, width=100, height=18, wrap='none', state='disabled')
        scroll = ttk.Scrollbar(frame, command=self.preview.yview)
        scroll.pack(side='right', fill='y')
        self.preview.configure(yscrollcommand=scroll.set)
        self.preview.pack(fill='both', expand=True)
        buttons = ttk.Frame(self.window)
        buttons.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(buttons, text='Preview Changes', command=self._preview).pack(side='left')
        self.apply_button = ttk.Button(buttons, text='Apply Changes', state='disabled', command=self._apply)
        self.apply_button.pack(side='right')
        ttk.Button(buttons, text='Cancel', command=self.window.destroy).pack(side='right', padx=5)

    def _invalidate(self):
        self.plan = ()
        self.apply_button.configure(state='disabled')
        self.preview.configure(state='normal')
        self.preview.delete('1.0', 'end')
        self.preview.configure(state='disabled')

    def _preview(self):
        self._invalidate()
        try:
            changes = {key: variable.get().strip() for key, variable in self.variables.items()}
            self.plan = plan_correction(self.browser.data_root, measurements=self.measurements, changes=changes)
            lines = []
            for item in self.plan:
                source, destination = item.source.relative_to(self.browser.data_root), item.destination.relative_to(self.browser.data_root)
                lines.append(f'{source}\n  → {destination}')
                if item.is_csv:
                    lines.append('  CSV header → ' + item.identity.label)
            self.preview.configure(state='normal')
            self.preview.insert('1.0', '\n\n'.join(lines) if lines else 'No files in this selection.')
            self.preview.configure(state='disabled')
            self.apply_button.configure(state='normal' if self.plan else 'disabled')
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror('Cannot correct assignment', str(exc), parent=self.window)

    def _apply(self):
        if self.browser.is_running():
            messagebox.showinfo('Correct Assignment', 'Wait for the measurement run to finish before correcting saved files.', parent=self.window)
            return
        try:
            self.apply_button.configure(state='disabled', text='Correcting…')
            self.window.configure(cursor='watch')
            self.window.update_idletasks()
            apply_correction(self.browser.data_root, self.plan)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror('Assignment correction failed', str(exc), parent=self.window)
            self._invalidate()
            self.apply_button.configure(text='Apply Changes')
            return
        finally:
            self.window.configure(cursor='')
        chips = {item.identity.chip for item in self.plan}
        if len(chips) == 1:
            self.browser.chip = chips.pop()
        self.browser.selected_identities = {item.identity for item in self.plan
                                            if item.identity.chip == self.browser.chip}
        self.window.destroy()
        self.browser.refresh()
