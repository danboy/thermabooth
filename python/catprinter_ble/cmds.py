"""MXW01 cat-printer BLE protocol.

The MXW01 generation (a different, newer protocol than the GB01/GT01/GB02 "51 78"
family) uses three characteristics: a control channel for commands, a notify channel
for acknowledgements/status, and a separate data channel for the bulk image bytes.

Adapted from jeremy46231/MXW01-catprinter (MIT), itself a fork of rbaron/catprinter.
Protocol reference: https://github.com/jeremy46231/MXW01-catprinter/blob/main/PROTOCOL.md
"""

PRINT_WIDTH = 384  # dots per row: 58mm paper at 203dpi
PRINT_WIDTH_BYTES = PRINT_WIDTH // 8  # 48

# The printer wants at least 90 lines (4320 bytes) per print job; shorter jobs are
# padded with blank rows.
MIN_DATA_BYTES = 90 * PRINT_WIDTH_BYTES

MAIN_SERVICE_UUID = "0000ae30-0000-1000-8000-00805f9b34fb"
MAIN_SERVICE_UUID_ALT = "0000af30-0000-1000-8000-00805f9b34fb"  # some bleak backends report this instead
CONTROL_CHARACTERISTIC_UUID = "0000ae01-0000-1000-8000-00805f9b34fb"
NOTIFY_CHARACTERISTIC_UUID = "0000ae02-0000-1000-8000-00805f9b34fb"
DATA_CHARACTERISTIC_UUID = "0000ae03-0000-1000-8000-00805f9b34fb"


class CommandIDs:
    GET_STATUS = 0xA1
    PRINT_INTENSITY = 0xA2
    PRINT = 0xA9
    PRINT_COMPLETE = 0xAA
    PRINT_DATA_FLUSH = 0xAD


MONOCHROME = 0x00

# CRC-8/DALLAS-MAXIM (poly 0x07, init 0x00), computed over the payload only.
_CRC8_TABLE = [
    0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15, 0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
    0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65, 0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
    0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5, 0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
    0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85, 0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
    0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2, 0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
    0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2, 0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
    0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32, 0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
    0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42, 0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
    0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C, 0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
    0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC, 0xC1, 0xC6, 0xCF, 0xC8, 0xDD, 0xDA, 0xD3, 0xD4,
    0x69, 0x6E, 0x67, 0x60, 0x75, 0x72, 0x7B, 0x7C, 0x51, 0x56, 0x5F, 0x58, 0x4D, 0x4A, 0x43, 0x44,
    0x19, 0x1E, 0x17, 0x10, 0x05, 0x02, 0x0B, 0x0C, 0x21, 0x26, 0x2F, 0x28, 0x3D, 0x3A, 0x33, 0x34,
    0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B, 0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
    0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B, 0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
    0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB, 0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
    0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB, 0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3,
]


def _crc8(payload: bytes) -> int:
    crc = 0
    for byte in payload:
        crc = _CRC8_TABLE[crc ^ byte]
    return crc


def _command(command_id: int, payload: bytes) -> bytes:
    data_len = len(payload)
    packet = bytearray([0x22, 0x21, command_id & 0xFF, 0x00, data_len & 0xFF, (data_len >> 8) & 0xFF])
    packet += payload
    packet.append(_crc8(payload))
    packet.append(0xFF)
    return bytes(packet)


def cmd_get_status() -> bytes:
    return _command(CommandIDs.GET_STATUS, bytes([0x00]))


def cmd_set_intensity(intensity: int) -> bytes:
    return _command(CommandIDs.PRINT_INTENSITY, bytes([max(0, min(255, intensity))]))


def cmd_print_request(line_count: int, mode: int = MONOCHROME) -> bytes:
    payload = line_count.to_bytes(2, "little") + bytes([0x30, mode & 0xFF])
    return _command(CommandIDs.PRINT, payload)


def cmd_flush() -> bytes:
    return _command(CommandIDs.PRINT_DATA_FLUSH, bytes([0x00]))


def encode_row(row) -> bytes:
    """row: PRINT_WIDTH-long sequence of booleans, True = black dot.
    LSB of each byte is the leftmost pixel of its 8-pixel group."""
    out = bytearray(PRINT_WIDTH_BYTES)
    for byte_idx in range(PRINT_WIDTH_BYTES):
        byte_val = 0
        base = byte_idx * 8
        for bit_idx in range(8):
            if row[base + bit_idx]:
                byte_val |= 1 << bit_idx
        out[byte_idx] = byte_val
    return bytes(out)


def prepare_image_data(rows) -> bytes:
    """rows: iterable of PRINT_WIDTH-long boolean sequences, top row first.
    Returns the packed 1bpp buffer, padded to MIN_DATA_BYTES."""
    buf = bytearray()
    for row in rows:
        buf += encode_row(row)
    if len(buf) < MIN_DATA_BYTES:
        buf += bytes(MIN_DATA_BYTES - len(buf))
    return bytes(buf)


def parse_notification(data: bytes):
    """Parses an AE02 notification. Returns (command_id, payload) or None if malformed."""
    if len(data) < 6 or data[0] != 0x22 or data[1] != 0x21:
        return None
    cmd_id = data[2]
    payload_len = int.from_bytes(data[4:6], "little")
    end = 6 + payload_len
    if len(data) < end:
        return None
    return cmd_id, bytes(data[6:end])


def status_error(payload: bytes) -> str | None:
    """Returns a human error message if the A1 status payload reports a problem, else None."""
    if len(payload) < 13 or payload[12] == 0:
        return None
    code = payload[13] if len(payload) >= 14 else 0
    return {1: "Printer is out of paper.", 9: "Printer is out of paper.", 4: "Printer overheated, let it cool down.",
            8: "Printer battery is low."}.get(code, f"Printer reported an error (code {code}).")
