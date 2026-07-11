# SD-card image build procedure

Deze procedure bouwt geen ISO, maar een Raspberry Pi SD-card image. Dat is het juiste formaat voor een Raspberry Pi 3 Model A+.

## Basisimage

1. Download Raspberry Pi OS Lite 64-bit of 32-bit via Raspberry Pi Imager.
2. Schrijf het image naar microSD.
3. Zet SSH aan als beheer op afstand nodig is.
4. Boot de Raspberry Pi en log in.

## Packages

```bash
sudo apt update
sudo apt install -y \
  python3-venv python3-pip \
  surf fbi xserver-xorg xinit openbox unclutter \
  avahi-daemon bluetooth bluez rfkill \
  git
```

## Applicatie installeren

```bash
sudo mkdir -p /opt/raspdash
sudo chown -R "$USER:$USER" /opt/raspdash
git clone <repo> /opt/raspdash
cd /opt/raspdash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
sudo bash ./scripts/install-pi.sh
sudo reboot
```

## Bluetooth ELM327 koppelen

```bash
sudo bluetoothctl
power on
agent on
default-agent
scan on
pair XX:XX:XX:XX:XX:XX
trust XX:XX:XX:XX:XX:XX
quit
sudo rfcomm bind rfcomm0 XX:XX:XX:XX:XX:XX 1
```

Gebruik daarna `/dev/rfcomm0` als ELM327 poort in de beheerinterface.

## Boot-optimalisatie

Controleer de traagste services:

```bash
systemd-analyze
systemd-analyze blame
```

Schakel alleen services uit waarvan je zeker weet dat ze niet nodig zijn in de auto:

```bash
sudo systemctl disable triggerhappy
sudo systemctl disable hciuart
```

Laat `avahi-daemon` actief als `dashboard.local` nodig is.

## Image vastleggen

Als de Raspberry volledig is ingericht:

```bash
sudo shutdown now
```

Maak op een andere machine een image van de SD-card met Raspberry Pi Imager, Win32DiskImager of `dd`.

## Verificatie op doelhardware

Meet na installatie:

```bash
systemd-analyze
free -m
top
curl http://127.0.0.1:5000/api/health
```

Doelen:

- Linux boot binnen 20 seconden
- Dashboard zichtbaar binnen 25 seconden
- Gemiddelde CPU onder 40%
- RAM onder 500 MB
