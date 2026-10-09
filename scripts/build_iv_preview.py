"""Generate an offline interactive preview from actual simulated procedure runs.

Run from the repository root: python -m scripts.build_iv_preview
The instrument is never opened. The production procedures write every CSV.
"""
from dataclasses import asdict
import itertools
import json
from pathlib import Path
import tempfile

from procedures.i_sweep import ISweepProcedure
from procedures.v_sweep import VSweepProcedure
from scripts.iv_simulator import simulate


def build_cases():
    cases = []
    for cls, sensing, low, symmetric, pattern, condition in itertools.product(
            (ISweepProcedure, VSweepProcedure), ('None', 'High only', 'Low only', 'Both'),
            ('SMU', 'GNDU'), (False, True), ('Single', 'Return', 'Butterfly'),
            ('normal', 'compliance', 'interrupted')):
        if symmetric and (cls is ISweepProcedure or low == 'GNDU'):
            continue
        settings = dict(points=7, sweep_pattern=pattern,
                        sense_high=5 if sensing in ('High only', 'Both') else None,
                        sense_low=6 if sensing in ('Low only', 'Both') else None,
                        low_channel=3 if low == 'SMU' else 'GNDU')
        if cls is VSweepProcedure:
            settings.update(symmetric_terminals=symmetric, start_voltage=-1.2, v_max=1.2)
        else:
            settings.update(start_current=-.001, stop_current=.001)
        with tempfile.TemporaryDirectory() as directory:
            procedure, runner, instrument, csv, error = simulate(cls, settings, directory, condition)
        plan = procedure.plan()
        cases.append(dict(procedure=cls.NAME, sensing=sensing, low=low, symmetric=symmetric,
                          pattern=pattern, condition=condition, csv=csv, error=error,
                          plots=[asdict(p) for p in runner.plots], sources=runner.plot.sources,
                          quantities={name: asdict(q) for name, q in plan.csv_quantities.items()},
                          measurements=[asdict(m) for m in plan.measurements],
                          segments=[list(c[1][1:]) for c in instrument.calls if c[0] == 'set_iv_sweep']))
    return cases


def main():
    root = Path(__file__).resolve().parents[1]
    cases = build_cases()
    template = Path(__file__).with_name('iv_preview_template.html').read_text()
    output = root / 'docs' / 'iv_sweep_preview.html'
    payload = json.dumps(cases, separators=(',', ':'), allow_nan=False).replace('</', '<\\/')
    output.write_text(template.replace('/*CASES*/[]', payload))
    print(f'{output}: {len(cases)} simulated runs; {output.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
