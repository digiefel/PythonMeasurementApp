"""Transient ContactTest controls and main-thread dialogs; no config writes."""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from procedures._contact_test import SUMMARY_ORDER, format_resistance, pair_sequence
from runner import MeasurementAbortRequested, MeasurementSkipRequested
from instrumentio.protocol import InstrumentCancelled
from window_layout import center_popup


def ask_options(ui):
    dialog = tk.Toplevel(ui.root)
    dialog.title('ContactTest')
    dialog.transient(ui.root)
    body = ttk.Frame(dialog, padding=18)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='ContactTest — probe connections', font=('TkDefaultFont', 12, 'bold')).grid(
        row=0, column=0, columnspan=2, sticky='w', pady=(0, 10))
    ttk.Label(body, text='Chip ID').grid(row=1, column=0, sticky='w', padx=(0, 10))
    chip = tk.StringVar(value=ui.chip_var.get().strip())
    chip_entry = ttk.Entry(body, textvariable=chip, width=30)
    chip_entry.grid(row=1, column=1, sticky='ew')
    ttk.Label(body, text='Operator name').grid(row=2, column=0, sticky='w', padx=(0, 10))
    operator = tk.StringVar(value='')
    entry = ttk.Entry(body, textvariable=operator, width=30)
    entry.grid(row=2, column=1, sticky='ew')
    probes = {}
    for row, label in enumerate(('GND', '1', '2', '3', '4'), start=3):
        probes[label] = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text=label if label == 'GND' else f'SMU{label}', variable=probes[label]).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=3)
    result = None

    def submit():
        nonlocal result
        chip_id = chip.get().strip()
        if not chip_id:
            messagebox.showerror('ContactTest', 'Please enter a Chip ID.', parent=dialog)
            chip_entry.focus_set()
            return
        selected = tuple(n for n in range(1, 5) if probes[str(n)].get())
        ground = probes['GND'].get()
        try:
            pair_sequence(selected, ground)
        except ValueError as exc:
            messagebox.showerror('ContactTest', str(exc), parent=dialog)
            return
        name = operator.get().strip()
        while not name:
            name = simpledialog.askstring('ContactTest', 'please enter your name:', parent=dialog)
            if name is None:
                return
            name = name.strip()
        result = chip_id, name, selected, ground
        dialog.destroy()

    buttons = ttk.Frame(body)
    buttons.grid(row=8, column=0, columnspan=2, sticky='e')
    ttk.Button(buttons, text='Cancel', command=dialog.destroy).pack(side='left', padx=5)
    ttk.Button(buttons, text='Start', command=submit).pack(side='left')
    dialog.bind('<Escape>', lambda _: dialog.destroy())
    center_popup(dialog, ui.root)
    dialog.grab_set()
    chip_entry.focus_set()
    ui.root.wait_window(dialog)
    return result


def confirm_lift(ui):
    """Called by worker; build/destroy Tk controls only on the UI thread."""
    done = threading.Event()
    accepted = False

    def show():
        if done.is_set():
            return
        dialog = tk.Toplevel(ui.root)
        dialog.title('ContactTest — lift GNDU')
        dialog.transient(ui.root)
        ttk.Label(dialog, text='please lift the GNDU tip to continue', padding=18).pack()

        def finish(value):
            nonlocal accepted
            accepted = value
            done.set()

        buttons = ttk.Frame(dialog, padding=(18, 0, 18, 18))
        buttons.pack(anchor='e')
        ttk.Button(buttons, text='Cancel', command=lambda: finish(False)).pack(side='left', padx=5)
        ttk.Button(buttons, text='Continue', command=lambda: finish(True)).pack(side='left')
        dialog.protocol('WM_DELETE_WINDOW', lambda: finish(False))
        dialog.bind('<Escape>', lambda _: finish(False))
        center_popup(dialog, ui.root)
        dialog.grab_set()

        def poll():
            if done.is_set():
                dialog.destroy()
            else:
                dialog.after(100, poll)
        poll()

    ui._post(show)
    try:
        while not done.wait(.1):
            ui.runner.check_stop('ContactTest stopped while waiting for GNDU lift.')
            if ui.runner.skip_device_event.is_set():
                raise MeasurementAbortRequested('ContactTest cancelled.')
        ui.runner.check_stop('ContactTest cancelled at GNDU prompt.')
        return accepted
    finally:
        done.set()


def show_results(ui, results, path):
    dialog = tk.Toplevel(ui.root)
    dialog.title('ContactTest results')
    dialog.transient(ui.root)
    body = ttk.Frame(dialog, padding=18)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Pair', font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky='w')
    ttk.Label(body, text='Fitted resistance (Ω)', font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=1, padx=(22, 0))
    for row, key in enumerate(SUMMARY_ORDER, start=1):
        ttk.Label(body, text=f'R{key}').grid(row=row, column=0, sticky='w', pady=3)
        ttk.Label(body, text=format_resistance(results.get(key)), font=('TkFixedFont', 11)).grid(
            row=row, column=1, sticky='e', padx=(22, 0), pady=3)
    ttk.Button(body, text='Close', command=dialog.destroy).grid(row=11, column=0, columnspan=2, sticky='e')
    center_popup(dialog, ui.root)


def start_contact_test(ui):
    if ui._connection_busy or ui._is_running() or ui._closing:
        return
    if ui._run_thread and ui._run_thread.is_alive():
        return
    if not ui._b1500_available():
        messagebox.showerror('ContactTest', 'Connect the B1500 before starting ContactTest.', parent=ui.root)
        return
    options = ask_options(ui)
    if options is None:
        return
    # A modal dialog runs Tk's event loop: recheck ownership before starting.
    if ui._closing or ui._connection_busy or ui._is_running() or not ui._b1500_available():
        return
    chip, operator, selected, ground = options
    address = ui.runner.b1500.address
    ui.runner.stop_event.clear()
    ui.runner.skip_device_event.clear()
    ui.runner.cancel_queue_event.clear()
    ui.runner.prober_motion_inhibited = True
    ui._set_running_state(True)
    ui.progress_frame.grid_remove()
    ui._set_section_enabled(ui.prober_frame, False)
    ui._finish_btn.configure(state=tk.DISABLED)
    ui._skip_button.configure(state=tk.DISABLED)

    def finish(results, path, error):
        ui._run_thread = None
        ui.runner.stop_event.clear()
        ui.runner.skip_device_event.clear()
        ui.runner.cancel_queue_event.clear()
        ui.runner.prober_motion_inhibited = False
        # Automatic reconnect also initializes the prober; leave that to an
        # explicit Reconnect action after a cancelled standalone measurement.
        ui._set_running_state(False, reconnect=False)
        ui._finish_btn.configure(state=tk.NORMAL)
        ui._skip_button.configure(state=tk.NORMAL)
        if results is not None:
            show_results(ui, results, path)
        elif error is not None:
            messagebox.showerror('ContactTest', error, parent=ui.root)

    def target():
        results = path = error = None
        try:
            results, path = ui.runner.run_contact_test(chip, operator, selected, ground,
                                                       lambda: confirm_lift(ui), address)
        except (MeasurementAbortRequested, MeasurementSkipRequested, InstrumentCancelled):
            ui._post_log('ContactTest cancelled. Completed pair fits, if any, remain in ContactTestLog.')
        except Exception as exc:
            error = str(exc)
            ui._post_log(f'ContactTest failed: {error}')
        finally:
            ui._post(finish, results, path, error)

    ui._run_thread = threading.Thread(target=target, daemon=True)
    ui._run_thread.start()
