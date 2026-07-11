# Raspberry Pi SD-card image procedure

This procedure creates a Raspberry Pi SD-card image, not an ISO file.

## Base operating system

1. Download Raspberry Pi OS Lite through Raspberry Pi Imager.
2. Write it to a 16 GB or larger microSD card.
3. Configure a hostname, user account, Wi-Fi, and SSH in Raspberry Pi Imager when required.
4. Boot the Raspberry Pi and log in.

## Install operating-system packages

```bash
sudo apt update
sudo apt install -y \
  git python3-venv python3-pip \
  surf fbi xserver-xorg xinit openbox unclutter \
  avahi-daemon bluetooth bluez rfkill
```

## Install RaspDash

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

## Optional Bluetooth ELM327 pairing

```bash
sudo bluetoothctl
power on
agent on
default-agent
scan on
pair XX:XX:XX:XX:XX:XX
trust XX:XX:XX:XX:XX:XX
quit
```

Set the paired MAC address and `/dev/rfcomm0` in the runtime configuration, then rerun `scripts/install-pi.sh` to install and enable the RFCOMM service.

## Boot-performance checks

Inspect boot time and slow services:

```bash
systemd-analyze
systemd-analyze blame
```

Disable a service only after confirming that the dashboard, display, input devices, network discovery, and selected OBD adapter do not depend on it.

## Verification

```bash
systemctl status raspdash.service raspdash-kiosk.service raspdash-splash.service
curl --fail http://127.0.0.1:5000/api/health
free -m
df -h /
```

Also verify:

- the splash and kiosk never display a white frame;
- the HDMI mode and layout match the target display;
- `vcgencmd get_throttled` reports `0x0`;
- the selected provider reconnects after a reboot;
- user uploads and runtime configuration survive a service restart.

## Capture the image

Shut down cleanly:

```bash
sudo shutdown now
```

After the Raspberry Pi has powered down, create a full SD-card image with Raspberry Pi Imager, Win32 Disk Imager, or `dd`. Store a SHA-256 checksum next to the backup and test restoration on a spare card when possible.
