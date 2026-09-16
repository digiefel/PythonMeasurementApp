# Van der Pauw

Select **VanDerPauw** in the procedure selector. The four SMU selectors are:

| Contact | Default |
|---|---|
| TL (top left) | SMU1 |
| TR (top right) | SMU2 |
| BL (bottom left) | SMU3 |
| BR (bottom right) | SMU4 |

The procedure runs all eight sweeps automatically. Leave the defaults unless the
wiring differs. Plot titles and CSV entries use the selected SMU numbers.

**Ibias** sets the sweep limits: -Ibias to +Ibias. The default is 1 µA with
75 points. Even point counts also work. Set compliance and settling times for
the sample.

With the default wiring:

| Current flows from | Measured voltage |
|---|---|
| SMU1 to SMU2 | V_3 − V_4 |
| SMU2 to SMU4 | V_1 − V_3 |
| SMU4 to SMU3 | V_2 − V_1 |
| SMU3 to SMU1 | V_4 − V_2 |

Each row also runs with the current contacts exchanged and the voltage contacts
exchanged. For example, `1->2 / V3-V4` is followed by `2->1 / V4-V3`, both swept
from -Ibias to +Ibias. This changes which SMU holds 0 V while keeping the sign of
the resistance the same. There are eight sweeps in total.

Each sweep is fitted as `V = R*I + b`, using measured current. R is the slope;
b is the fitted voltage at zero current. The four slopes from the top and bottom
current pairs are averaged into RA. The four from the right and left pairs are
averaged into RB. Sheet resistance Rs is found by solving
`exp(-pi RA/Rs) + exp(-pi RB/Rs) = 1`.

Each small plot overlays the two current directions, with a legend showing the
SMU numbers. Its `dR` value is their signed resistance difference as a percentage
of their mean magnitude. Red crosses mark instrument flags. Differences between
opposite edges are also saved and logged, without a pass/fail threshold.

The main plot shows the results before and after exchanging contacts as two
separate sets of points. Each point uses the voltage difference between +I and -I
to remove a constant voltage contribution. The horizontal line is the result
from all eight fitted slopes, averaged before solving for Rs. Keeping the two
sets of points visible shows differences that averaging alone would hide.

The procedure does not grade the data or reject flagged readings from the fit.
Only NaN and infinity are omitted from calculations. Results that cannot be
calculated are recorded as NaN. All measured values and instrument flags are saved.

A completed run saves **one CSV and one plot PNG**. The CSV contains the raw
readings, with the sheet resistance, eight fitted slopes, fitted voltages at zero
current, R² values and settings in its comment header. There are no separate
summary, fit or positive/negative-current data files. If interrupted, the available
complete readings are saved in one `_partial.csv` instead. Abort/error instrument
cleanup is handled by the runner and connection.

The usual Van der Pauw interpretation assumes a uniform conducting sheet without
holes, uniform thickness and small ohmic contacts on its outside edge, at zero
magnetic field. Synthetic tests verify the calculation and software sequencing;
the actual instrument and wiring still need a lab test.

Reference: [NIST Van der Pauw technique](https://www.nist.gov/pml/nanoscale-device-characterization-division/popular-links/hall-effect/hall-effect).
