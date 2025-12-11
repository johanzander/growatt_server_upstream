
# Growatt TOU Control Types

After checking all the different Growatt inverter APIs, I've found that there are 4 different ways they handle time-of-use/charge/discharge controls. Each type works completely differently.

## The 4 Types

### MIN Inverters - Time Segments

- 9 programmable time slots
- 3 modes: Load First, Battery First, Grid First
- No charge/discharge power settings (handled by separate number entities)

### NOAH Inverters - Basic Time Segments  

- 9 programmable time slots (like MIN)
- Only 2 modes: Load First, Battery First (no Grid First)
- Has output power limit setting per time segment

### MIX(SPH)/SPA Inverters - Charge/Discharge Periods

- Separate charge and discharge controls
- 3 time periods for each
- Power percentage controls, SOC limits, global on/off
- MIX and SPA work exactly the same

### STORAGE Inverters - Basic Periods

- Separate charge and discharge controls (like MIX)
- Only 1 time period for each
- Just simple on/off, no advanced settings
- For off-grid systems

## Propsed Service Names

**Main models get clean names:**

MIN

- `growatt_server.update_time_segment`

MIX/SPA

- `growatt_server.update_charge_periods`
- `growatt_server.update_discharge_periods`

**Niche models get "basic_" prefix:**

NOAH

- `growatt_server.update_basic_time_segment`

STORAGE

- `growatt_server.update_basic_charge_period`
- `growatt_server.update_basic_discharge_period`

## Why This Makes Sense

- To the best of my knowledge, MIN and MIX inverters seem to be the newer more modern inverters with more advanced controls.
- NOAH and STORAGE are specialty products, so the "basic_" prefix makes it clear they're different
- Possible to create simple Blueprints based on these 4 different control types
