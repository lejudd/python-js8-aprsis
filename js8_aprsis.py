#!/usr/bin/env python3
"""
JS8Call-compatible @APRSIS GRID generator.

Produces a 2-frame JS8 transmission:
  Frame 1: directed  CALLSIGN -> @APRSIS GRID
  Frame 2: Huffman data with the Maidenhead grid (4, 6, 8 or 10 chars)

Examples:
  ./js8_aprsis.py VK0LID PG74
  ./js8_aprsis.py VK0LID PG74EJ33KV --speed turbo
  ./js8_aprsis.py VK0LID --lat -34.60 --lon 134.36 --precision 8 -o out.wav
  ./js8_aprsis.py VK0LID PG74EJ --speed turbo --verbose
  ./js8_aprsis.py VK0LID PG74 --play                 # play only (no WAV kept)
  ./js8_aprsis.py VK0LID PG74 --speed turbo --play --immediate
  ./js8_aprsis.py VK0LID PG74 --play -o out.wav      # play and keep the WAV
"""

from __future__ import annotations

import argparse
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 12000
OUTPUT_RATE = 48000

ALPHABET72 = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "-+"
)
ALPHANUMERIC = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ /@"

FRAME_DIRECTED = 3
TX_FIRST = 1
TX_LAST = 2

SUBMODES = {
    "normal": {"nsps": 1920, "slot": 15.0, "start_delay": 0.500, "costas": 1},
    "fast":   {"nsps": 1200, "slot": 10.0, "start_delay": 0.200, "costas": 2},
    "turbo":  {"nsps": 600,  "slot": 6.0,  "start_delay": 0.100, "costas": 2},
    "slow":   {"nsps": 3840, "slot": 30.0, "start_delay": 0.500, "costas": 2},
    "ultra":  {"nsps": 384,  "slot": 4.0,  "start_delay": 0.100, "costas": 2},
}

COSTAS_SET_1 = (
    (4, 2, 5, 6, 1, 3, 0),
    (4, 2, 5, 6, 1, 3, 0),
    (4, 2, 5, 6, 1, 3, 0),
)
COSTAS_SET_2 = (
    (0, 6, 2, 3, 5, 4, 1),
    (1, 5, 0, 2, 3, 6, 4),
    (2, 5, 0, 6, 4, 1, 3),
)

HUFFMAN = {
    " ": "01", "E": "100", "T": "1101", "A": "0011", "O": "11111",
    "I": "11100", "N": "10111", "S": "10100", "H": "00011", "R": "00000",
    "D": "111011", "L": "110011", "C": "110001", "U": "101101", "M": "101011",
    "W": "001011", "F": "001001", "G": "000101", "Y": "000011", "P": "1111011",
    "B": "1111001", ".": "1110100", "V": "1100101", "K": "1100100",
    "-": "1100001", "+": "1100000", "?": "1011001", "!": "1011000",
    '"': "1010101", "X": "1010100", "0": "0010101", "J": "0010100",
    "1": "0010001", "Q": "0010000", "2": "0001001", "Z": "0001000",
    "3": "0000101", "5": "0000100", "4": "11110101", "9": "11110100",
    "8": "11110001", "6": "11110000", "7": "11101011", "/": "11101010",
}

NBASECALL = 37 * 36 * 10 * 27 * 27 * 27
BASECALLS = {
    "<....>": NBASECALL + 1,
    "@ALLCALL": NBASECALL + 2,
    "@APRSIS": NBASECALL + 33,
    # Other groups are not needed for @APRSIS GRID generation.
}

DIRECTED_COMMANDS = {
    "ACK": 14,
    "GRID": 15,
}

# LDPC(174,87) generator matrix rows from JS8Call JS8.cpp (top 87 bits of each
# 88-bit hex string, MSB first). Embedded so no network download is required.
LDPC_ROWS = [
    "23bba830e23b6b6f50982e",
    "1f8e55da218c5df3309052",
    "ca7b3217cd92bd59a5ae20",
    "56f78313537d0f4382964e",
    "6be396b5e2e819e373340c",
    "293548a138858328af4210",
    "cb6c6afcdc28bb3f7c6e86",
    "3f2a86f5c5bd225c961150",
    "849dd2d63673481860f62c",
    "56cdaec6e7ae14b43feeee",
    "04ef5cfa3766ba778f45a4",
    "c525ae4bd4f627320a3974",
    "41fd9520b2e4abeb2f989c",
    "7fb36c24085a34d8c1dbc4",
    "40fc3e44bb7d2bb2756e44",
    "d38ab0a1d2e52a8ec3bc76",
    "3d0f929ef3949bd84d4734",
    "45d3814f504064f80549ae",
    "f14dbf263825d0bd04b05e",
    "db714f8f64e8ac7af1a76e",
    "8d0274de71e7c1a8055eb0",
    "51f81573dd4049b082de14",
    "d8f937f31822e57c562370",
    "b6537f417e61d1a7085336",
    "ecbd7c73b9cd34c3720c8a",
    "3d188ea477f6fa41317a4e",
    "1ac4672b549cd6dba79bcc",
    "a377253773ea678367c3f6",
    "0dbd816fba1543f721dc72",
    "ca4186dd44c3121565cf5c",
    "29c29dba9c545e267762fe",
    "1616d78018d0b4745ca0f2",
    "fe37802941d66dde02b99c",
    "a9fa8e50bcb032c85e3304",
    "83f640f1a48a8ebc0443ea",
    "3776af54ccfbae916afde6",
    "a8fc906976c35669e79ce0",
    "f08a91fb2e1f78290619a8",
    "cc9da55fe046d0cb3a770c",
    "d36d662a69ae24b74dcbd8",
    "40907b01280f03c0323946",
    "d037db825175d851f3af00",
    "1bf1490607c54032660ede",
    "0af7723161ec223080be86",
    "eca9afa0f6b01d92305edc",
    "7a8dec79a51e8ac5388022",
    "9059dfa2bb20ef7ef73ad4",
    "6abb212d9739dfc02580f2",
    "f6ad4824b87c80ebfce466",
    "d747bfc5fd65ef70fbd9bc",
    "612f63acc025b6ab476f7c",
    "05209a0abb530b9e7e34b0",
    "45b7ab6242b77474d9f11a",
    "6c280d2a0523d9c4bc5946",
    "f1627701a2d692fd9449e6",
    "8d9071b7e7a6a2eed6965e",
    "bf4f56e073271f6ab4bf80",
    "c0fc3ec4fb7d2bb2756644",
    "57da6d13cb96a7689b2790",
    "a9fa2eefa6f8796a355772",
    "164cc861bdd803c547f2ac",
    "cc6de59755420925f90ed2",
    "a0c0033a52ab6299802fd2",
    "b274db8abd3c6f396ea356",
    "97d4169cb33e7435718d90",
    "81cfc6f18c35b1e1f17114",
    "481a2a0df8a23583f82d6c",
    "081c29a10d468ccdbcecb6",
    "2c4142bf42b01e71076acc",
    "a6573f3dc8b16c9d19f746",
    "c87af9a5d5206abca532a8",
    "012dee2198eba82b19a1da",
    "b1ca4ea2e3d173bad4379c",
    "b33ec97be83ce413f9acc8",
    "5b0f7742bca86b8012609a",
    "37d8e0af9258b9e8c5f9b2",
    "35ad3fb0faeb5f1b0c30dc",
    "6114e08483043fd3f38a8a",
    "cd921fdf59e882683763f6",
    "95e45ecd0135aca9d6e6ae",
    "2e547dd7a05f6597aac516",
    "14cd0f642fc0c5fe3a65ca",
    "3a0a1dfd7eee29c2e827e0",
    "c8b5dffc335095dcdcaf2a",
    "3dd01a59d86310743ec752",
    "8abdb889efbe39a510a118",
    "3f231f212055371cf3e2a2"
]


# ---------------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------------

def int_to_bits(value: int, width: int) -> list[int]:
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def bits_to_int(bits) -> int:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def bits_to_string(bits) -> str:
    return "".join(str(int(x)) for x in bits)


# ---------------------------------------------------------------------------
# 12-character JS8 payload packing (Varicode::pack72bits)
# ---------------------------------------------------------------------------

def pack72bits(value: int, remainder: int) -> str:
    value &= (1 << 64) - 1
    remainder &= 0xFF
    rem_high = ((value & 0xF) << 2) | ((remainder >> 6) & 0x3)
    rem_low = remainder & 0x3F
    value >>= 4
    packed = [None] * 12
    packed[11] = ALPHABET72[rem_low]
    packed[10] = ALPHABET72[rem_high]
    for i in range(10):
        packed[9 - i] = ALPHABET72[value & 0x3F]
        value >>= 6
    return "".join(packed)


def unpack72bits(text: str) -> list[int]:
    if len(text) != 12:
        raise ValueError("JS8 frame payload must be exactly 12 characters")
    bits: list[int] = []
    for ch in text:
        try:
            value = ALPHABET72.index(ch)
        except ValueError as exc:
            raise ValueError(f"Invalid JS8 6-bit character: {ch!r}") from exc
        bits.extend(int_to_bits(value, 6))
    return bits


# ---------------------------------------------------------------------------
# Callsign packing
# ---------------------------------------------------------------------------

def pack_callsign(callsign: str) -> tuple[int, bool]:
    callsign = callsign.upper().strip()
    portable = False

    if callsign in BASECALLS:
        return BASECALLS[callsign], False

    if callsign.endswith("/P"):
        callsign = callsign[:-2]
        portable = True

    if callsign.startswith("3DA0"):
        callsign = "3D0" + callsign[4:]
    if callsign.startswith("3X") and len(callsign) >= 3 and "A" <= callsign[2] <= "Z":
        callsign = "Q" + callsign[2:]

    if not 2 <= len(callsign) <= 6:
        return 0, portable

    permutations = [callsign]
    if len(callsign) == 2:
        permutations += [" " + callsign + "   "]
    elif len(callsign) == 3:
        permutations += [" " + callsign + "  ", callsign + "   "]
    elif len(callsign) == 4:
        permutations += [" " + callsign + " ", callsign + "  "]
    elif len(callsign) == 5:
        permutations += [" " + callsign, callsign + " "]

    pattern = re.compile(
        r"([0-9A-Z ])([0-9A-Z])([0-9])([A-Z ])([A-Z ])([A-Z ])"
    )
    matched = None
    for candidate in permutations:
        m = pattern.fullmatch(candidate)
        if m:
            matched = m.group(0)
            break
    if matched is None:
        return 0, portable

    values = [ALPHANUMERIC.index(c) for c in matched]
    packed = values[0]
    packed = 36 * packed + values[1]
    packed = 10 * packed + values[2]
    packed = 27 * packed + values[3] - 10
    packed = 27 * packed + values[4] - 10
    packed = 27 * packed + values[5] - 10
    return packed, portable


# ---------------------------------------------------------------------------
# Directed + Huffman frames
# ---------------------------------------------------------------------------

def pack_directed_frame(from_call: str, to_call: str, command: str) -> str:
    packed_from, portable_from = pack_callsign(from_call)
    packed_to, portable_to = pack_callsign(to_call)
    if packed_from == 0:
        raise ValueError(f"Unable to pack source callsign {from_call!r}")
    if packed_to == 0:
        raise ValueError(f"Unable to pack destination {to_call!r}")

    command_key = command.upper().strip()
    if command_key not in DIRECTED_COMMANDS:
        raise ValueError(f"Unknown directed command {command!r}")
    packed_cmd = DIRECTED_COMMANDS[command_key]

    bits = (
        int_to_bits(FRAME_DIRECTED, 3)
        + int_to_bits(packed_from, 28)
        + int_to_bits(packed_to, 28)
        + int_to_bits(packed_cmd % 32, 5)
    )
    extra = (int(portable_from) << 7) | (int(portable_to) << 6)
    return pack72bits(bits_to_int(bits), extra)


def pack_huffman_data_frame(text: str) -> tuple[str, int]:
    """Legacy data frame: prefix '10' + Huffman payload + pad."""
    text = text.upper()
    prefix = "10"
    payload = ""
    chars = 0
    for ch in text:
        if ch not in HUFFMAN:
            raise ValueError(f"Character {ch!r} is not in the Huffman table")
        code = HUFFMAN[ch]
        if len(prefix) + len(payload) + len(code) < 72:
            payload += code
            chars += 1
        else:
            break
    frame_bits = prefix + payload
    pad = 72 - len(frame_bits)
    if pad > 0:
        frame_bits += "0" + "1" * (pad - 1)
    if len(frame_bits) != 72:
        raise RuntimeError("Huffman frame is not exactly 72 bits")
    return pack72bits(bits_to_int(frame_bits[:64]), bits_to_int(frame_bits[64:])), chars


# ---------------------------------------------------------------------------
# CRC-12, LDPC, tones, waveform
# ---------------------------------------------------------------------------

def crc12_from_75_bits(bits75: list[int]) -> int:
    """boost::augmented_crc<12, 0xc06> ^ 42 over 75 payload bits in an 11-byte buffer."""
    if len(bits75) != 75:
        raise ValueError("CRC input must contain exactly 75 bits")
    data = bytearray(11)
    for i, bit in enumerate(bits75):
        if bit:
            data[i // 8] |= 1 << (7 - (i % 8))
    crc = 0
    poly = 0xC06
    for byte in data:
        for bit_index in range(8):
            bit = (byte >> (7 - bit_index)) & 1
            top = (crc >> 11) & 1
            crc = ((crc << 1) & 0xFFF) | bit
            if top:
                crc ^= poly
    return crc ^ 42


def make_information_bits(msg72_bits: list[int], i3: int) -> tuple[list[int], int]:
    if len(msg72_bits) != 72:
        raise ValueError("msg72 must contain exactly 72 bits")
    payload75 = msg72_bits + int_to_bits(i3, 3)
    crc = crc12_from_75_bits(payload75)
    information = payload75 + int_to_bits(crc, 12)
    if len(information) != 87:
        raise RuntimeError("JS8 information word is not 87 bits")
    return information, crc


def load_ldpc_matrix() -> list[list[int]]:
    matrix = []
    for row in LDPC_ROWS:
        value = int(row, 16)
        matrix.append([(value >> (87 - i)) & 1 for i in range(87)])
    return matrix


def ldpc_encode(information: list[int], matrix: list[list[int]]) -> list[int]:
    """Systematic LDPC(174,87): codeword = parity[87] || information[87]."""
    if len(information) != 87:
        raise ValueError("LDPC information must be 87 bits")
    parity = []
    for row in matrix:
        p = 0
        for bit, coefficient in zip(information, row):
            if coefficient:
                p ^= bit
        parity.append(p)
    return parity + information


def make_tones(codeword: list[int], submode: dict) -> list[int]:
    if len(codeword) != 174:
        raise ValueError("Codeword must contain 174 bits")
    costas = COSTAS_SET_1 if submode["costas"] == 1 else COSTAS_SET_2
    tones = [0] * 79
    tones[0:7] = costas[0]
    tones[36:43] = costas[1]
    tones[72:79] = costas[2]
    for symbol in range(29):
        i = symbol * 3
        tones[7 + symbol] = (codeword[i] << 2) | (codeword[i + 1] << 1) | codeword[i + 2]
    for symbol in range(29):
        i = 87 + symbol * 3
        tones[43 + symbol] = (codeword[i] << 2) | (codeword[i + 1] << 1) | codeword[i + 2]
    return tones


def synthesize_gfsk(
    tones: list[int],
    base_frequency: float,
    nsps: int,
    output_rate: int = OUTPUT_RATE,
) -> list[float]:
    """Continuous-phase FSK matching JS8Call Modulator.cpp (48 kHz)."""
    import numpy as np

    if len(tones) != 79:
        raise ValueError(f"JS8 waveform requires 79 tones, got {len(tones)}")
    tone_spacing = SAMPLE_RATE / nsps
    samples_per_symbol = int(round(nsps * (output_rate / SAMPLE_RATE)))
    tau = 2.0 * math.pi
    freqs = base_frequency + np.asarray(tones, dtype=np.float64) * tone_spacing
    dphi = tau * freqs / output_rate
    phase = np.cumsum(np.repeat(dphi, samples_per_symbol))
    audio = np.sin(phase)
    ramp = max(1, min(samples_per_symbol // 16, len(audio) // 2))
    if ramp > 1:
        t = np.arange(ramp, dtype=np.float64)
        gain = 0.5 * (1.0 - np.cos(math.pi * t / ramp))
        audio[:ramp] *= gain
        audio[-ramp:] *= gain[::-1]
    return audio.tolist()


def write_wav(filename: Path, audio: list[float], sample_rate: int = OUTPUT_RATE) -> None:
    with wave.open(str(filename), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for x in audio:
            x = max(-1.0, min(1.0, x))
            frames.extend(struct.pack("<h", int(round(x * 32767))))
        wav.writeframes(frames)


def wait_for_slot(slot: float, verbose: bool = False) -> float:
    """Sleep until the next JS8 slot boundary (UTC epoch multiple of *slot*).

    Returns the number of seconds slept.  The WAV already contains the
    submode start_delay, so starting playback exactly on the boundary
    places the first tone at boundary + start_delay, matching JS8Call.
    """
    now = time.time()
    next_boundary = math.ceil(now / slot) * slot
    # Guard against floating-point landing exactly on a boundary with
    # a tiny negative remainder that would make us wait a full slot.
    if next_boundary - now < 1e-3:
        next_boundary += slot
    wait = next_boundary - now
    if verbose:
        print(f"Waiting {wait:.3f} s for next {slot:.0f}s slot boundary…")
    time.sleep(wait)
    return wait


def play_audio(path: Path, slot: float, immediate: bool = False,
               verbose: bool = False) -> None:
    """Play *path* through the default sound device using ffplay.

    By default waits for the next JS8 slot boundary so the transmission
    is time-aligned.  Pass immediate=True to start at once.
    """
    if not immediate:
        wait_for_slot(slot, verbose=verbose)
    elif verbose:
        print("Playing immediately (no slot alignment)")

    cmd = [
        "ffplay",
        "-nodisp",          # no video window
        "-autoexit",        # quit when finished
        "-loglevel", "error",
        str(path),
    ]
    if verbose:
        print(f"Starting ffplay: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        sys.exit(
            "ffplay not found. Install ffmpeg (which provides ffplay) "
            "or omit --play."
        )
    except subprocess.CalledProcessError as exc:
        sys.exit(f"ffplay failed with exit code {exc.returncode}")


def encode_frame(
    payload_text: str,
    i3: int,
    submode: dict,
    matrix: list[list[int]],
    base_frequency: float,
) -> tuple[list[int], int, list[int], list[float]]:
    information, crc = make_information_bits(unpack72bits(payload_text), i3)
    codeword = ldpc_encode(information, matrix)
    tones = make_tones(codeword, submode)
    audio = synthesize_gfsk(tones, base_frequency, submode["nsps"])
    return information, crc, tones, audio


# ---------------------------------------------------------------------------
# Maidenhead + message construction
# ---------------------------------------------------------------------------

def validate_maidenhead(grid: str) -> str:
    """Accept Maidenhead locators of length 4, 6, 8 or 10."""
    grid = grid.upper().strip()
    patterns = {
        4:  r"[A-R]{2}[0-9]{2}",
        6:  r"[A-R]{2}[0-9]{2}[A-X]{2}",
        8:  r"[A-R]{2}[0-9]{2}[A-X]{2}[0-9]{2}",
        10: r"[A-R]{2}[0-9]{2}[A-X]{2}[0-9]{2}[A-X]{2}",
    }
    pat = patterns.get(len(grid))
    if not pat or not re.fullmatch(pat, grid):
        raise ValueError(
            f"Invalid Maidenhead grid {grid!r}. "
            "Length must be 4, 6, 8 or 10 characters "
            "(e.g. PG74, PG74EJ, PG74EJ33, PG74EJ33KV)."
        )
    return grid


def latlon_to_maidenhead(lat: float, lon: float, precision: int = 6) -> str:
    if precision not in (4, 6, 8, 10):
        raise ValueError("precision must be 4, 6, 8 or 10")
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"latitude out of range: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"longitude out of range: {lon}")

    adj_lon = lon + 180.0
    adj_lat = lat + 90.0
    A = int(adj_lon / 20.0)
    B = int(adj_lat / 10.0)
    adj_lon -= A * 20.0
    adj_lat -= B * 10.0
    C = int(adj_lon / 2.0)
    D = int(adj_lat / 1.0)
    adj_lon -= C * 2.0
    adj_lat -= D * 1.0
    grid = chr(ord("A") + A) + chr(ord("A") + B) + str(C) + str(D)
    if precision == 4:
        return grid
    E = int(adj_lon * 12.0)
    F = int(adj_lat * 24.0)
    adj_lon -= E / 12.0
    adj_lat -= F / 24.0
    grid += chr(ord("A") + E) + chr(ord("A") + F)
    if precision == 6:
        return grid
    G = int(adj_lon * 120.0)
    H = int(adj_lat * 240.0)
    adj_lon -= G / 120.0
    adj_lat -= H / 240.0
    grid += str(G) + str(H)
    if precision == 8:
        return grid
    I = int(adj_lon * 2880.0)
    J = int(adj_lat * 5760.0)
    return grid + chr(ord("A") + I) + chr(ord("A") + J)


def build_aprsis_frames(callsign: str, grid: str) -> list[dict]:
    callsign = callsign.upper().strip()
    grid = validate_maidenhead(grid)
    directed = pack_directed_frame(callsign, "@APRSIS", "GRID")
    data_payload, nchars = pack_huffman_data_frame(grid)
    if nchars != len(grid):
        raise ValueError(
            f"Grid {grid!r} does not fit in one data frame "
            f"({nchars}/{len(grid)} characters). Use 10 characters or fewer."
        )
    return [
        {
            "name": "DIRECTED",
            "payload": directed,
            "i3": TX_FIRST,
            "description": f"{callsign} -> @APRSIS GRID",
        },
        {
            "name": "DATA",
            "payload": data_payload,
            "i3": TX_LAST,
            "description": grid,
        },
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate JS8 @APRSIS GRID audio (Maidenhead 4-10 chars, or lat/lon)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("callsign", help="Your callsign, e.g. VK0LID")
    parser.add_argument(
        "grid", nargs="?", default=None,
        help="Maidenhead locator (4-10 chars), e.g. PG74EJ33KV",
    )
    parser.add_argument("--lat", type=float, default=None,
                        help="Latitude (decimal degrees, WGS84)")
    parser.add_argument("--lon", type=float, default=None,
                        help="Longitude (decimal degrees, WGS84)")
    parser.add_argument(
        "--precision", type=int, default=10, choices=[4, 6, 8, 10],
        help="Maidenhead length when using --lat/--lon (default 10)",
    )
    parser.add_argument(
        "--speed", choices=list(SUBMODES.keys()), default="normal",
        help="JS8 submode (default: normal)",
    )
    parser.add_argument(
        "--freq", type=float, default=1500.0,
        help="Base audio frequency in Hz (default: 1500)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output WAV path (default: CALLSIGN_GRID_SPEED.wav)",
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Signal only (no slot padding / start delay)",
    )
    parser.add_argument(
        "--play", action="store_true",
        help="Play audio to the default sound device via ffplay (ffmpeg)",
    )
    parser.add_argument(
        "--immediate", action="store_true",
        help="With --play: start playback immediately instead of waiting "
             "for the next JS8 slot boundary",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print frame details (payload, CRC, tones)",
    )
    args = parser.parse_args()

    callsign = args.callsign.upper().strip()

    if args.lat is not None or args.lon is not None:
        if args.lat is None or args.lon is None:
            parser.error("--lat and --lon must be used together")
        if args.grid:
            parser.error("Provide either a grid argument or --lat/--lon, not both")
        grid = latlon_to_maidenhead(args.lat, args.lon, args.precision)
        if args.verbose:
            print(f"Maidenhead from lat/lon: {grid}")
    elif args.grid:
        grid = validate_maidenhead(args.grid)
    else:
        parser.error("Provide a grid, or --lat/--lon")

    submode = SUBMODES[args.speed]
    matrix = load_ldpc_matrix()
    frames = build_aprsis_frames(callsign, grid)

    if args.verbose:
        print(f"Callsign       : {callsign}")
        print(f"Grid           : {grid}  ({len(grid)} chars)")
        print(f"Submode        : {args.speed}  "
              f"(nsps={submode['nsps']}, slot={submode['slot']}s)")
        print(f"Base frequency : {args.freq:.1f} Hz")
        print(f"JS8 frames     : {len(frames)}")

    all_audio: list[float] = []
    for number, frame in enumerate(frames, start=1):
        information, crc, tones, audio = encode_frame(
            frame["payload"], frame["i3"], submode, matrix, args.freq,
        )
        if args.verbose:
            print()
            print("=" * 60)
            print(f"FRAME {number}: {frame['name']}")
            print("=" * 60)
            print(f"Meaning     : {frame['description']}")
            print(f"JS8 payload : {frame['payload']}")
            print(f"i3          : {frame['i3']} ({frame['i3']:03b})")
            print(f"CRC-12      : 0x{crc:03X}")
            print(f"Tones       : {''.join(str(t) for t in tones)}")

        if number == 1:
            if args.raw:
                all_audio.extend([0.0] * int(0.1 * OUTPUT_RATE))
            else:
                delay = int(round(submode["start_delay"] * OUTPUT_RATE))
                all_audio.extend([0.0] * delay)
        all_audio.extend(audio)
        if not args.raw:
            sig = len(audio)
            slot = int(round(submode["slot"] * OUTPUT_RATE))
            if sig < slot:
                all_audio.extend([0.0] * (slot - sig))

    # Persist a WAV only when the user asked for one (--output) or when we
    # are not playing (so the generated file remains the primary deliverable).
    save_wav = args.output is not None or not args.play
    tmp_path: Path | None = None

    if save_wav:
        output = Path(args.output) if args.output else Path(f"{callsign}_{grid}_{args.speed}.wav")
        write_wav(output, all_audio)
    else:
        # Play-only: write to a temporary file that is removed after playback.
        fd, name = tempfile.mkstemp(suffix=".wav", prefix="js8_")
        os.close(fd)
        tmp_path = Path(name)
        write_wav(tmp_path, all_audio)
        output = tmp_path

    if args.verbose:
        print()
        print("=" * 60)
        print("RESULT")
        print("=" * 60)
        if save_wav:
            print(f"WAV         : {output}")
        else:
            print(f"WAV         : (temporary, not kept)")
        print(f"Duration    : {len(all_audio) / OUTPUT_RATE:.3f} s")
        print(f"Sample rate : {OUTPUT_RATE} Hz")
        for n, fr in enumerate(frames, start=1):
            print(f"  Frame {n}: {fr['payload']}  {fr['description']}")
    elif save_wav:
        print(str(output))

    if args.play:
        if args.raw and not args.immediate:
            # Raw mode has no slot padding; still allow timed start if desired,
            # but warn that the audio itself is not slot-length.
            if args.verbose:
                print("Note: --raw audio is not padded to slot length; "
                      "timing alignment only controls when playback begins.")
        try:
            play_audio(
                output,
                slot=submode["slot"],
                immediate=args.immediate,
                verbose=args.verbose,
            )
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
