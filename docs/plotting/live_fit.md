# Live-Fit Notes

These are the current plotting rules for streamed plots in the DearPyGui viewer.

## What We Learned

- Leaving a DearPyGui axis at `auto_fit=True` is wrong for live measurements.
  The plot keeps hugging the newest data and normal pan/zoom never really takes over.
- `fit_axis_data(...)` was not reliable enough for the mixed linear/log streaming case we
  use in `OxideBreakdown`, especially on the secondary log axis.
- The viewer already mirrors every source locally, so using that mirrored data as the
  source of truth for live bounds is the simplest stable option.

## Current Behavior

- Axes with explicit `xlim` / `ylims` stay fixed.
- Axes without explicit limits are live-fit from the mirrored curve data.
- Linear axes get an 8% margin around the data span.
- Log axes get a multiplicative margin of 8% in log space, with a minimum of 0.2 decades.
- DearPyGui `set_axis_limits(...)` is only used to move the current view for the current
  frame. The viewer then calls `set_axis_limits_auto(...)` on the next frame so those
  bounds do not remain as hard pan/zoom limits.
- If the visible axis limits stop matching the last auto-fit limits the viewer set,
  live-fitting is disabled for that plot until the next `configure(...)`.
- The viewer does not need a custom mouse-wheel handler for this; DearPyGui keeps the
  native plot zoom/pan behavior.

## OxideBreakdown-Specific Notes

- The secondary `log |I|` axis is now a real log axis.
- `log_I` is streamed point-by-point during acquisition instead of being appended in one
  bulk update after the sweep ends.
- This avoids the late end-of-sweep redraw that used to make the plot jump.
