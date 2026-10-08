"""A compact condition editor for the measurement gallery."""

import tkinter as tk
from tkinter import ttk, messagebox

from measurement_query import FIELDS, Condition, MeasurementQuery
from tooltip_helper import attach_tooltip


class MeasurementFilterDialog:
    def __init__(self, parent, query, measurements, apply):
        self.apply = apply
        self.measurements = measurements
        self.fields = tuple(dict.fromkeys((*FIELDS, *sorted({key for item in measurements for key in item.metadata}))))
        self.rows = []
        self.window = tk.Toplevel(parent)
        self.window.title('Find / Filter Measurements')
        self.window.transient(parent)
        self.window.grab_set()
        form = ttk.Frame(self.window, padding=8)
        form.pack(fill='both', expand=True)
        ttk.Label(form, text='Text').grid(row=0, column=0, sticky='w')
        self.text = tk.StringVar(value=query.text)
        entry = ttk.Entry(form, textvariable=self.text, width=48)
        entry.grid(row=0, column=1, sticky='ew', padx=(6, 0))
        attach_tooltip(entry, 'Find words in filenames, identity, saved metadata, or device notes.')
        ttk.Label(form, text='Dates').grid(row=1, column=0, sticky='w', pady=5)
        dates = ttk.Frame(form)
        dates.grid(row=1, column=1, sticky='w', padx=6)
        self.from_date, self.to_date = tk.StringVar(value=query.from_date), tk.StringVar(value=query.to_date)
        for label, variable in (('From', self.from_date), ('To', self.to_date)):
            ttk.Label(dates, text=label).pack(side='left', padx=(0, 4))
            date_entry = ttk.Entry(dates, textvariable=variable, width=12)
            date_entry.pack(side='left', padx=(0, 8))
            attach_tooltip(date_entry, 'YYYY-MM-DD, inclusive. Leave blank for an open end.')
        ttk.Label(form, text='Match').grid(row=2, column=0, sticky='w', pady=5)
        self.mode = tk.StringVar(value='Any condition' if query.match_any else 'All conditions')
        ttk.Combobox(form, textvariable=self.mode, values=('All conditions', 'Any condition'),
                     state='readonly', width=18).grid(row=2, column=1, sticky='w', padx=6, pady=5)
        self.conditions_frame = ttk.Frame(form)
        self.conditions_frame.grid(row=3, column=0, columnspan=2, sticky='ew')
        for condition in query.conditions or (Condition('Procedure', 'contains', ''),):
            self._add_condition(condition)
        ttk.Button(form, text='+ Condition', command=self._add_condition).grid(row=4, column=0, columnspan=2, sticky='w', pady=6)
        actions = ttk.Frame(form)
        actions.grid(row=5, column=0, columnspan=2, sticky='ew')
        ttk.Button(actions, text='Clear Filter', command=self._clear).pack(side='left')
        ttk.Button(actions, text='Apply', command=self._submit).pack(side='right')
        ttk.Button(actions, text='Cancel', command=self.window.destroy).pack(side='right', padx=5)
        form.columnconfigure(1, weight=1)
        self.window.bind('<Return>', lambda event: self._submit())
        self.window.bind('<Escape>', lambda event: self.window.destroy())
        entry.focus_set()

    def _add_condition(self, condition=None):
        condition = condition or Condition('Procedure', 'contains', '')
        frame = ttk.Frame(self.conditions_frame)
        frame.pack(fill='x', pady=2)
        field, comparison, value = (tk.StringVar(value=text) for text in (condition.field, condition.comparison, condition.value))
        row = frame, field, comparison, value
        self.rows.append(row)
        field_box = ttk.Combobox(frame, textvariable=field, values=self.fields, state='readonly', width=18)
        field_box.pack(side='left')
        operator_box = ttk.Combobox(frame, textvariable=comparison, state='readonly', width=13)
        operator_box.pack(side='left', padx=4)
        value_box = ttk.Combobox(frame, textvariable=value, width=23)
        value_box.pack(side='left', fill='x', expand=True)

        def update(event=None):
            operators = ('is', 'is not', 'after', 'on or after', 'before', 'on or before') if field.get() == 'Date' else ('contains', 'is', 'is not', '>', '>=', '<', '<=')
            operator_box.configure(values=operators)
            if comparison.get() not in operators:
                comparison.set(operators[0])
            choices = {'Device status': ('Good', 'OK', 'Bad', 'Untagged'),
                       'Has notes': ('Yes', 'No'), 'Has plot': ('Yes', 'No'), 'Metadata warning': ('Yes', 'No')}
            values = choices.get(field.get(), sorted({str(item.metadata.get(field.get(), getattr(item.identity, field.get().lower(), '')))
                                                     for item in self.measurements} - {''}))
            value_box.configure(values=values)

        field_box.bind('<<ComboboxSelected>>', update)
        attach_tooltip(value_box, lambda: 'YYYY-MM-DD' if field.get() == 'Date' else 'Choose a saved value or enter your own.')
        ttk.Button(frame, text='×', width=2, command=lambda: self._remove(row)).pack(side='left', padx=(4, 0))
        update()

    def _remove(self, row):
        self.rows.remove(row)
        row[0].destroy()

    def _submit(self):
        conditions = tuple(Condition(field.get(), comparison.get(), value.get().strip())
                           for _, field, comparison, value in self.rows if value.get().strip())
        query = MeasurementQuery(self.text.get().strip(), conditions, self.mode.get() == 'Any condition',
                                 self.from_date.get().strip(), self.to_date.get().strip())
        try:
            query.validate()
        except ValueError as exc:
            messagebox.showerror('Invalid filter', str(exc), parent=self.window)
            return
        if self.apply(query):
            self.window.destroy()

    def _clear(self):
        if self.apply(MeasurementQuery()):
            self.window.destroy()
