"""Discover independent procedure files when the application starts."""

import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_procedures(on_error=None):
    """Load one locally defined MeasurementProcedure subclass per public .py file.

    Each procedure supplies its own NAME, PARAMETERS, measurement and optional
    UI_ACTIONS. Shared support belongs in base.py or private modules. Import
    errors and duplicate names are logged without preventing other files loading.
    """
    from .base import MeasurementProcedure

    procedures = {}
    for path in sorted(Path(__file__).parent.glob('*.py'), key=lambda p: p.name.casefold()):
        if path.name == 'base.py' or path.name.startswith('_'):
            continue
        try:
            module = importlib.import_module(f'{__name__}.{path.stem}')
            classes = [
                value for value in vars(module).values()
                if isinstance(value, type)
                and value.__module__ == module.__name__
                and issubclass(value, MeasurementProcedure)
                and value is not MeasurementProcedure
            ]
            if len(classes) != 1:
                raise ValueError('expected exactly one locally defined MeasurementProcedure subclass')
            procedure = classes[0]
            if (procedure.measure is MeasurementProcedure.measure
                    and procedure.run is MeasurementProcedure.run):
                raise ValueError('procedure must implement measure(device) or run(b1500, device)')
            name = procedure.procedure_name()
            if not isinstance(name, str) or not name.strip():
                raise ValueError('procedure name must be a nonempty string')
            if name in procedures:
                raise ValueError(f'duplicate procedure name {name!r}')
            # Catch broken form declarations before offering the procedure.
            procedure.ui_fields()
            procedure.ui_defaults()
            procedure.ui_actions()
            procedures[name] = procedure
        except Exception as exc:
            message = f'Could not load procedure {path.name}: {exc}'
            logger.exception(message)
            if on_error is not None:
                on_error(message)
    return dict(sorted(procedures.items(), key=lambda item: item[0].casefold()))
