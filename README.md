# Python Measurement GUI App Architecture

## Overview
This is a simplified Python-based GUI application for running automated measurements on semiconductor devices using instruments like B1500 and WGFMU. It replaces a console-based C# workflow with a Tkinter GUI, CSV-based device configs, and automatic probe station movement via sentio. The app allows users to select sites, subsites, devices, and procedures, then execute measurements with logging and data saving.

Key goals: Simplicity, ease of config editing, automatic movement, and extensibility for new procedures.

## Architecture Components
- **Language**: Python 3.x
- **GUI**: Tkinter (built-in, lightweight)
- **Instrument Control**: pyvisa for GPIB communication
- **Config Handling**: pandas for CSV, json for global settings
- **Movement**: subprocess calls to sentio subsite_move (assumed command-line tool)
- **Logging**: Console + GUI text area
- **Data Saving**: CSV files in hierarchical folders (output/{Site}/{Subsite}/{Device}/)

## File Structure
```
PythonMeasurementApp/
├── models.py              # Data classes: Device, Subsite, Site
├── config.py              # Config loader/saver for CSV and JSON
├── runner.py              # MeasurementRunner: orchestrates execution, movement, logging
├── ui.py                  # Main Tkinter GUI
├── procedures/
│   ├── base.py            # Abstract MeasurementProcedure class
│   └── cv_sweep.py        # Example concrete procedure
├── requirements.txt       # Dependencies: pyvisa, pandas
├── devices.csv            # Sample device config (Site, Subsite, Device, X, Y)
├── global_config.json     # Auto-generated global settings (GPIB, output dir, procedure settings)
├── bindings.py            # Python bindings to B1500 and WGFMU C APIs
└── README.md              # This file
```

## Dependencies
- pyvisa: For instrument communication
- pandas: For CSV parsing
- tkinter: Built-in for GUI
- ctypes: Built-in for C DLL bindings (for B1500/WGFMU)
- pythonnet: For C# DLL bindings (optional alternative)

## Windows Run / Setup

This project targets Windows for real instrument DLL execution. Use split environments:
- Main env (64-bit): `.venv` (run the UI from here)
- Worker env (32-bit): `.venv32` (auto-started by the bridge)

The normal lab-user entry point is:

```text
Run Measurement App.cmd
```

Double-clicking that file checks for `uv`, creates or updates `.venv` and `.venv32`, installs `requirements.txt` into the main env, and launches `main.py`.

Prerequisites on the instrument PC:
- `uv` on `PATH`
- 64-bit Python 3.11
- 32-bit Python 3.11 for the vendor DLL bridge
- Vendor B1500/WGFMU/VISA DLLs installed in their standard locations, or supplied with environment overrides

If Python auto-detection fails, run from PowerShell with explicit interpreters:

```powershell
.\scripts\windows\run_app.ps1 `
    -Python64 "C:\Path\To\Python311-x64\python.exe" `
    -Python32 "C:\Path\To\Python311-x86\python.exe"
```

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
1. Prepare one or more device CSV files (columns: `Site,Subsite,Device,X,Y`).
2. Double-click `Run Measurement App.cmd` to launch the GUI.
3. In the Selection panel, choose a `Devices CSV` source (dropdown or `Browse...`).
4. Select site/subsite/device/procedure.
5. Click "Run" to execute (logs to GUI, saves data).

## Key Classes and Methods
### models.py
- `Device(name, x, y)`: Represents a device with position.
- `Subsite(name, devices)`: List of devices.
- `Site(name, subsites)`: List of subsites.
- `load_devices_csv(csv_path)`: Parses CSV into Site list.

### config.py
- `Config(config_path, devices_csv_path)`: Loads/saves global JSON and devices CSV.
- `load()`: Loads JSON or defaults.
- `save()`: Saves JSON.
- `get_procedure_settings(proc_name)`: Retrieves settings dict.
- `set_procedure_settings(proc_name, settings)`: Saves settings.

### procedures/base.py
- `MeasurementProcedure(settings, output_dir, runner)`: Abstract base with runner provided at construction.
- `run(device)`: Abstract method for execution.
- `log(message)`: Logs with timestamp.
- `save_data(data, filename, headers)`: Saves CSV.

### procedures/cv_sweep.py (Example)
- `CVSweepProcedure`: Inherits from base.
- `run(device)`: Implements measurement logic using bindings to B1500/WGFMU.

### runner.py
- `MeasurementRunner(config)`: Handles execution.
- `log_to_gui(msg)`: Updates GUI log.
- `move_to_device(device)`: Calls sentio move (subprocess).
- `run_procedure(site, subsite, device, proc_class, settings)`: Sets up and runs procedure.

### ui.py
- `MainUI(root)`: Tkinter form.
- Dropdowns for site/subsite/device/procedure.
- `run()`: Triggers execution.
- `log(msg)`: Appends to text area.
- Event handlers: `update_subsites()`, `update_devices()`.

### bindings.py
- `B1500Session`: Wrapper for B1500 instrument using ctypes to agb1500_32.dll
- `WGFMUSession`: Wrapper for WGFMU using ctypes to WGFMU.dll
- Functions to initialize, configure, measure, etc.

## Planned Temperature Control Design
### Modes and UI
- Top-level toggle to enable/disable the Temperature panel; when off, the panel is disabled/gray and the app behaves exactly as today.
- Mode selector inside the panel: Off / Setpoint / Sweep.
  - Off: identical to current app; no temperature actions.
  - Setpoint: single temperature value (°C).
  - Sweep: comma-separated list of temperatures (°C).
- Shared fields: “Wait after stabilization” time (seconds) slept after stability is reached; optional poll interval for stability/live reads.
- Tiny visualization in the panel:
  - Always shows the target temperature profile (index or cumulative time vs. target temp) for Setpoint/Sweep.
  - If easy to wire, overlay live measured temperature vs. elapsed time via periodic reads; if not, just show the target profile.

### Runner orchestration
- Add a temperature controller handle on the runner with `set_point(temp_c)`, `wait_until_stable(target_c, tol, poll)`, and `read_temp()`.
- Track `runner.current_temp_c` while a temperature is active; clear it when not.
- New method `run_temperature_sweep(temp_list_c, wait_after_stable_s, settings, proc_class, selection...)`:
  - For each target `t` in `temp_list_c`: check stop; set setpoint; wait until stable; sleep `wait_after_stable_s`; then invoke existing run path (subsite or single device) with the same settings (optionally include `temperature_c` in settings for logging/CSV headers).
  - No extra edge-handling; a stop just stops.

### File and plot naming
- Keep the same output directory structure (no per-temperature subfolders).
- Filenames gain a Kelvin suffix when temperature is active: `_{temp_k:.0f}K` inserted before the procedure tag in the base filename (`chip_site_subsite_device_timestamp_298K_proc`). Timestamps remain, so no overwrites.
- Plot titles include the same Kelvin tag when temperature is active.

### Persistence
- Store the temperature toggle state, mode (Off/Setpoint/Sweep), temperatures, wait-after-stabilization time, and poll interval in config/last selection alongside existing settings.

### Procedure impact
- Procedures remain temperature-agnostic. They may read `settings.get("temperature_c")` or `runner.current_temp_c` for logging/CSV headers, but no changes are required when temperature is off.
- `MeasurementProcedure.format_filename` should append the Kelvin suffix when a temperature is present (integer Kelvin, formatted with `.0f`).

### Live temperature (optional but simple)
- If implemented: a UI `after` timer reads `read_temp()` every poll interval during a temperature run and updates the tiny plot; stop the timer when the run ends to avoid collisions.

### Non-goals
- Swallowing errors
- Beyond-reasonable robustness when erroring
- Hacky solutions

## Config Files
- **Device CSV files**: Flat CSV catalogs for devices. Columns: Site, Subsite, Device, X, Y.
- **global_config.json**: Stores global app settings including the active `devices_csv_path`.

## Procedures
- Known at compile time (hardcoded in UI).
- Each is a class inheriting `MeasurementProcedure`.
- Settings: Dict stored in global_config.json.
- Add new procedures by creating subclasses and updating UI values.

## GUI
- Comboboxes for selection (cascading updates).
- Run button.
- Log text area.
- No complex controls—keeps it simple.

## Workflow
1. Load configs on startup.
2. User selects via GUI.
3. On run: Move to device (sentio), execute procedure (instrument calls via bindings), log/save.
4. Repeat for multiple devices if needed.

## Reference Programs Analysis

### C++ Reference (Measuring_with_B1500)
The C++ program in `Main.cpp` and `Functions.cpp` provides a console-based measurement workflow:

- **Initialization**: Uses VISA to open GPIB session to B1500 (e.g., "GPIB0::17::INSTR").
- **B1500 Setup**: Calls `agb1500_init`, `agb1500_reset`, `agb1500_timeOut`, `agb1500_errorQueryDetect`.
- **Measurement Loop**:
  - For each subsite/cycle/RV step:
    - `pulse_wgfmu`: Creates pulse pattern on WGFMU channels (101 dummy, 102 pulse), executes, saves data.
    - `perform_IV`: Forces voltage on B1500 SMU, measures current, saves data.
- **Key Functions in Functions.cpp**:
  - `init`: Checks B1500 init status.
  - `check_err`: Error handling for B1500.
  - `writeResults`: Saves WGFMU measurement data to CSV.
  - `pulse_wgfmu`: Sets up WGFMU patterns and sequences.
  - `perform_IV`: Configures B1500 for IV sweep, executes, saves.

This uses direct C API calls via headers `agb1500.h` and `wgfmu.h`, linked to DLLs.

### C# Reference (Measuring_with_B1500_CSharp)
The C# program provides an object-oriented workflow:

- **Classes**:
  - `MeasurementConfig`: Holds settings (GPIB, biases, vectors, etc.).
  - `MeasurementWorkflow`: Orchestrates the run.
- **Initialization**: Opens B1500 session via `AgB1500.agb1500_init`.
- **WGFMU Usage**: Uses `WGFMU` class (Interop) for patterns, sequences, measurements.
- **B1500 Usage**: P/Invoke to `agb1500_32.dll` for SMU control.
- **Execution**: Builds RV vector, runs pulses on WGFMU, IV on B1500, saves data.

The C# is a thin wrapper over the C APIs, using P/Invoke for B1500 and COM/Interop for WGFMU.

### Manufacturer Sample Programs (B1530A-InstLib-SampleProgram)
These include C# WinForms apps for various procedures (DATASAMPLER, NBTI, PULSE, etc.):

- Use similar B1500/WGFMU APIs.
- GUI for config, execution, data plotting.
- Demonstrate full measurement sequences.

## Python Bindings Implementation

To port the C# and C++ logic to Python, we need bindings to the instrument DLLs. Two main approaches:

### Option 1: ctypes for C APIs (Recommended)
Use Python's built-in `ctypes` to call the C DLLs directly, similar to C++.

- **Advantages**: No extra dependencies, direct access, matches reference code.
- **Disadvantages**: Manual marshalling, error-prone.

### Option 2: pythonnet for C# Assemblies
Use `pythonnet` to load C# DLLs and call managed code.

- **Advantages**: Leverage existing C# wrappers.
- **Disadvantages**: Requires .NET runtime, pythonnet installation.

We'll implement Option 1 (ctypes) as it's simpler and matches the low-level C APIs.

### B1500 Bindings (agb1500_32.dll)
Based on `AgB1500.cs` P/Invoke:

```python
import ctypes as ct

class B1500Session:
    def __init__(self, gpib_addr="GPIB0::17::INSTR"):
        self.dll = ct.windll.LoadLibrary("agb1500_32.dll")
        self.session = ct.c_int()
        ret = self.dll.agb1500_init(gpib_addr.encode(), 1, 1, ct.byref(self.session))
        if ret != 0:
            raise RuntimeError(f"B1500 init failed: {ret}")

    def reset(self):
        self.dll.agb1500_reset(self.session)

    def set_timeout(self, ms):
        self.dll.agb1500_timeOut(self.session, ms)

    def enable_error_detect(self, enable):
        self.dll.agb1500_errorQueryDetect(self.session, 1 if enable else 0)

    def force_voltage(self, channel, voltage, compliance=1e-3):
        # agb1500_force: session, channel, mode=1 (IM), range=0 (auto), value, compliance, polarity=0
        ret = self.dll.agb1500_force(self.session, channel, 1, 0.0, voltage, compliance, 0)
        self._check_error(ret)

    def measure_current(self, channel):
        # Simplified: assume force is set, measure
        # In practice, use agb1500_sweepIv or similar
        pass  # Implement based on perform_IV

    def close(self):
        self.dll.agb1500_close(self.session)

    def _check_error(self, ret):
        if ret < 0:
            # Query error message
            pass
```

Full implementation in `instrumentio/sessions.py` and `instrumentio/bindings.py`.

### WGFMU Bindings (WGFMU.dll)
Based on `WGFMU.cs` DllImport:

```python
class WGFMUSession:
    def __init__(self):
        self.dll = ct.windll.LoadLibrary("WGFMU.dll")

    def clear(self):
        ret = self.dll.WGFMU_clear()
        self._check_error(ret)

    def create_pattern(self, name, initial_voltage=0.0):
        ret = self.dll.WGFMU_createPattern(name.encode(), initial_voltage)
        self._check_error(ret)

    def add_vector(self, pattern_name, time, voltage):
        ret = self.dll.WGFMU_addVector(pattern_name.encode(), time, voltage)
        self._check_error(ret)

    def add_sequence(self, channel_id, pattern_name, repetitions):
        ret = self.dll.WGFMU_addSequence(channel_id, pattern_name.encode(), repetitions)
        self._check_error(ret)

    def execute(self):
        ret = self.dll.WGFMU_execute()
        self._check_error(ret)

    def get_measure_value_size(self, channel_id):
        size = ct.c_int()
        total = ct.c_int()
        ret = self.dll.WGFMU_getMeasureValueSize(channel_id, ct.byref(size), ct.byref(total))
        self._check_error(ret)
        return size.value, total.value

    def get_measure_value(self, channel_id, index):
        time = ct.c_double()
        value = ct.c_double()
        ret = self.dll.WGFMU_getMeasureValue(channel_id, index, ct.byref(time), ct.byref(value))
        self._check_error(ret)
        return time.value, value.value

    def _check_error(self, ret):
        if ret < 0:
            raise RuntimeError(f"WGFMU error: {ret}")
```

Full implementation in `bindings.py`.

### Using Bindings in Procedures
In `rv_sweep.py`:

```python
from instrumentio.sessions import B1500Session, WGFMUSession

class CVSweepProcedure(MeasurementProcedure):
    def run(self, device, runner):
        b1500 = B1500Session()
        wgfmu = WGFMUSession()
        # Setup patterns like in pulse_wgfmu
        wgfmu.clear()
        wgfmu.create_pattern("pulse", 0)
        # ... add vectors
        wgfmu.execute()
        # Then B1500 CV
        ...
        # Measure and save
        b1500.close()
```

### Alternative: pythonnet for C#
If preferring C#:

```python
import clr
clr.AddReference("Measuring_with_B1500_CSharp.exe")  # Or DLL
from Measuring_with_B1500_CSharp import MeasurementWorkflow, MeasurementConfig

def run_csharp():
    config = MeasurementConfig()
    workflow = MeasurementWorkflow(config)
    workflow.Run()
```

But requires compiling C# to DLL.

## Simplifications
- No JSON for devices (too nested)—use flat CSV.
- No procedure list in config—compile-time known.
- Automatic movement via sentio—no manual prompts.
- Synchronous execution—no threads yet.
- Port C# logic directly to Python via ctypes bindings.

## C# Binding (Optional)
If reusing C# code:
- Install pythonnet.
- In runner.py: `import clr; clr.AddReference('YourDll.dll'); from YourNamespace import Class; obj = Class(); obj.Method()`

## Implementation Notes for AI Agent
- Start with models and config.
- Implement bindings.py with ctypes wrappers.
- Build procedures by porting C++/C# instrument code to bindings.
- Integrate sentio in runner.move_to_device().
- Test GUI selections and logging.
- Extend for more procedures/devices as needed.
