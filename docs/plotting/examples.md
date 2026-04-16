# Plotting examples

## RV sweep (single axis, single series)

```python
runner.plot.configure(title=f"R-V Sweep - {device.name}", plots=[
    PlotDef("rv", xlabel="Voltage (V)", ylabels=("Current (A)",),
            elements=[
                Curve("I_V", label="I(V)"),
            ]),
])

for v, i in zip(voltages, currents):
    runner.plot.append("I_V", v, i)

runner.plot.save(plot_filename, output_root, output_relative, fallback_root)
```

## 4-terminal IV (scatter + live fit)

```python
runner.plot.configure(title=f"4-Term IV - {device.name}", plots=[
    PlotDef("iv", xlabel="Current (A)", ylabels=("Voltage (V)",),
            elements=[
                Curve("V_I", marker="x", linestyle=None, color="C0", label="V(I)"),
                LinearFit("V_I", color="C1",
                          label="R = {slope:.4g} Ohm  (R^2 = {r_squared:.4f})"),
            ]),
])

for idx in range(num_points):
    runner.check_stop()
    # ... perform measurement ...
    runner.plot.append("V_I", current, voltage)

# read fit result for data output
ds = runner.plot.source("V_I")
fit = stats.linear_fit(ds.x, ds.y)
save_to_csv(resistance=fit.slope, r_squared=fit.r_squared)

runner.plot.save(plot_filename, output_root, output_relative, fallback_root)
```

## Oxide breakdown (two y-axes, post-sweep derived series)

```python
runner.plot.configure(title=f"Oxide Breakdown - {device.name}", plots=[
    PlotDef("bd", xlabel="Voltage (V)",
            ylabels=("Current (A)", "log |I| (A)"),
            yscales=("linear", "log"),
            elements=[
                Curve("I_pos", color="C0", label="I+(V)"),
                Curve("I_neg", color="C1", label="-I-(V)"),
                Curve("log_I", color="k", linestyle="--", yaxis=1, label="log(I)"),
            ]),
])

for v, i_hi, i_lo in measurements:
    runner.plot.append("I_pos", v, i_hi)
    runner.plot.append("I_neg", v, -i_lo)

# compute log magnitude and add as bulk array at the end
log_vals = [max(abs(i), 1e-15) for i in all_currents]
runner.plot.append("log_I", all_voltages, log_vals)

runner.plot.save(plot_filename, output_root, output_relative, fallback_root)
```

## CV sweep (dual axis, multiple frequencies, color = frequency)

```python
colors = ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]
elements = []
for i, freq in enumerate(frequencies):
    color = colors[i % len(colors)]
    tag = freq_label(freq)
    elements.append(Curve(f"Cp_{tag}", color=color, label=f"Cp @ {tag}"))
    elements.append(Curve(f"Td_{tag}", color=color, linestyle="--",
                          yaxis=1, label=f"Tan(d) @ {tag}"))

runner.plot.configure(title=f"C-V Sweep - {device.name}", plots=[
    PlotDef("cv", xlabel="Bias (V)",
            ylabels=("Capacitance (F)", "Tan(delta)"),
            elements=elements),
])

# during sweep
runner.plot.append(f"Cp_{tag}", bias, capacitance)
runner.plot.append(f"Td_{tag}", bias, tan_delta)

runner.plot.save(plot_filename, output_root, output_relative, fallback_root)
```

## PUND fatigue (dual axis, color gradient = cycle progression)

```python
elements = []
for i, cyc in enumerate(cycle_indices):
    t = i / max(len(cycle_indices) - 1, 1)
    show_legend = (i == 0 or i == len(cycle_indices) - 1)
    elements.append(Curve(f"V_{cyc}", color=(0, 0, t), linewidth=0.8,
                          label=f"V(cyc {cyc})" if show_legend else ""))
    elements.append(Curve(f"I_{cyc}", color=(t, 0.3 * t, 0), linewidth=0.8,
                          yaxis=1,
                          label=f"I(cyc {cyc})" if show_legend else ""))

runner.plot.configure(title=f"PUND Fatigue - {device.name}", plots=[
    PlotDef("pund", xlabel="Time (s)",
            ylabels=("Voltage (V)", "Current (uA)"),
            xlim=(0, pattern_duration),
            ylims=((-vmax - margin, vmax + margin), None),
            elements=elements),
])

# stream bulk arrays per cycle
runner.plot.append(f"V_{cyc}", times, voltages)
runner.plot.append(f"I_{cyc}", times, currents_ua)

runner.plot.save(plot_filename, output_root, output_relative, fallback_root)
```

## WGFMU sampling (curve + live histogram sidebar)

```python
runner.plot.configure(title="WGFMU Sampling", plots=[
    PlotDef("main", row=0, col=0,
            xlabel="Time (s)", ylabels=("Current (A)",),
            xlim=(0.0, sampling_duration),
            elements=[
                Curve("I1", color="C0", label="I1(t)"),
                Curve("I2", color="C1", label="-I2(t)"),
            ]),
    PlotDef("hist", row=0, col=1,
            xlabel="Count", ylabels=("Current (A)",),
            elements=[
                Histogram("I1", color="C0", orientation="horizontal"),
                Histogram("I2", color="C1", orientation="horizontal"),
            ]),
])

# during sampling (downsampled buckets)
runner.plot.append("I1", bucket_time, bucket_i1)
runner.plot.append("I2", bucket_time, bucket_i2)

# histogram updates live alongside the curves

runner.plot.save(plot_filename, output_root, output_relative, fallback_root)
```

## Grid layout with linked x-axes

```python
runner.plot.configure(title="Multi-panel Analysis", plots=[
    PlotDef("iv", row=0, col=0,
            xlabel="Voltage (V)", ylabels=("Current (A)",),
            elements=[Curve("I_V", label="I(V)")]),
    PlotDef("cv", row=0, col=1,
            xlabel="Voltage (V)", ylabels=("Capacitance (F)",),
            xlink="iv",
            elements=[Curve("C_V", label="C(V)")]),
    PlotDef("endurance", row=1, col=0, colspan=2,
            xlabel="Cycle", ylabels=("2Pr (uC/cm2)",),
            elements=[
                Curve("Pr", marker="o", label="2Pr"),
                LinearFit("Pr", color="C1", label="trend: {slope:.2g}/cycle"),
            ]),
])
```
