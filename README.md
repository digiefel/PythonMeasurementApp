# Python Measurement App

Windows measurement application for Keysight B1500/SMU/CMU/WGFMU instruments
and a SENTIO probe station. Select a device catalog and procedure, configure the
measurement, and save readings and plots. The Tkinter app uses a separate plot
viewer and a 32-bit instrument worker for the vendor DLLs.

## Windows Run / Setup

This project targets Windows for real instrument execution. The lab-user entry point is:

```text
Run Measurement App.cmd
```

Double-clicking that file prepares the application and launches the UI. Instrument
support starts and stops automatically; there is no separate process for users
to manage.

The remaining setup details are for maintainers. The launcher creates or updates
`.venv` (64-bit application) and `.venv32` (32-bit native instrument support),
installs `requirements.txt` into the application environment, and runs `main.py`.

Prerequisites on the instrument PC:
- `uv` on `PATH`
- A modern 64-bit Python 3 for the main GUI environment
- The existing `.venv32` worker env, or 32-bit Python 3.11 so the script can create it
- Vendor B1500/WGFMU/VISA DLLs installed in their standard locations, or supplied with environment overrides

To only create/update the environments:

```powershell
.\scripts\windows\setup_uv_envs.ps1
```

Optional DLL overrides:

```powershell
.\scripts\windows\run_app.ps1 `
    -B1500Dll "C:\Path\To\agb1500_32.dll" `
    -WGFMUDll "C:\Path\To\WGFMU.dll" `
    -Visa32Dll "C:\Path\To\visa32.dll"
```

## Portable Config

Default configs live in `saved_configs`. The checked-in `global_config.json` uses repo-relative paths:
- `devices_csv_path`: `devices.csv` resolves to `saved_configs/devices.csv`
- `output_dir`: `output` resolves to a folder inside the app copy
- `fallback_output_dir`: `output` resolves to the same local folder

## How to Run
1. Prepare one or more device CSV files. See `docs/devices_csv.md` for the full format.
2. Double-click `Run Measurement App.cmd` to launch the GUI.
3. In the Selection panel, choose a `Devices CSV` source (dropdown or `Browse...`).
4. Select site/subsite/device/procedure.
5. Click "Run" to execute (logs to GUI, saves data).

## Documentation

- **ContactTest:** the button beside the procedure selector runs a standalone
  contact check without moving the prober. Operator name and GND/SMU1–4 choices
  reset each launch. Selected SMUs are swept against GNDU first, followed by a
  prompt to lift GNDU and sweeps between selected SMUs. With GND unchecked, the
  ground stage and prompt are skipped. Each sweep uses 20 points from −10 to
  +10 mV (excluding zero), a 10 mA compliance limit, high-speed ADC with one
  sample, parallel readings, Auto ≥100 nA, and automatic settling waits.
  Individual panels show current in mA with compact fitted-resistance labels;
  the combined panel shows one fitted-resistance bar per measured pair.
  Only fitted values are saved (one header and one data row) under
  `C:/Users/EMN Lab/Desktop/ContactTestLog/ContactTest_{timestamp}_{OperatorName}_{chip name}.csv`.
  Completed pairs are saved after each sweep; skipped pairs are omitted.
- **I/V sweeps:** `Isweep` and `Vsweep` share optional voltage probes, hardware
  sweep patterns, ADC/settling controls, and plotting. Open the
  [interactive sweep/CSV preview](docs/iv_sweep_preview.html) in a browser to
  explore simulated normal, compliance-flagged, and interrupted measurements.
  Regenerate it with `python -m scripts.build_iv_preview`.
- **Sweep CSV:** up to six columns: `VoltageHigh_V`, `VoltageLow_V`,
  `CurrentHigh_A`, `CurrentLow_A`, `Time_s`, `Status`. Header comments identify
  the selected endpoints and measured/programmed provenance. Unavailable
  quantities are omitted, GNDU quantities are NaN, and missing records are empty.
  Voltage columns use the optional sense probes when selected; current columns
  always refer to force terminals.
- **Data management:** [browse measurements, edit device notes/status, and correct assignments](docs/data_management.md).
- **Setting tooltips:** hover over a setting for the explanation declared beside
  its parameter in the procedure source.
- **Procedure implementation:** docstrings and comments in [procedures/](procedures/)
  explain calculations and sequencing next to the code.
- **Instrument implementation:** [sessions.py](instrumentio/sessions.py) documents
  driver calls and acquisition; [bridge_worker.py](instrumentio/bridge_worker.py)
  and [bridge.py](instrumentio/bridge.py) document ownership and cancellation.
- **Reference material:** [device CSV format](docs/devices_csv.md),
  [plot API](docs/plotting/api.md), [plot examples](docs/plotting/examples.md), and
  [plot architecture](docs/plotting/architecture.md).
- **Manufacturer manuals:** [B1500 Programming Guide](<docs/B1500 Programmers Guide 9018-01851.pdf>),
  [SMU Guide](<docs/B1500 SMU Guide.pdf>), and [WGFMU Guide](<docs/B1500 WGFMU Guide.pdf>).
  Page references in code use printed manual page numbers.

Keep implementation-specific explanations with their functions/classes. Declare
setting help alongside `parameter(..., help="...")`; the UI reads it directly.
Use `docs/` for manufacturer material and established references shared across
features, not procedure copies or implementation plans.

## Adding a procedure

Add a single `.py` file to `procedures/` and restart the app. In that file, define
one `MeasurementProcedure` subclass with a unique `NAME`, declare `PARAMETERS`,
and implement `measure(device)`. The app discovers it automatically; removing
that file removes the procedure after restarting. `base.py` and files beginning
with `_` are shared support, not selectable procedures. A broken procedure file
is logged and skipped, and saved selections fall back if a procedure was removed.

Keep procedure-specific helpers and documentation in the same file. Parameter
declarations provide form fields, defaults, runtime attributes, wrapped hover help
and CSV metadata. Optional `UI_ACTIONS` declare buttons with
`action("Label", callback)`: a callable defined in the procedure file receives
the app UI, providing `ui.collect_settings()` and `ui.root`. String callbacks
refer to shared app services, such as CMU calibration. Procedures can depend on
the shared app APIs and installed libraries; do not import another procedure file.

Use `self.b1500` and the runner's plot interface. Instrument connection ownership
and abort cleanup belong to the runner/bridge, not individual procedures.
