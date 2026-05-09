#!/usr/bin/env python3
"""Validate and explain a devices CSV file."""

import argparse
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models import compile_devices_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a devices CSV and report how sites, subsites, devices, reused rows, and position changes are interpreted."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=os.path.join(ROOT, "saved_configs", "devices.csv"),
        help="Path to the devices CSV. Defaults to saved_configs/devices.csv.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every decision made while reading the file.",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Print the full expanded tree.",
    )
    parser.add_argument(
        "--explain",
        metavar="PATH",
        help="Explain one path, such as S01, S01/FeCap, or S01/FeCap/D01.",
    )
    args = parser.parse_args()

    compilation = compile_devices_csv(args.csv_path)
    print(f"Reading: {compilation.csv_path}")
    print()

    if compilation.errors:
        print("The CSV could not be loaded.")
        print()
        print("Errors:")
        for error in compilation.errors:
            print(f"  - {error}")
        return 1

    _print_summary(compilation)
    _print_overrides(compilation)
    _print_shared_positions(compilation)
    _print_warnings(compilation)

    if args.explain:
        _print_explain(compilation, args.explain)

    if args.tree:
        _print_tree(compilation)

    if args.verbose:
        _print_decisions(compilation)

    return 0


def _print_summary(compilation):
    stats = compilation.stats
    print("Result:")
    print(f"  {stats['sites']} sites were created.")
    print(f"  {stats['subsites']} subsites were created.")
    print(f"  {stats['devices']} devices were created.")
    print(f"  {stats['subsite_template_rows']} reusable subsite definitions were read.")
    print(f"  {stats['device_template_rows']} reusable device definitions were read.")
    print(f"  {stats['overrides']} overrides were applied.")
    print(f"  {stats['shared_positions']} shared device positions were found.")
    print(f"  {stats['warnings']} warnings were found.")
    print("  0 conflicts were found.")
    print()


def _print_overrides(compilation):
    if not compilation.overrides:
        return
    print("Overrides:")
    for override in compilation.overrides:
        print(f"  - {override}")
    print()


def _print_shared_positions(compilation):
    if not compilation.shared_positions:
        return
    print("Shared Positions:")
    print("  These are allowed. They mean multiple measurement targets use the same probe position.")
    for shared in compilation.shared_positions:
        print(f"  - {shared}")
    print()


def _print_warnings(compilation):
    if not compilation.warnings:
        return
    print("Warnings:")
    for warning in compilation.warnings:
        print(f"  - {warning}")
    print()


def _print_explain(compilation, path: str):
    parts = [part for part in path.split("/") if part]
    print(f"Explain: {path}")
    if len(parts) == 1:
        site = _find_site(compilation, parts[0])
        if not site:
            print("  No loaded site matched this path.")
        else:
            print(f"  Site {site.name}: local ({site.x:g}, {site.y:g}), rows {_rows(site.source_rows)}")
            _print_tags(site.tags)
    elif len(parts) == 2:
        site = _find_site(compilation, parts[0])
        subsite = _find_subsite(site, parts[1]) if site else None
        if not subsite:
            print("  No loaded subsite matched this path.")
        else:
            print(
                f"  Subsite {site.name}/{subsite.name}: local ({subsite.x:g}, {subsite.y:g}), "
                f"absolute ({subsite.absolute_x:g}, {subsite.absolute_y:g}), rows {_rows(subsite.source_rows)}"
            )
            _print_tags(subsite.tags)
    elif len(parts) == 3:
        site = _find_site(compilation, parts[0])
        subsite = _find_subsite(site, parts[1]) if site else None
        device = _find_device(subsite, parts[2]) if subsite else None
        if not device:
            print("  No loaded device matched this path.")
        else:
            print(
                f"  Device {site.name}/{subsite.name}/{device.name}: local ({device.x:g}, {device.y:g}), "
                f"absolute ({device.absolute_x:g}, {device.absolute_y:g}), rows {_rows(device.source_rows)}"
            )
            _print_tags(device.tags)
    else:
        print("  Use Site, Site/Subsite, or Site/Subsite/Device.")
    print()


def _print_tree(compilation):
    print("Expanded Tree:")
    if not compilation.sites:
        print("  No sites were created.")
        print()
        return
    for site in compilation.sites:
        print(f"  {site.name} at ({site.x:g}, {site.y:g})")
        for subsite in site.subsites:
            print(
                f"    {subsite.name} at local ({subsite.x:g}, {subsite.y:g}), "
                f"absolute ({subsite.absolute_x:g}, {subsite.absolute_y:g})"
            )
            for device in subsite.devices:
                tag_text = f" tags={';'.join(sorted(device.tags))}" if device.tags else ""
                print(
                    f"      {device.name} at local ({device.x:g}, {device.y:g}), "
                    f"absolute ({device.absolute_x:g}, {device.absolute_y:g}){tag_text}"
                )
    print()


def _print_decisions(compilation):
    print("Reading Decisions:")
    if not compilation.decisions:
        print("  No decisions were recorded.")
    for decision in compilation.decisions:
        print(f"  - {decision}")
    print()


def _print_tags(tags):
    if tags:
        print(f"  Tags: {';'.join(sorted(tags))}")


def _find_site(compilation, name):
    return next((site for site in compilation.sites if site.name == name), None)


def _find_subsite(site, name):
    if not site:
        return None
    return next((subsite for subsite in site.subsites if subsite.name == name), None)


def _find_device(subsite, name):
    if not subsite:
        return None
    return next((device for device in subsite.devices if device.name == name), None)


def _rows(rows):
    return ", ".join(str(row) for row in rows) if rows else "implicit"


if __name__ == "__main__":
    raise SystemExit(main())
