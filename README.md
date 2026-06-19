# Midea GA014s Gateway

Home Assistant custom integration for **Midea GA014s** central air conditioning gateway.

The GA014s is a 485-bus gateway that exposes Midea MDV central AC units over a local HTTP API. This integration connects to the gateway on your LAN and creates a `climate` entity for each indoor unit (up to 64).

## Features

- **No cloud, no account** — pure local HTTP polling, no authentication required
- **Config flow** — set up via UI, just enter the gateway IP
- **Full climate control** — HVAC mode (off/fan/cool/heat/auto/dry), target temperature, fan speed (7 levels + auto), swing mode, electric auxiliary heat (preset)
- **Per-device capability detection** — auto mode is only offered if the indoor unit supports it
- **HVAC action inference** — shows `cooling`/`heating`/`idle` based on current vs target temperature

## Installation

### Via HACS

1. Add this repository as a custom repository in HACS (category: Integration)
2. Install "Midea GA014s Gateway"
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** → search "GA014s"

### Manual

1. Copy the `custom_components/ga014s/` directory to your HA `custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration** → search "GA014s"

## Configuration

| Field | Description | Required |
|-------|-------------|----------|
| Host  | IP address of the GA014s gateway (e.g. `192.168.1.100`) | Yes |

## Supported models

- GA014s (MDV Gateway, firmware v20+)
- Other Midea 485 gateways using the same `protocol.csp` HTTP API

## Protocol documentation

See [PROTOCOL.md](PROTOCOL.md) for the full HTTP API specification.

## License

MIT
