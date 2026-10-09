# js8_aprsis — JS8 @APRSIS GRID Generator

Standalone Python tool that generates **JS8Call-compatible** audio for a two-frame
`@APRSIS GRID` transmission. Use it to report a Maidenhead locator (4–10 characters)
to the APRS-IS network via any station that receives the directed message and has
APRS-IS forwarding enabled.

This implementation embeds the LDPC(174,87) generator matrix and modulation
parameters taken from the JS8Call / JS8Call-Improved codebase so that the produced
WAV files are decodable by standard JS8Call receivers.

## Features

- Directed frame: `CALLSIGN → @APRSIS GRID`
- Huffman-coded data frame carrying the Maidenhead grid (4, 6, 8 or 10 characters)
- All five JS8 submodes: `normal`, `fast`, `turbo`, `slow`, `ultra`
- Generate grid from latitude/longitude (`--lat` / `--lon`) or supply it directly
- Optional live playback timed to the next JS8 slot boundary (`--play`)
- Optional raw (unpadded) audio for testing
- Verbose dump of payload, CRC-12, tones and frame layout

## Requirements

- Python 3.9+ (uses only the standard library)
- Optional: `ffmpeg` / `ffplay` if you want `--play`

## Quick start

```bash
# Basic 4-character grid, normal speed → writes VK0LID_PG74_normal.wav
./js8_aprsis.py VK0LID PG74

# High-precision grid, turbo mode
./js8_aprsis.py VK0LID PG74EJ33KV --speed turbo

# From coordinates (10-character grid by default)
./js8_aprsis.py VK0LID --lat -34.60 --lon 134.36 -o out.wav

# Play immediately (no file kept)
./js8_aprsis.py VK0LID PG74 --play --immediate

# Play and also keep the WAV
./js8_aprsis.py VK0LID PG74 --play -o out.wav
```

## Command-line options

| Argument | Description |
|----------|-------------|
| `callsign` | Your callsign (required) |
| `grid` | Maidenhead locator, 4–10 characters (optional if using `--lat`/`--lon`) |
| `--lat` / `--lon` | Decimal degrees (WGS84); both required together |
| `--precision` | Grid length when deriving from lat/lon: 4, 6, 8 or 10 (default 10) |
| `--speed` | Submode: `normal` (default), `fast`, `turbo`, `slow`, `ultra` |
| `--base` | Base audio frequency in Hz (default 1500) |
| `-o`, `--output` | Output WAV path (default: `CALLSIGN_GRID_SPEED.wav`) |
| `--raw` | Emit signal only (no slot padding / start delay) |
| `--play` | Play via `ffplay` |
| `--immediate` | With `--play`: start at once instead of waiting for the next slot |
| `-v`, `--verbose` | Print frame details, CRC, tones, etc. |

## Transmission format

The tool produces exactly two JS8 frames:

1. **Directed** (`i3 = TX_FIRST`)  
   `CALLSIGN → @APRSIS GRID`

2. **Huffman data** (`i3 = TX_LAST`)  
   The Maidenhead string, Huffman-coded and packed into a single 72-bit payload.

Slot timing, Costas arrays, LDPC encoding, CRC-12 and continuous-phase GFSK
modulation follow the same rules used by JS8Call-Improved so that any modern
JS8 decoder accepts the audio.

## Example output files

The repository may contain sample WAVs generated with the tool, e.g.:

- `VK0LID_PG74EJ33KV_turbo.wav`
- `from_latlon.wav`

## License

This program is free software: you can redistribute it and/or modify it under
the terms of the **GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version**.

See the file [LICENSE](LICENSE) for the full text.

The LDPC generator matrix, tone mapping and modulation parameters are derived
from the JS8Call / [JS8Call-Improved](https://github.com/JS8Call-improved/JS8Call-improved)
codebase, which is itself licensed under GPL-3.0. Consequently this tool is
distributed under the same license.

## Acknowledgements

- Original JS8Call by Jordan Sherer (KN4CRD) and contributors
- Ongoing development by the [JS8Call-Improved](https://github.com/JS8Call-improved/JS8Call-improved) team
- WSJT-X / FT8 foundations by K1JT et al. (the JS8 mode is a derivative work)

## Disclaimer

Amateur radio operators are responsible for ensuring that any transmissions
comply with their local regulations, including identification and permitted
power levels. This tool only generates baseband audio; it does not control a
transmitter.
