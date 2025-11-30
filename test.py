#!/usr/bin/env python3
import sys
print("Python version:", sys.version)
print("Current directory:", sys.path[0])

try:
    import pandas as pd
    print("Pandas imported successfully")
    df = pd.read_csv('devices.csv')
    print("CSV loaded:")
    print(df)
except Exception as e:
    print("Error:", e)

try:
    from config import Config
    print("Config imported successfully")
    c = Config('global_config.json', 'devices.csv')
    print("Sites:", [s.name for s in c.sites])
    print("Config data:", c.data)
    
    # Add default RV sweep settings
    rv_settings = {
        'rv_start': 0.1,
        'rv_stop': 2.0,
        'rv_step': 0.1,
        'pulse_length': 100e-6,
        'read_bias': 0.3,
        'set_amplitude': -1.8
    }
    c.set_procedure_settings('RVSweep', rv_settings)
    print("RV sweep settings added to config")
    
except Exception as e:
    print("Error:", e)

try:
    from runner import MeasurementRunner
    from procedures.rv_sweep import RVSweepProcedure
    print("Runner and procedures imported successfully")
    
    # Create a mock runner for testing
    runner = MeasurementRunner(c)
    runner.log_callback = lambda msg: print("LOG:", msg)
    
    # Get first device
    site = c.sites[0]
    subsite = site.subsites[0]
    device = subsite.devices[0]
    print(f"Testing with device: {device.name} at ({device.x}, {device.y})")
    runner.current_chip = c.data.get("last_chip_id", "TEST")
    runner.current_site = site
    runner.current_subsite = subsite
    
    # Test procedure creation and execution
    settings = c.get_procedure_settings('RVSweep')
    settings['mock_mode'] = True  # Enable mock mode for testing
    proc = RVSweepProcedure(settings, 'test_output', runner)
    print("Procedure created successfully")
    
    # Actually run the procedure
    print("Running RV sweep procedure...")
    proc.run(device)
    print("Procedure completed!")
    
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
