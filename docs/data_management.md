# Data management

Open **Data Management…** between the Selection and Temperature sections. The browser uses
the selected output directory as its data source; changing chips in the browser does not change
the chip or site selected for a measurement run.

The left two-thirds show the whole sample using the loaded `devices.csv`, with a
searchable chip picker in the top-left. Measured sites have tinted boxes and their
total measurement count inside. Small green/yellow/red badges count devices assessed
Good/OK/Bad, including assessments made before measuring. Unmeasured regions stay
neutral and have no measurement count.
Scroll to reveal subsite outlines, then device markers. Double-click a region to
zoom to it, right- or middle-drag to pan, and use **Fit View** to restore the overview.
Click the canvas to use arrow keys for panning; hold Shift for larger steps.
Click a region to select its devices; click or drag over devices to select them.
Ctrl+Click toggles selection. A blue outline indicates selection. With no devices
selected, the gallery shows the whole chip's measurements.

Subsites show the same measurement and assessment totals as they come into view.
Device colors and counts appear as soon as their markers become visible. Region
totals include separate histories at shared coordinates and data from unpositioned
devices within that site or subsite. Names, dates, notes, and selection details
appear in hover tooltips, keeping the canvas free of floating labels. Hover the
info icon for navigation help and the color key for the meaning of the indicators.
Hidden and off-screen devices do not receive position updates.

Devices missing from the layout or lacking absolute coordinates appear in a small
list below the map. The other devices remain on the canvas. If none have positions,
the browser uses a list with Site, Subsite, Device, and Status columns. You can also
choose **List View** at any time.

Devices at exactly the same coordinates share one marker. Selecting it shows the
combined measurement gallery. Unmeasured devices are empty circles; measured
devices are filled, with their count inside. Untagged devices use black and white
numbers. Tagged devices use their assessment color, with white numbers on green
or red and black numbers on yellow. Shared markers with differing assessments use
colored rings when unmeasured and filled sectors when measured. Zero measurement
counts are omitted. Nearby coordinates remain separate. Subsites sharing device
locations share an outline. Hover a marker for device names, comma-separated
subsites, latest measurement date, assessments, and saved notes.

## Device notes and status

Select one device to edit its notes and assessment. For a merged marker, choose
its individual subsite/device from the notes editor's dropdown; the gallery keeps
showing the combined history. Each member's notes and assessment remain separate.
The optional assessments are
**Good** (green), **OK** (yellow), and **Bad** (red); **Clear** removes the assessment.
These assessments are independent of the tags in `devices.csv`, which this
feature does not change. An assessment does not exclude a device from measurement.

Notes are saved automatically shortly after editing, when the editor loses focus,
and before changing selections, opening artifacts, applying corrections, or closing.
If saving fails, the unsaved text stays in the editor and selection changes and
closing are blocked until it can be saved.

Each physical device uses an ordinary text file:

```text
<output directory>/<chip>/<site>/<subsite>/<device>/notes.txt
```

```text
Status: Bad

Leaky after the last fatigue run.
```

Existing notes without a recognized first `Status:` line are kept as free text.
The status can also be recorded before taking any measurements.

The regular **Device Selection…** dialog reads the same notes and assessments.
Status labels and colors appear on its markers, and an asterisk indicates notes;
hover to read them. If several selected sites have different assessments for the
same device name, the label says **Mixed**, and hovering shows each site's status.

## Measurement gallery

The right-hand gallery uses compact rows, with plot thumbnails beside the procedure,
timestamp, and device path, newest first. A plain click selects a measurement;
double-click opens its plot in the associated image application. Ctrl+Click
(or Command+Click on macOS) toggles selection; Shift+Click selects a range.
Ctrl+A or Command+A selects the gallery.
The gallery is paginated to avoid loading every image into memory.

Right-click a measurement for **Open Data**, **Open Plot**, or
**Correct Assignment…**. A WGFMU sampling run's combination CSVs and shared plot
are treated as one measurement, so they move together.

A warning popup reports missing identity metadata or disagreements between a
CSV's Chip/Site/Subsite/Device header and its containing directory. Warnings are
shown together and do not repeat for every click; **Show Warning…** reopens the
details from a measurement's context menu.

## Correcting an assignment

Use **Correct Assignment…** for selected gallery measurements. To correct all data
for some devices, select those devices on the canvas, click a gallery row, and use
Ctrl+A (Command+A on macOS) to select all their measurements, including other pages.
Corrections apply to the selected measurement data and plots.

Enter the correct Chip, Site, Subsite, or Device names. Blank fields retain each
file's existing directory identity. **Preview Changes** lists the destination of
every file and the corrected identity for each CSV header. Editing a field
invalidates that preview; **Apply Changes** becomes available after previewing.
Keeping the fields unchanged also repairs mismatched or missing CSV headers.

Corrections change the identity prefix of standard measurement filenames while
preserving timestamps, temperature, procedure names, and combination suffixes.
Data and plots are kept together. Other CSV metadata and numeric data are preserved.
Unrecognized filenames are retained, with their destination visible in the preview.

Notes and other device-folder contents stay attached to their original device.
Existing destinations and collisions within a batch are rejected; files are never
silently overwritten. Changed source files invalidate the preview.
Corrections stage originals and restore them if an operation fails. If recovery
itself fails, the error gives the location of the retained originals.

File correction is unavailable during a measurement run. No extra pre-run
chip/site reminder is added.
