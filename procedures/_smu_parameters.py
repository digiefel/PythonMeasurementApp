"""Common B1500 ADC and settling controls."""
from procedures.base import Choice, parameter

ACQUISITION_PARAMETERS = (
    parameter('adc_type', 'ADC Type', 0, Choice(((0, 'High-speed'), (1, 'High-resolution')), int), help='Selects the ADC for all active SMUs. High-speed supports parallel measurements.'),
    parameter('adc_mode', 'ADC Integration Mode', 0,
              Choice(((0, 'Auto'), (1, 'Manual'), (2, 'Power line cycles')), int),
              help='Auto scales instrument-selected averaging/integration. Manual uses sample count for high-speed or 80 µs units for high-resolution. PLC uses whole power line cycles (20 ms each at 50 Hz).'),
    parameter('adc_coefficient', 'ADC Samples / Factor / PLC (0 = mode default)', 0.0, float,
              help='Integer coefficient. Auto/Manual: 1–1023 for high-speed, 1–127 for high-resolution. PLC: 1–100. Zero selects the mode default: HS Auto/Manual 1, HR Auto 6, HR Manual 3, PLC 1.'),
    parameter('parallel_measurement', 'Parallel Measurement (high-speed ADC)', False, bool,
              help='Measure the active SMUs in parallel within each sweep step. Requires high-speed ADC; does not run separate contact sweeps concurrently.'),
    parameter('adc_autozero', 'ADC Autozero (high-resolution ADC)', False, bool,
              help='Cancels high-resolution ADC offset, adding integration time. Has no effect with high-speed ADC.'),
    parameter('source_wait_factor', 'Source Settling Factor (0–10, step 0.1)', 1.0, float,
              help='Source wait = factor × instrument automatic wait + offset, before changing output. Default 1 preserves automatic timing; 0 removes its automatic component.'),
    parameter('source_wait_offset', 'Source Settling Offset (s, step 0.0001)', 0.0, float,
              help='Adds 0–1 seconds to the source wait. Separate from hold and step delays.'),
    parameter('measurement_wait_factor', 'Measurement Settling Factor (0–10, step 0.1)', 1.0, float,
              help='Measurement wait = factor × instrument automatic wait + offset. Default 1 preserves automatic settling even when Delay Time is zero. Reducing it may measure before the device settles.'),
    parameter('measurement_wait_offset', 'Measurement Settling Offset (s, step 0.0001)', 0.0, float,
              help='Adds 0–1 seconds to the measurement wait. The instrument wait can be covered by a longer Delay Time.'),
)
