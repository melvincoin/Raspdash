# RaspDash

Offline VW-retro HDMI dashboard voor Raspberry Pi 3 Model B.

## Publieke repository

Persoonlijke runtimegegevens worden bewust niet opgenomen. Dit geldt onder andere voor voertuig- en ritlogs, lokale configuratie, backups, geuploade splashscreens/achtergronden en niet-herdistribueerbare lettertypen. RaspDash maakt de benodigde datamappen en standaardconfiguratie bij de eerste start zelf aan.

Deze versie bevat een werkende simulator zonder OBD-data. Daarmee kun je het dashboard lokaal of op de Raspberry starten, de fullscreen UI tonen en later de `VehicleProvider`-implementaties uitbreiden voor HEX-V2 of ELM327.

## Snel starten op Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Open daarna:

- Dashboard: http://127.0.0.1:5000/
- Beheer: http://127.0.0.1:5000/admin
- Healthcheck: http://127.0.0.1:5000/api/health

## Snel starten op Raspberry Pi OS Lite

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip surf fbi xserver-xorg xinit openbox unclutter avahi-daemon bluetooth bluez
sudo mkdir -p /opt/raspdash
sudo chown -R "$USER:$USER" /opt/raspdash
git clone <repo> /opt/raspdash
cd /opt/raspdash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
sudo bash ./scripts/install-pi.sh
```

Na reboot start het dashboard in Chromium kiosk mode. De beheerinterface is bereikbaar via `http://dashboard.local/admin` als mDNS actief is, of via het IP-adres van de Raspberry.

## Projectstructuur

```text
raspdash/
  app.py                  Flask routes, API en WebSocket events
  config.py               JSON-configuratiebeheer
  providers/              VehicleProvider abstractie en adapters
  static/
    css/                  Dashboard en admin styling
    js/                   WebSocket client en beheerlogica
    uploads/              Splash screens en achtergronden
  templates/              Dashboard, admin en splash views
scripts/
  install-pi.sh           Installeert systemd services en kiosk setup
  build-image.md          Procedure voor SD-card image
  services/               systemd unit files
```

## Status

Werkend:

- Dashboard met digitale waarden voor olie, DSG en accuspanning
- Simulated provider met realistische fake waarden
- Flask backend met REST API
- WebSocket realtime updates via Flask-SocketIO
- Beheerpagina voor display, widgets, kleuren, provider en uploadbare assets
- Configureerbare splash screen en achtergrond
- HEX-V2 USB detectie op basis van seriele poorten/USB metadata
- ELM327 seriele/Bluetooth provider skeleton
- systemd servicebestanden en kiosk launcher
- SD-card image build procedure

Niet lokaal verifieerbaar zonder Raspberry/auto:

- Werkelijke boot-tijd op Raspberry Pi 3 Model A+
- HDMI timing van de aftermarket tellerunit
- HEX-V2 clone protocolgedrag
- ELM327 Bluetooth pairing in de auto

## Ontwerpkeuzes

De dashboard UI gebruikt een donkere OEM-stijl met carbon achtergrond, VW-logo centraal en digitale segmentcijfers. Er is geen frontend-interactie op het dashboard zelf. Alle instellingen lopen via `/admin`.

De backend gebruikt deze providerlaag:

```text
VehicleProvider
├── SimulatedProvider
├── HexV2Provider
└── Elm327Provider
```

Als een provider geen data kan leveren, blijven de dashboardwaarden zichtbaar als placeholders in plaats van de UI te blokkeren.
