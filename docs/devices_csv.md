# Devices CSV Tutorial

The devices CSV tells the app what can be measured and where the prober should
move. The GUI shows it as a tree:

```text
Site -> Subsite -> Device
```

The most important columns are always:

```csv
Site,Subsite,Device,X,Y
```

`X` and `Y` are micrometer coordinates. `X` increases to the right, and `Y`
increases up:

```text
             +Y
              ^
              |
              |
              o------> +X
```

## The Simplest File

The simplest format is one row per device:

```csv
Site,Subsite,Device,X,Y
S01,FeCap,A1,0,0
S01,FeCap,A2,100,0
S01,FeCap,A3,200,0
S01,FeCap,A4,300,0
```

This creates one site called `S01`, one subsite called `FeCap`, and four devices.
The app reads it as:

```text
S01
  FeCap
    A1 at (0, 0)
    A2 at (100, 0)
    A3 at (200, 0)
    A4 at (300, 0)
```

The `Device` column names a measurement target. It does not have to be a single
physical object on the chip. Multiple device rows may also use the same position. 

## Adding Site Coordinates

A row with only `Site`, `X`, and `Y` gives a site a position:

```csv
Site,Subsite,Device,X,Y
S01,,,1000,2000
S01,FeCap,A1,0,0
S01,FeCap,A2,100,0
```

This means:

```text
S01 is at (1000, 2000)
FeCap has no subsite offset, so it is at (0, 0) inside S01
A1 is at (0, 0) inside FeCap
A2 is at (100, 0) inside FeCap
```

The target position for `S01/FeCap/A2` is:

```text
site position + subsite position + device position
= (1000, 2000) + (0, 0) + (100, 0)
= (1100, 2000)
```

If no site coordinate row is given, the site position is treated as `(0, 0)`.

Site coordinate rows are also a convenient way to list the relative positions of
sites on a chip. They do not create subsites by themselves.

```csv
Site,Subsite,Device,X,Y
S01,,,0,0
S02,,,2000,0
S03,,,0,2000
S04,,,2000,2000
```

This creates four empty sites:

```text
S01 at (0, 0)
S02 at (2000, 0)
S03 at (0, 2000)
S04 at (2000, 2000)
```

## Adding Subsite Coordinates

A row with `Site`, `Subsite`, `X`, and `Y`, but no `Device`, gives that subsite
a position inside that site:

```csv
Site,Subsite,Device,X,Y
S01,FeCap,,1000,2000
S01,FeCap,A1,0,0
S01,FeCap,A2,100,0
```

This creates:

```text
S01
  FeCap at (1000, 2000)
    A1 at (0, 0), target position (1000, 2000)
    A2 at (100, 0), target position (1100, 2000)
```

This is useful when the same subsite shape appears at different places on the
chip.

## Reusing The Same Devices In Many Sites

Often, many sites contain the same subsite layout. You can define the devices
once, then list where that subsite appears.

Rows with an empty `Site` and a filled `Subsite` and `Device` define devices for
any subsite with that name:

```csv
Site,Subsite,Device,X,Y
,FeCap,A01,0,0
,FeCap,A02,100,0
,FeCap,A03,200,0
,FeCap,A04,300,0
,FeCap,A05,400,0
,FeCap,A06,0,100
,FeCap,A07,100,100
,FeCap,A08,200,100
,FeCap,A09,300,100
,FeCap,A10,400,100
S01,,,0,0
S02,,,2000,0
S03,,,4000,0
S04,,,6000,0
S05,,,8000,0
S06,,,0,2000
S07,,,2000,2000
S08,,,4000,2000
S09,,,6000,2000
S10,,,8000,2000
S01,FeCap,,100,100
S02,FeCap,,100,100
S03,FeCap,,100,100
S04,FeCap,,100,100
S05,FeCap,,100,100
S06,FeCap,,100,100
S07,FeCap,,100,100
S08,FeCap,,100,100
S09,FeCap,,100,100
S10,FeCap,,100,100
```

This creates 10 sites. Each site gets one `FeCap` subsite. Each `FeCap` subsite
gets the same 10 devices.

The expanded result is equivalent to writing all 100 device rows by hand, but
the CSV stays short and easier to edit.

## Reusing A Subsite Position

A row with an empty `Site`, a filled `Subsite`, and no `Device` gives a default
position to every subsite with that name:

```csv
Site,Subsite,Device,X,Y
,FeCap,,1000,2000
,FeCap,A1,0,0
,FeCap,A2,100,0
S01,FeCap,A3,200,0
S02,FeCap,A3,200,0
```

Both `S01/FeCap` and `S02/FeCap` use the `FeCap` subsite position `(1000,
2000)`. The explicit device rows for `A3` create the two concrete subsites.
The device rows for `A1` and `A2` are then reused inside both.

## Changing One Site Or Device

You can define the common case once and then change one specific site or device.

```csv
Site,Subsite,Device,X,Y
,FeCap,,1000,2000
,FeCap,A1,0,0
,FeCap,A2,100,0
S01,FeCap,,1200,2000
S02,FeCap,,1000,2000
S01,FeCap,A1,10,0
```

This means:

```text
Most FeCap subsites use position (1000, 2000)
S01/FeCap uses position (1200, 2000)
Most A1 devices inside FeCap use position (0, 0)
S01/FeCap/A1 uses position (10, 0)
```

The more specific row wins for that one place.

## Tags

You may add a `Tags` column:

```csv
Site,Subsite,Device,X,Y,Tags
S01,FeCap,A1,0,0,25um;normal
S01,FeCap,A2,100,0,25um;normal
S01,FeCapBD,A1A2,50,0,breakdown;oxide
```

Tags are saved on the loaded objects for future use. The current GUI does not
filter or run by tag yet.

## Rules To Remember

- `X` and `Y` are required on every non-empty row.
- A device must belong to a subsite.
- A row with `Site,Subsite,Device` filled defines one exact measurement target.
- A row with empty `Site` can define something reusable for every subsite with
  that name.
- Site-only rows define site positions.
- A row with empty `Device` defines a site or subsite position.
- The order of rows does not matter.
- More specific rows can change the position from a more general row.
- The same exact site, subsite, or device path cannot be defined twice with
  different coordinates.

## Advanced Details

The app first turns the CSV into a fully explicit tree. After that step, the GUI
and runner no longer care which rows were reused and which rows were written out
explicitly.

Coordinates are added by level:

```text
target position = site position + subsite position + device position
```

If a site or subsite was only implied by a device row, its position is `(0, 0)`.

Internally, the probe station moves the chuck, not the drawn coordinate system.
That hardware convention is opposite to the user-facing chip coordinates above.
The app handles this when loading the CSV, so you should write coordinates in
the natural chip convention: `X` to the right and `Y` up.

Rows with the same exact meaning and the same coordinates are allowed. Their
tags are combined. Rows with the same exact meaning and different coordinates
are conflicts.

This is a conflict:

```csv
Site,Subsite,Device,X,Y
S01,FeCap,A1,0,0
S01,FeCap,A1,10,0
```

This is not a conflict:

```csv
Site,Subsite,Device,X,Y
,FeCap,A1,0,0
S01,FeCap,A1,10,0
```

The second file says: use `(0, 0)` for `A1` in most `FeCap` subsites, but use
`(10, 0)` for `S01/FeCap/A1`.

## Checking A File

Use the validation script to check what the app will load:

```bash
python scripts/validate_devices_csv.py saved_configs/devices.csv
```

Print the full expanded tree:

```bash
python scripts/validate_devices_csv.py saved_configs/devices.csv --tree
```

Explain one path:

```bash
python scripts/validate_devices_csv.py saved_configs/devices.csv --explain S01/FeCap/A01
```

Print every decision made while reading the file:

```bash
python scripts/validate_devices_csv.py saved_configs/devices.csv --verbose
```

The script reports errors, position changes from more specific rows, unused
reusable rows, and shared probe positions.
