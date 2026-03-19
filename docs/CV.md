# B1500 CV Sweep — Internal Architecture and Live Plotting

## What the agb1500 DLL is

The `agb1500_32.dll` is a Keysight VXIplug&play VISA instrument driver (copyright 1995-2005). It wraps all B1500 GPIB SCPI commands into callable C functions. Every DLL function simply translates into one or more ASCII SCPI commands sent over GPIB. The DLL is a convenience layer — it is not the only way to talk to the instrument.

---

## Anatomy of a CV Sweep (MM 18)

### The full SCPI command sequence

This is what `agb1500_setCv` + `agb1500_sweepCv` (and our Python `set_cv` + `sweep_cv`) translates to at the SCPI level:

```
*RST                          <- reset instrument
FMT 1,1                       <- set ASCII output format, include source data
TSC 1                         <- enable timestamps
DV <drain>,0,0,0.1,0          <- force 0V on drain/source SMUs (guard)
DV <source>,0,0,0.1,0
SSP <cmu_ch>,4                <- set SCUU path (CMU to output)
ACT 2,4                       <- CMU ADC integration: PLC mode, 4 cycles
FC <cmu_ch>,1000000           <- set AC frequency to 1 MHz
ACV <cmu_ch>,0.03             <- set AC oscillator level to 30 mV
ADJ <cmu_ch>,1                <- phase compensation (optional)
CORR? ...                     <- open/short correction (optional)
WMDCV 2,1                     <- auto-abort ON, post-sweep output = start value
WTDCV <hold>,<delay>,<sdelay> <- sweep timing (hold, delay, step delay)
WDCV <cmu_ch>,1,-5,5,21       <- define sweep: linear, -5V to +5V, 21 steps
MM 18,<cmu_ch>                <- measurement mode = CV (DC bias) sweep
IMP 100                       <- measurement parameter = Cp-G (para1=Cp, para2=G)
LMN 1                         <- enable monitor data output (osc level + DC bias)
RC <cmu_ch>,0                 <- measurement range = auto
TSR                           <- reset timestamp counter
XE                            <- *** TRIGGER: start the sweep ***
```

After `XE`, the instrument begins stepping the DC bias from start to stop, measuring impedance at each step.

### What happens physically at each step

1. CMU sets the DC bias to the next step voltage.
2. Wait for `delay` time (let the DUT settle).
3. The MFCMU applies a small AC signal (e.g. 30 mV at 1 MHz) superimposed on the DC bias.
4. The MFCMU's internal bridge circuit measures the complex impedance (phase-sensitive detection): it drives an AC current, measures the AC voltage response, and computes both the in-phase and quadrature components.
5. The ADC integrates for N power line cycles (PLC) to reject noise — at 50 Hz that's N x 20 ms per point.
6. The `IMP` mode setting determines how the raw R+jX is reported: e.g. `IMP 100` = Cp-G model (parallel capacitance and conductance).
7. The result (Para1=Cp, Para2=G, plus optional monitor data) is placed into the **data output buffer**.
8. Repeat for all sweep steps.

---

## The Two Ways to Read Sweep Data

The Programmer's Guide (page 1-18, "To Read Sweep Measurement Data") explicitly documents two approaches. This is the critical distinction.

### Method 1 — Read after completion (what `agb1500_sweepCv` does)

```vb
session.WriteString("XE" & vbLf)
session.WriteString("*OPC?" & vbLf)    ' <- BLOCKS until entire sweep finishes
rep = session.ReadString(1 + 2)         ' read *OPC? response ("1")
mret = session.ReadString(16 * 6 * nop) ' read ALL data at once
```

This is what the Programmer's Guide Table 3-21 example does, and it is what the DLL's `agb1500_sweepCv` does internally. The calling thread is blocked on the `*OPC?` read for the entire duration of the sweep.

### Method 2 — Read after every step (live streaming)

```vb
session.WriteString("FMT 5,0" & vbLf)
session.TerminationCharacter = 44        ' 44 = comma (ASCII)
session.TerminationCharacterEnabled = True
session.WriteString("XE" & vbLf)         ' start sweep (returns immediately)
For i = 0 To nop - 1
    ret_val = session.ReadString(16)     ' <- blocks only until THIS step is done
    ' parse and plot ret_val immediately
Next i
```

The Programmer's Guide says explicitly:

> "This way starts to read the data after the XE command. You do not need to wait for the sweep measurement completion. So you can check the result data before the sweep measurement is completed."

The trick is the **comma terminator**: `FMT 5,0` sets the output format so that each data block is terminated by a comma (`,`) instead of `CR/LF+EOI`. When you set the VISA session's `TerminationCharacter` to comma, each `ReadString` call returns as soon as one data item arrives — which happens as soon as the instrument finishes measuring one step.

### Why `agb1500_sweepCv` cannot do this

The DLL always uses Method 1 internally. It sends `XE`, waits for `*OPC?`, then bulk-reads the entire output buffer. There is no parameter or flag to change this behavior. The DLL is a black box.

---

## Data Structure Per Step

For a CV sweep with `FMT 1,1` (or `FMT 5,1`), `TSC 1`, `LMN 1`, and `IMP 100` (Cp-G), each sweep step produces **6 data items** in the output buffer:

| Item | Type code | Content                            |
|------|-----------|------------------------------------|
| 1    | `T`       | Timestamp (seconds since TSR)      |
| 2    | `C`       | Para1 = Cp (Farads)                |
| 3    | `Y`       | Para2 = G (Siemens)                |
| 4    | `V`       | Monitor: oscillator level (V)      |
| 5    | `V`       | Monitor: DC bias (V)               |
| 6    | `V`       | Source data = sweep bias (V)       |

Each item is 15-16 characters in FMT 1/5: a 3-char header (`status + channel + type`) followed by a 12-char scientific notation value, then the terminator (comma or CR/LF depending on FMT).

The type codes are determined by the `IMP` command setting. With `IMP 100` (Cp-G), Para1 is reported with type `C` and Para2 with type `Y`. Different IMP modes produce different type codes (see Table 4-16 in the Programmer's Guide, page 4-29).

Without `LMN 1` (monitor data disabled), each step produces only 4 items: Time, Para1, Para2, Source.

Without `TSC 1` (timestamp disabled), the Time item is omitted.

---

## Comparison: Current Blocking Implementation vs. Live Streaming

### Current flow (cv_sweep.py + bindings.py)

```
Python                          DLL                         B1500 Instrument
------                          ---                         ----------------
b1500.set_cv(...)          -->  agb1500_setCv()        -->  WDCV, WTDCV, WMDCV
b1500.sweep_cv(...)        -->  agb1500_sweepCv()      -->  XE + *OPC? (blocks)
  |                               |                           measuring step 1...
  |  (thread blocked)             |  (blocked on GPIB read)   measuring step 2...
  |                               |                           ...
  |                               |                           measuring step N...
  |                               |                           *OPC? -> "1"
  |                               |  <-- bulk read all data
  |  <-- returns arrays           |
  |
  runner.add_live_series(...)     <-- plots everything at once (not live)
```

### Desired flow (live streaming via SCPI)

```
Python                          VISA (direct SCPI)          B1500 Instrument
------                          ------------------          ----------------
visa_write("WDCV ...")                                 -->  configure sweep
visa_write("FMT 5,0")                                 -->  comma terminator
visa_write("XE")                                       -->  start sweep
  |
  for each step:
    visa_read(comma-terminated)  <-------- step 1 data <--  step 1 done
    parse + add_live_point()
    visa_read(comma-terminated)  <-------- step 2 data <--  step 2 done
    parse + add_live_point()
    ...
```

### What the four_terminal_iv_sweep.py already does

The four-terminal IV sweep uses the DLL's streaming API (`agb1500_startMeasure` + `agb1500_readData`) which works the same way but is only available for SMU-based measurements. The CMU has no equivalent DLL streaming function, so we must drop to raw SCPI for CV sweeps.

---

## Key SCPI Commands Reference

| Command | Purpose | Programmer's Guide Page |
|---------|---------|------------------------|
| `FMT`   | Set data output format and terminator | 4-118 |
| `TSC`   | Enable/disable timestamp output | (see TSC) |
| `TSR`   | Reset timestamp counter | (see TSR) |
| `MM`    | Set measurement mode (18 = CV DC bias sweep) | (see MM) |
| `IMP`   | Select impedance measurement parameter (e.g. 100 = Cp-G) | Table 4-16, 4-29 |
| `LMN`   | Enable/disable monitor data output (osc level, DC bias) | (see LMN) |
| `FC`    | Set MFCMU AC frequency | (see FC) |
| `ACV`   | Set MFCMU AC oscillator level | (see ACV) |
| `ACT`   | Set MFCMU ADC integration mode and value | (see ACT) |
| `RC`    | Set MFCMU measurement range | (see RC) |
| `WDCV`  | Define DC bias sweep source (channel, mode, start, stop, steps) | 4-230 |
| `WTDCV` | Set CV sweep timing (hold, delay, step delay) | (see WTDCV) |
| `WMDCV` | Set auto-abort and post-sweep output | (see WMDCV) |
| `XE`    | Trigger/execute measurement | (see XE) |
| `*OPC?` | Query operation complete (blocks until done) | (see *OPC?) |
| `NUB?`  | Query number of data items in output buffer | (see NUB?) |
| `DZ`    | Force 0V on all channels and memorize settings | (see DZ) |
| `ADJ`   | Phase compensation | (see ADJ) |
| `CORR?` | Open/short/load correction | (see CORR?) |

---

## IMP Mode Codes (Table 4-16)

These determine what Para1 and Para2 mean in the measurement output:

| Code | Para1 | Para2 | Model |
|------|-------|-------|-------|
| 1    | R     | X     | Series impedance |
| 2    | G     | B     | Parallel admittance |
| 10   | Z     | Theta (rad) | Impedance polar |
| 11   | Z     | Theta (deg) | Impedance polar |
| 100  | Cp    | G     | Parallel capacitance + conductance |
| 101  | Cp    | D     | Parallel capacitance + dissipation |
| 200  | Cs    | Rs    | Series capacitance + resistance |
| 201  | Cs    | D     | Series capacitance + dissipation |
| 300  | Lp    | G     | Parallel inductance + conductance |
| 400  | Ls    | Rs    | Series inductance + resistance |

---

## Notes

- The DLL functions for CMU setup (`agb1500_setCmuFreq`, `agb1500_forceCmuAcLevel`, `agb1500_setCmuInteg`, `agb1500_setCv`) can still be used for configuration. Only the sweep execution + data read needs to bypass the DLL.
- Alternatively, all setup can also be done via raw SCPI for full control.
- The `NUB?` command can be used to check how many data items are in the output buffer at any time, which is useful for verification after streaming.
- Error checking with `ERR?` or `ERRX?` should be done after the sweep completes, not during streaming (it can hang the instrument mid-measurement).
