# RaspDash

RaspDash is an offline, full-screen vehicle dashboard for a Raspberry Pi and an HDMI display. It provides a configurable canvas-based UI, a browser-based administration page, live WebSocket updates, a simulator, and read-only vehicle providers for ELM327-compatible and HEX-V2-style adapters.

The current hardware target is a Raspberry Pi 3 Model B connected to a 1280x720 aftermarket instrument display. Vehicle-specific VAG/UDS decoding is experimental and may not work on a different ECU, model year, gateway, adapter, or CAN topology.

## Features

- Full-screen 1280x720 dashboard with configurable widgets
- Digital, gauge, and retro widget renderers
- Live updates over WebSocket
- Browser-based administration page
- Simulated provider for development without a vehicle
- Read-only ELM327/vLinker OBD-II and VAG UDS polling
- HEX-V2 USB detection and diagnostics
- Configurable boot splash and background assets
- Raspberry Pi systemd, X11, Surf kiosk, and black-cover startup chain
- Optional ride logging and diagnostic discovery tools
- Raspberry Pi temperature, throttling, display, load, and uptime status

## Requirements

### Minimum hardware

- Raspberry Pi 3 Model B or newer
- Reliable 5 V Raspberry Pi power supply appropriate for the selected model
- 16 GB or larger microSD card recommended
- HDMI display; the supplied layout is designed for 1280x720
- Network access during installation and for the administration page

The simulator does not require an OBD adapter or a vehicle.

### Vehicle-data hardware

For live vehicle data, use one of the following:

- USB ELM327-compatible adapter; a vLinker FS at 115200 baud is the tested setup
- Serial or Bluetooth ELM327-compatible adapter exposed as `/dev/ttyUSB*`, `/dev/ttyACM*`, or `/dev/rfcomm*`
- HEX-V2-style USB adapter for detection and experimental diagnostics

The tested vehicle connection uses ISO 15765-4 CAN, 11-bit identifiers, at 500 kbit/s. Manufacturer-specific UDS values are not universal. Verify every decoded value against a trusted diagnostic tool before relying on it.

### Software

- Raspberry Pi OS Lite with systemd, or a comparable Debian-based distribution
- Python 3.11 or newer recommended
- Git
- Python packages from `requirements.txt`
- Xorg, Xinit, Openbox, Surf, FBI, unclutter, and Avahi for kiosk operation
- BlueZ only when a Bluetooth adapter is used

The tested Raspberry Pi currently runs Python 3.13.5.

## Quick start on Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open:

- Dashboard: <http://127.0.0.1:5000/>
- Administration: <http://127.0.0.1:5000/admin>
- Health check: <http://127.0.0.1:5000/api/health>

The default provider is the simulator.

## Install on Raspberry Pi OS Lite

Install the operating-system packages:

```bash
sudo apt update
sudo apt install -y \
  git python3-venv python3-pip \
  surf fbi xserver-xorg xinit openbox unclutter \
  avahi-daemon bluetooth bluez
```

Clone and install RaspDash:

```bash
sudo mkdir -p /opt/raspdash
sudo chown -R "$USER:$USER" /opt/raspdash
git clone https://github.com/melvincoin/Raspdash.git /opt/raspdash
cd /opt/raspdash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
sudo bash ./scripts/install-pi.sh
sudo reboot
```

The installer:

- installs and enables the backend, kiosk, and splash systemd services;
- configures Xorg access for the kiosk user;
- changes the hostname to `dashboard`;
- enables Avahi for `dashboard.local` discovery;
- configures Bluetooth RFCOMM only when a Bluetooth MAC address exists in the runtime configuration.

After reboot, open <http://dashboard.local/admin> from another device on the same trusted network. If mDNS is unavailable, use the Raspberry Pi IP address.

Surf is preferred for the kiosk. Chromium is used only as a fallback when Surf is unavailable.

## Configuration

On first start, RaspDash creates `data/config.json` from the defaults in `raspdash/config.py`. Runtime configuration is intentionally excluded from Git.

Use the administration page to configure:

- display brightness, render scale, background, and splash image;
- widget sources, labels, positions, sizes, styles, and warning thresholds;
- simulator, ELM327, or HEX-V2 provider settings;
- serial port, baud rate, CAN protocol, and polling intervals.

OBD requests are disabled by default. Enable `allow_requests` only after confirming the adapter, port, protocol, and vehicle are correct. RaspDash only implements read operations; coding, adaptations, security access, output tests, and ECU writes are outside the project scope.

## Custom assets and fonts

Personal splash images, backgrounds, runtime data, backups, reports, and non-redistributable fonts are excluded from the public repository.

- Upload splash screens and backgrounds through the administration page.
- If you have suitable font licenses, place custom fonts in `raspdash/static/fonts/` and adjust the CSS as needed.
- Without the optional VW-style font files, the browser falls back to locally available system fonts.

## Project structure

```text
raspdash/
  app.py                  Flask application, API, and WebSocket stream
  config.py               Default and runtime configuration handling
  providers/              Simulator and vehicle-data providers
  routes/                 Widget and layout APIs
  services/               Configuration, layout, and logging services
  static/                 CSS, JavaScript, icons, and user upload folders
  templates/              Dashboard, administration, and splash pages
scripts/
  install-pi.sh           Raspberry Pi systemd and kiosk installation
  services/               systemd unit templates
  start-kiosk.sh          X11, black-cover, and browser startup
  start-splash.sh         Framebuffer splash startup
  *.py                    Read-only discovery and analysis utilities
tests/
  test_app_runtime.py     Runtime regression tests
```

## Development checks

```bash
python -m unittest discover -s tests -v
python -m compileall -q raspdash scripts tests run.py
python -m pip check
```

## Operational notes

- The application listens on `0.0.0.0:5000` and the administration API has no authentication. Run it only on a trusted, isolated network.
- This project is not a replacement for the original instrument cluster, warning lamps, audible alerts, or vehicle safety systems.
- Do not intentionally trigger Front Assist, distance, emergency-braking, or steering-takeover warnings for testing.
- Use a properly fused automotive power solution and shut down the Raspberry Pi cleanly before removing power.
- Keep an SD-card image backup before changing kiosk, display, or boot settings.

## Public repository policy

The `.gitignore` intentionally excludes personal and runtime material, including:

- local configurations and vehicle/ride logs;
- diagnostic exports and generated reports;
- SD-card images and application backups;
- uploaded splash screens and backgrounds;
- non-redistributable font files.

RaspDash creates the required runtime directories and default configuration when it starts.
