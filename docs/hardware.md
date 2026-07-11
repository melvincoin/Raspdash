# Hardware integration

## ELM327 and vLinker

The primary tested adapter is a USB vLinker FS exposed as `/dev/ttyUSB0` at 115200 baud. RaspDash also supports ELM327-compatible serial devices such as `/dev/ttyACM0` and Bluetooth RFCOMM devices such as `/dev/rfcomm0`.

The tested connection uses ISO 15765-4 CAN with 11-bit identifiers at 500 kbit/s. Generic OBD-II PIDs provide values such as RPM, speed, coolant temperature, intake temperature, throttle, engine load, and manifold pressure. VAG-specific values use read-only UDS `ReadDataByIdentifier` requests.

Manufacturer-specific DIDs vary by ECU software and vehicle. Confirm decoded values with a trusted diagnostic tool before enabling them as dashboard widgets.

## HEX-V2-style USB adapters

RaspDash detects likely HEX-V2 adapters through USB and serial metadata. Clones may appear as CH340, FTDI, or generic USB serial devices, so `/api/obd/hexv2` reports candidates instead of assuming a protocol.

Reliable VAG measurement access depends on the adapter implementation. Confirm:

- which ECU supplies each requested value;
- which DIDs or measurement blocks apply to the vehicle;
- whether the adapter exposes raw KWP, UDS, or CAN traffic;
- whether the adapter supports the required baud rate and framing.

HEX-V2 functionality remains experimental and read-only.

## GPIO and direct CAN

Raspberry Pi GPIO pins cannot connect directly to CAN-H and CAN-L. A separate CAN controller and automotive transceiver are required, for example an MCP2515-based SPI CAN HAT.

When connecting to an existing vehicle bus:

- use a 3.3 V-compatible or isolated CAN HAT;
- connect only through a verified wiring diagram;
- do not connect vehicle 12 V to a GPIO pin;
- do not add another 120-ohm termination resistor to a bus that is already terminated;
- configure SocketCAN in listen-only mode for passive diagnostics.

Internal driver-assistance or instrument-cluster broadcasts may be isolated from the OBD diagnostic connector by the vehicle gateway. Accessing those messages can require a passive connection at the relevant internal CAN bus.

## Dashboard fallback

If a provider cannot supply data, the dashboard displays placeholders instead of blocking the UI. Vehicle-data failures must not prevent the kiosk, administration page, or health endpoint from loading.
