"""Whole-sample data browser, plot gallery, and device notes."""

from pathlib import Path
from types import SimpleNamespace
import math
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

from data_management import (
    IDENTITY_KEYS, STATUSES, STATUS_COLORS, Identity, chips_in, scan_chip,
    layout_devices, missing_geometry, read_notes, write_notes, plan_correction, apply_correction,
)
from ui_sample_view import SampleMap


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
        self._warned = set()
        self._sash_job = None
        self.window = tk.Toplevel(parent)
        self.window.title('Data Management')
        self.window.geometry('1250x800')
        self.window.minsize(900, 600)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self._build()
        self._refresh_chips()
        self.refresh()

    def _build(self):
        toolbar = ttk.Frame(self.window)
        toolbar.pack(fill='x', padx=8, pady=6)
        ttk.Label(toolbar, text=str(self.data_root)).pack(side='left')
        ttk.Button(toolbar, text='Refresh', command=self.refresh).pack(side='right')
        panes = ttk.Panedwindow(self.window, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=1)
        self._sash_job = self.window.after_idle(lambda: panes.sashpos(0, int(panes.winfo_width() * 2 / 3)))

        header = ttk.Frame(left)
        header.pack(fill='x')
        picker = ttk.LabelFrame(header, text='Chip')
        picker.pack(side='left', anchor='nw', padx=4, pady=4)
        self.search = tk.StringVar()
        ttk.Entry(picker, textvariable=self.search, width=24).pack(fill='x', padx=4, pady=4)
        self.chip_list = tk.Listbox(picker, height=3, width=24, exportselection=False)
        self.chip_list.pack(fill='x', padx=4, pady=(0, 4))
        self.search.trace_add('write', lambda *_: self._filter_chips())
        self.chip_list.bind('<<ListboxSelect>>', self._choose_chip)
        self.chip_list.bind('<Button-3>', self._chip_menu)
        self.chip_list.bind('<Button-2>', self._chip_menu)
        legend = ttk.Frame(header)
        legend.pack(side='left', padx=12, anchor='nw', pady=10)
        for status, color in STATUS_COLORS.items():
            tk.Label(legend, text=f'● {status}', foreground=color).pack(anchor='w')
        ttk.Label(legend, text='Blue outline: selected').pack(anchor='w')
        self.view_toggle = ttk.Button(header, text='List View', command=self._toggle_view)
        self.view_toggle.pack(side='right', padx=4, pady=4)
        self.explanation = ttk.Label(left, wraplength=650)
        self.explanation.pack(fill='x', padx=5, pady=4)
        self.view_frame = ttk.Frame(left)
        self.view_frame.pack(fill='both', expand=True)
        self.folder_button = ttk.Button(left, text='Correct Selected Device Folders…', command=self._correct_devices)
        self.folder_button.pack(anchor='w', padx=4, pady=5)

        self.notes_frame = ttk.LabelFrame(right, text='Select one device to edit its notes and status')
        self.notes_frame.pack(fill='x', padx=5, pady=5)
        controls = ttk.Frame(self.notes_frame)
        controls.pack(fill='x', padx=5, pady=4)
        ttk.Label(controls, text='Status').pack(side='left')
        self.status = tk.StringVar()
        self.status_box = ttk.Combobox(controls, textvariable=self.status, values=STATUSES, width=10, state='disabled')
        self.status_box.pack(side='left', padx=6)
        self.status_box.bind('<<ComboboxSelected>>', self._status_changed)
        self.clear_status_button = ttk.Button(controls, text='Clear', command=self._clear_status, state='disabled')
        self.clear_status_button.pack(side='left')
        self.save_label = ttk.Label(controls)
        self.save_label.pack(side='right')
        self.notes = tk.Text(self.notes_frame, height=6, wrap='word', undo=True, state='disabled')
        self.notes.pack(fill='x', padx=5, pady=(0, 5))
        self.notes.bind('<<Modified>>', self._notes_changed)
        self.notes.bind('<FocusOut>', lambda event: self.save_notes())

        gallery_header = ttk.Frame(right)
        gallery_header.pack(fill='x', padx=5, pady=4)
        self.gallery_label = ttk.Label(gallery_header, text='Measurements')
        self.gallery_label.pack(side='left')
        ttk.Button(gallery_header, text='Correct Assignment…', command=self._correct_measurements).pack(side='right')
        navigation = ttk.Frame(right)
        navigation.pack(fill='x', padx=5)
        ttk.Button(navigation, text='Previous', command=lambda: self._change_page(-1)).pack(side='left')
        self.page_label = ttk.Label(navigation)
        self.page_label.pack(side='left', padx=6)
        ttk.Button(navigation, text='Next', command=lambda: self._change_page(1)).pack(side='right')
        self.gallery_canvas = tk.Canvas(right, highlightthickness=0)
        scroll = ttk.Scrollbar(right, orient='vertical', command=self.gallery_canvas.yview)
        scroll.pack(side='right', fill='y')
        self.gallery_canvas.pack(fill='both', expand=True, padx=5, pady=5)
        self.gallery_canvas.configure(yscrollcommand=scroll.set)
        self.gallery_frame = ttk.Frame(self.gallery_canvas)
        self.gallery_window = self.gallery_canvas.create_window(0, 0, window=self.gallery_frame, anchor='nw')
        self.gallery_frame.bind('<Configure>', lambda event: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox('all')))
        self.gallery_canvas.bind('<Configure>', lambda event: self.gallery_canvas.itemconfigure(self.gallery_window, width=event.width))
        self.gallery_canvas.bind('<MouseWheel>', self._scroll_gallery)
        self.gallery_canvas.bind('<Button-4>', self._scroll_gallery)
        self.gallery_canvas.bind('<Button-5>', self._scroll_gallery)
        self.gallery_canvas.bind('<Control-a>', self._select_all_measurements)
        if sys.platform == 'darwin':
            self.gallery_canvas.bind('<Command-a>', self._select_all_measurements)

    def _refresh_chips(self):
        self.chips = chips_in(self.data_root)
        if self.chip and self.chip not in self.chips:
            self.chips.append(self.chip)
        self.chips.sort(key=str.casefold)
        self._filter_chips()

    def _filter_chips(self):
        self.visible_chips = [chip for chip in self.chips if self.search.get().casefold() in chip.casefold()]
        self.chip_list.delete(0, 'end')
        for index, chip in enumerate(self.visible_chips):
            self.chip_list.insert('end', chip)
            if chip == self.chip:
                self.chip_list.selection_set(index)

    def _choose_chip(self, event=None):
        selected = self.chip_list.curselection()
        if selected:
            if not self.save_notes():
                self._filter_chips()
                return
            chip = self.visible_chips[selected[0]]
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
            for identity in self.all_identities:
                status, notes = read_notes(self.data_root, identity)
                self.annotations[self._key(identity)] = self._annotation(identity, status, notes)
            self._show_view(as_list=bool(self.missing))
            self._selection_changed({self._key(identity) for identity in self.selected_identities}, force=True)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror('Data Management', str(exc), parent=self.window)

    @staticmethod
    def _key(identity):
        return '/'.join(identity.parts[1:])

    @staticmethod
    def _annotation(identity, status, notes):
        return {'status': status, 'has_notes': bool(notes),
                'details': identity.label + (f'\nStatus: {status}' if status else '') + (f'\n\n{notes}' if notes else '')}

    def _show_view(self, as_list=False):
        for child in self.view_frame.winfo_children():
            child.destroy()
        self.map = self.device_list = None
        self.view_toggle.configure(text='Map View' if as_list else 'List View', state='disabled' if self.missing else 'normal')
        if self.missing:
            examples = ', '.join(self._key(identity) for identity in self.missing[:4])
            more = f' (+{len(self.missing) - 4} more)' if len(self.missing) > 4 else ''
            self.explanation.configure(text=f'List view: devices.csv has missing entries or coordinates for {examples}{more}.')
        else:
            self.explanation.configure(text='Scroll to zoom; right/middle-drag to pan. Click or drag to select; Ctrl+Click toggles. Right-click for folder actions.')
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
            items = [SimpleNamespace(name=self._key(identity), display_name=f'{identity.subsite}/{identity.device}',
                                     identity=identity, x=device.absolute_x, y=device.absolute_y)
                     for identity, device in self.layout.items()]
            self.map = SampleMap(self.view_frame, items, self.annotations,
                                 {self._key(identity) for identity in self.selected_identities},
                                 self._selection_changed, self._map_menu)

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
            self._load_notes(next(iter(selected)) if len(selected) == 1 else None)
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror('Could not read device notes', str(exc), parent=self.window)
            return
        self.selected_identities = selected
        self.gallery_items = [item for item in self.measurements
                              if not self.selected_identities or item.identity in self.selected_identities]
        self.gallery_selection.clear()
        self.gallery_anchor, self.page = None, 0
        self._render_gallery()
        self._warn_mismatches()

    def _load_notes(self, identity):
        status, notes = read_notes(self.data_root, identity) if identity else ('', '')
        self._loading_notes = True
        self._notes_identity = identity
        self.notes_frame.configure(text=identity.label if identity else 'Select one device to edit its notes and status')
        self.notes.configure(state='normal')
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', notes)
        self.notes.edit_reset()
        self.notes.edit_modified(False)
        self.notes.configure(state='normal' if identity else 'disabled')
        self.status.set(status)
        self.status_box.configure(state='readonly' if identity else 'disabled')
        self.clear_status_button.configure(state='normal' if identity else 'disabled')
        self.save_label.configure(text='Saved automatically' if identity else '')
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
            self.annotations[key] = self._annotation(identity, self.status.get(), text)
            if self.map:
                self.map._draw_devices()
            if self.device_list:
                self.device_list.item(key, values=(*identity.parts[1:], self.status.get()), tags=(self.status.get(),))
            self._notes_dirty = False
            self.save_label.configure(text='Saved automatically')
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
        for child in self.gallery_frame.winfo_children():
            child.destroy()
        self.cards, self.photos = {}, []
        pages = max(1, math.ceil(len(self.gallery_items) / self.PAGE_SIZE))
        self.page = min(self.page, pages - 1)
        self.page_label.configure(text=f'{self.page + 1} / {pages}')
        self.gallery_label.configure(text=f'{len(self.gallery_items)} measurements · {len(self.gallery_selection)} selected')
        first = self.page * self.PAGE_SIZE
        for index in range(first, min(len(self.gallery_items), first + self.PAGE_SIZE)):
            item = self.gallery_items[index]
            card = tk.Frame(self.gallery_frame, borderwidth=2, relief='solid', background='white')
            card.pack(fill='x', padx=3, pady=4)
            self.cards[index] = card
            image = None
            if item.plot_files:
                try:
                    image = tk.PhotoImage(master=self.window, file=str(item.plot_files[0]))
                    factor = max(1, math.ceil(max(image.width() / 300, image.height() / 170)))
                    image = image.subsample(factor, factor)
                    self.photos.append(image)
                except tk.TclError:
                    pass
            picture = tk.Label(card, image=image, text='' if image else 'No readable plot', background='white')
            picture.pack(fill='x', pady=3)
            title = item.metadata.get('Procedure', item.name)
            caption = tk.Label(card, text=f'{title}\n{item.timestamp}\n{item.identity.site}/{item.identity.subsite}/{item.identity.device}'
                               + ('\n⚠ Folder / header mismatch' if item.warnings else ''),
                               justify='left', wraplength=310, background='white')
            caption.pack(fill='x', padx=4, pady=3)
            for widget in (card, picture, caption):
                widget.bind('<Button-1>', lambda event, i=index: self._gallery_click(i, event))
                widget.bind('<Button-3>', lambda event, i=index: self._gallery_menu(i, event))
                widget.bind('<Button-2>', lambda event, i=index: self._gallery_menu(i, event))
                widget.bind('<MouseWheel>', self._scroll_gallery)
                widget.bind('<Button-4>', self._scroll_gallery)
                widget.bind('<Button-5>', self._scroll_gallery)
                widget.bind('<Control-a>', self._select_all_measurements)
                if sys.platform == 'darwin':
                    widget.bind('<Command-Button-1>', lambda event, i=index: self._gallery_click(i, event, additive=True))
                    widget.bind('<Command-a>', self._select_all_measurements)
        if not self.gallery_items:
            ttk.Label(self.gallery_frame, text='No saved measurements for this selection.').pack(padx=10, pady=20)
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
        if not ctrl and not shift and self.gallery_items[index].plot_files:
            self._open_artifacts(self.gallery_items[index].plot_files)

    def _select_all_measurements(self, event=None):
        if self.save_notes():
            self.gallery_selection = set(range(len(self.gallery_items)))
            self._paint_gallery_selection()
        return 'break'

    def _paint_gallery_selection(self):
        for index, card in self.cards.items():
            card.configure(highlightbackground='dodgerblue' if index in self.gallery_selection else 'white',
                           highlightthickness=3)
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

    def _chip_menu(self, event):
        index = self.chip_list.nearest(event.y)
        if self.visible_chips:
            chip = self.visible_chips[index]
            menu = tk.Menu(self.window, tearoff=False)
            menu.add_command(label=f'Correct Chip Folder: {chip}…', command=lambda: self._correct(folders=[(chip,)]))
            self._popup(menu, event)

    def _list_menu(self, event):
        key = self.device_list.identify_row(event.y)
        identity = next((identity for identity in self.all_identities if self._key(identity) == key), None)
        if identity:
            self._map_menu('device', identity, event)

    def _map_menu(self, scope, value, event):
        if not self.save_notes():
            return
        menu = tk.Menu(self.window, tearoff=False)
        if scope == 'device':
            folders = [identity.parts for identity in sorted(self.selected_identities)] if value in self.selected_identities else [value.parts]
            menu.add_command(label='Correct Device Folder(s)…', command=lambda: self._correct(folders=folders))
            menu.add_command(label=f'Correct Subsite Folder: {value.subsite}…',
                             command=lambda: self._correct(folders=[value.parts[:3]]))
            menu.add_command(label=f'Correct Site Folder: {value.site}…',
                             command=lambda: self._correct(folders=[value.parts[:2]]))
        elif scope == 'site':
            menu.add_command(label=f'Correct Site Folder: {value}…', command=lambda: self._correct(folders=[(self.chip, value)]))
        menu.add_command(label='Correct Chip Folder…', command=lambda: self._correct(folders=[(self.chip,)]))
        self._popup(menu, event)

    def _correct_devices(self):
        self._correct(folders=[identity.parts for identity in sorted(self.selected_identities)])

    def _correct_measurements(self):
        self._correct(measurements=[self.gallery_items[index] for index in sorted(self.gallery_selection)])

    def _correct(self, measurements=(), folders=()):
        if not self.save_notes():
            return
        if not measurements and not folders:
            messagebox.showinfo('Correct Assignment', 'Select measurements or device folders first.', parent=self.window)
            return
        if self.is_running():
            messagebox.showinfo('Correct Assignment', 'Wait for the measurement run to finish before correcting saved files.', parent=self.window)
            return
        CorrectionDialog(self, measurements, folders)

    def close(self):
        if not self.save_notes():
            return False
        if self._sash_job:
            self.window.after_cancel(self._sash_job)
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
        ttk.Label(window, text='Use Correct Assignment… on the affected measurements or folders to fix them.').pack(padx=10, pady=8)
        ttk.Button(window, text='Close', command=window.destroy).pack(pady=(0, 10))


class CorrectionDialog:
    def __init__(self, browser, measurements, folders):
        self.browser, self.measurements, self.folders = browser, measurements, folders
        self.plan = ()
        self.window = tk.Toplevel(browser.window)
        self.window.title('Correct Assignment')
        self.window.transient(browser.window)
        self.window.grab_set()
        scope = '\n'.join('/'.join(folder) for folder in folders) if folders else f'{len(measurements)} selected measurement(s)'
        ttk.Label(self.window, text=f'Apply to: {scope}\nBlank fields keep their current values.', wraplength=750).pack(padx=10, pady=10)
        fields = ttk.Frame(self.window)
        fields.pack(fill='x', padx=10)
        identities = [item.identity for item in measurements] if measurements else [Identity(*(tuple(folder) + ('',) * (4 - len(folder)))) for folder in folders]
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
            self.plan = plan_correction(self.browser.data_root, self.measurements, self.folders, changes)
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
