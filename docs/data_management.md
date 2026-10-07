# Data management

Open **Data Management…** between the Selection and Temperature sections. The browser uses
the selected output directory as its data source; changing chips in the browser does not change
the chip or site selected for a measurement run.

The left two-thirds show the whole sample using the loaded `devices.csv`, with a
searchable chip picker in the top-left. The overview shows filled site boxes.
Scroll to reveal subsite outlines, then device markers and their details as space
permits. Double-click a region to zoom to it, right- or middle-drag to pan, and use
**Fit View** to restore the overview. Hidden and off-screen devices do not receive
position updates. Click a region to select its devices; click or drag over devices
to select them. Ctrl+Click toggles selection. A blue outline indicates selection;
collapsed regions show how many of their devices are selected. With no devices selected, the gallery shows the
whole chip's measurements.

Devices missing from the layout or lacking absolute coordinates appear in a small
list below the map. The other devices remain on the canvas. If none have positions,
the browser uses a list with Site, Subsite, Device, and Status columns. You can also
choose **List View** at any time.

Devices at exactly the same coordinates share one marker. Selecting it shows the
combined measurement gallery. At close zoom the marker shows the total measurement
count inside, with names, comma-separated subsites, latest measurement date, and a
small notes indicator alongside it. Zero counts and absent dates are omitted.
Good/OK/Bad appear as colors; differing assessments use a segmented ring. Nearby
coordinates remain separate. Subsites sharing device locations share an outline.
Hovering a marker shows its compact details at smaller zooms.

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

The right-hand gallery shows saved plot thumbnails, procedure, timestamp, and
device path, newest first. A plain click selects a measurement and opens its plot
in the associated image application. Ctrl+Click (or Command+Click on macOS) toggles
selection; Shift+Click selects a range. Ctrl+A or Command+A selects the gallery.
The gallery is paginated to avoid loading every image into memory.

Right-click a measurement for **Open Data**, **Open Plot**, or
**Correct Assignment…**. A WGFMU sampling run's combination CSVs and shared plot
are treated as one measurement, so they move together.

A warning popup reports missing identity metadata or disagreements between a
CSV's Chip/Site/Subsite/Device header and its containing directory. Warnings are
shown together and do not repeat for every click; **Show Warning…** reopens the
details from a measurement's context menu.

## Correcting an assignment

Use **Correct Assignment…** for selected gallery measurements. For whole folders,
use **Correct Selected Device Folders…**, right-click a device or site on the map
or list, or right-click a chip in the chip picker. Chip, site, subsite, and device
folder scopes are supported.

Enter the correct Chip, Site, Subsite, or Device names. Blank fields retain each
file's existing directory identity. **Preview Changes** lists the destination of
every file and the corrected identity for each CSV header. Editing a field
invalidates that preview; **Apply Changes** becomes available after previewing.
Keeping the fields unchanged also repairs mismatched or missing CSV headers.

Corrections change the identity prefix of standard measurement filenames while
preserving timestamps, temperature, procedure names, and combination suffixes.
Data and plots are kept together. Other CSV metadata and numeric data are preserved.
Unrecognized filenames are retained, with their destination visible in the preview.

Whole-folder corrections include `notes.txt` and other device-folder contents.
Correcting individual measurements leaves the notes attached to their original
device. Existing destinations and collisions within a batch are rejected; files
are never silently overwritten. Changed source files invalidate the preview.
Corrections stage originals and restore them if an operation fails. If recovery
itself fails, the error gives the location of the retained originals.

File correction is unavailable during a measurement run. No extra pre-run
chip/site reminder is added.
