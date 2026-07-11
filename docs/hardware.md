# Hardware integratie

## HEX-V2 USB clone

De huidige code detecteert waarschijnlijke HEX-V2 adapters via USB/seriele metadata. Veel clones presenteren zich als CH340, FTDI of generieke USB serial adapter. Daarom rapporteert `/api/obd/hexv2` kandidaten in plaats van blind een protocol te starten.

Echte VAG meetwaardeblokken via HEX-V2 zijn adapter- en protocolafhankelijk. Voor betrouwbaar uitlezen moet op de doelauto worden vastgesteld:

- Welke ECU de olietemperatuur levert
- Welke ECU de DSG-temperatuur levert
- Welke meetwaardeblokken/PIDs bruikbaar zijn
- Of de clone raw KWP/UDS/CAN frames doorlaat

Totdat dit bevestigd is, blijft `HexV2Provider` bewust read-only detectie doen.

## ELM327 Bluetooth

`Elm327Provider` opent een seriele poort zoals `/dev/rfcomm0`. De PID-polling is voorbereid maar nog niet actief, omdat DSG- en olietemperatuur bij VAG vaak fabrikant-specifieke PIDs of UDS services vereisen.

## Dashboard fallback

Als een provider geen data levert, toont het dashboard placeholders. De frontend mag nooit blokkeren op OBD.

