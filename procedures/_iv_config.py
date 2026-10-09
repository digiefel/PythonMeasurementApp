"""Translate old saved procedure names/settings without rewriting source files."""
from copy import deepcopy


def migrate_iv_config(data):
    procedures = deepcopy(data.get('procedures') or {})
    selection = data.get('last_selection', {})
    for old_name, new_name in (('IVSweep', 'Vsweep'), ('FourTerminalIV', 'Isweep')):
        old = procedures.pop(old_name, None)
        if isinstance(old, dict) and new_name not in procedures:
            settings = dict(old)
            if old_name == 'IVSweep':
                def enabled(value):
                    return value.strip().lower() in ('1', 'true', 'yes', 'on') if isinstance(value, str) else bool(value)
                butterfly = enabled(settings.pop('butterfly_sweep', False))
                double = enabled(settings.pop('double_sweep', True))
                settings.setdefault('sweep_pattern', 'Butterfly' if butterfly else 'Return' if double else 'Single')
            else:
                mapping = {'force_high_channel': 'high_channel', 'force_low_channel': 'low_channel',
                           'sense_high_channel': 'sense_high', 'sense_low_channel': 'sense_low',
                           'measurement_range': 'voltage_range', 'current_compliance': 'return_current_compliance'}
                for source, target in mapping.items():
                    if source in settings:
                        settings[target] = settings.pop(source)
                # Preserve the old procedure's mandatory probe defaults.
                settings.setdefault('sense_high', 5)
                settings.setdefault('sense_low', 6)
                settings.setdefault('sweep_pattern', 'Single')
            procedures[new_name] = settings
        if selection.get('procedure') == old_name:
            selection['procedure'] = new_name
    data['procedures'] = procedures
