# chint_pm

Home Assistant custom integration for Chint DTSU666 three phase power meters,
read over Modbus (RTU over a serial port, or TCP through a gateway).

Supported variants:

- **DTSU666-H** (the meter shipped with Huawei inverters)
- **DTSU666 / DTSU666-CT**

Requires Home Assistant 2025.6 or newer.

## Installation

Add this repository to HACS as a custom repository (category: integration),
install it, restart Home Assistant, then add the integration from
**Settings → Devices & services → Add integration → Chint powermeter DTSU666**.

The setup asks for the meter variant, the connection type, the port or host, and
the Modbus unit id (11 by default). The wiring mode (3P4W or 3P3W) is read from
the meter and offered as the default on the last step.

## Sensors

Voltages, currents, active and reactive power per phase, power factor,
frequency, and the imported/exported active energy totals are enabled by
default. The meter's configuration registers (transformer ratios, Modbus
settings, on-board clock) and the four reactive energy quadrants are created as
disabled diagnostic entities; enable the ones you need.

Line-to-line voltages are enabled automatically when the meter reports 3P3W
wiring, phase voltages when it reports 3P4W.

## Notes

- The DTSU666 (non-H) returns raw integers that are scaled per the conversion
  table in the operation manual; the -H returns ready-to-use floats.
- The current and voltage transformer ratios (`IrAt`, `UrAt`) are exposed as
  diagnostic sensors but are **not** applied to the measurements. If your meter
  is wired through current transformers, scale the values yourself (for example
  with a template sensor).
- The active energy totals are read from 0x4026 on the -H. The manual documents
  0x401E, but that block returns invalid data on this variant.

Register maps for the supported variants are in [`docs/`](docs/).

## Changelog

### 0.1.0

- Reworked for current Home Assistant: config entry `runtime_data`, a coordinator
  module, frozen entity descriptions, translated entity names, and `icons.json`.
- Fixed config entry migration, which crashed on every upgrade from version 1.
- Fixed the four reactive energy quadrant sensors, which never produced a value.
- Fixed the DTSU666 (non-H) configuration registers and the exported energy
  total, which were lost to a decoding error.
- Fixed the reactive power sensors on the DTSU666 (non-H), which used an energy
  unit that Home Assistant rejects.
- Total active power demand is now read from 0x2050 (per the manual) and reported
  in watts instead of amperes.
- Config flow no longer blocks the event loop and now assigns a unique id, so the
  same meter cannot be added twice.
- Failed register reads are logged instead of being silently discarded.

### 0.0.9

- Add support for multiple types of DTSU666.
- Fix serial connection init issue.
