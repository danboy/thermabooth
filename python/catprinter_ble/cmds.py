"""The "51 78" command protocol shared by cheap BLE cat-thermal printers.

Adapted from rbaron/catprinter (MIT). Reverse-engineered from the printers'
Android app traffic - see https://rbaron.net/blog/2021/08/15/Reverse-engineering-the-cat-printer-bluetooth-protocol
"""

PRINT_WIDTH = 384  # dots per row: 58mm paper at 203dpi


def _to_unsigned_byte(val: int) -> int:
    return val if val >= 0 else val & 0xFF


def bs(lst: list[int]) -> bytearray:
    """Turns a list of signed bytes (as reverse-engineered from Java) into an unsigned bytearray."""
    return bytearray(map(_to_unsigned_byte, lst))


CMD_GET_DEV_STATE = bs([81, 120, -93, 0, 1, 0, 0, 0, -1])
CMD_SET_QUALITY_200_DPI = bs([81, 120, -92, 0, 1, 0, 50, -98, -1])
CMD_GET_DEV_INFO = bs([81, 120, -88, 0, 1, 0, 0, 0, -1])
CMD_LATTICE_START = bs([81, 120, -90, 0, 11, 0, -86, 85, 23, 56, 68, 95, 95, 95, 68, 56, 44, -95, -1])
CMD_LATTICE_END = bs([81, 120, -90, 0, 11, 0, -86, 85, 23, 0, 0, 0, 0, 0, 0, 0, 23, 17, -1])
CMD_SET_PAPER = bs([81, 120, -95, 0, 2, 0, 48, 0, -7, -1])

CHECKSUM_TABLE = bs([
    0, 7, 14, 9, 28, 27, 18, 21, 56, 63, 54, 49, 36, 35, 42, 45, 112, 119, 126, 121,
    108, 107, 98, 101, 72, 79, 70, 65, 84, 83, 90, 93, -32, -25, -18, -23, -4, -5,
    -14, -11, -40, -33, -42, -47, -60, -61, -54, -51, -112, -105, -98, -103, -116,
    -117, -126, -123, -88, -81, -90, -95, -76, -77, -70, -67, -57, -64, -55, -50,
    -37, -36, -43, -46, -1, -8, -15, -10, -29, -28, -19, -22, -73, -80, -71, -66,
    -85, -84, -91, -94, -113, -120, -127, -122, -109, -108, -99, -102, 39, 32, 41,
    46, 59, 60, 53, 50, 31, 24, 17, 22, 3, 4, 13, 10, 87, 80, 89, 94, 75, 76, 69, 66,
    111, 104, 97, 102, 115, 116, 125, 122, -119, -114, -121, -128, -107, -110, -101,
    -100, -79, -74, -65, -72, -83, -86, -93, -92, -7, -2, -9, -16, -27, -30, -21, -20,
    -63, -58, -49, -56, -35, -38, -45, -44, 105, 110, 103, 96, 117, 114, 123, 124, 81,
    86, 95, 88, 77, 74, 67, 68, 25, 30, 23, 16, 5, 2, 11, 12, 33, 38, 47, 40, 61, 58,
    51, 52, 78, 73, 64, 71, 82, 85, 92, 91, 118, 113, 120, 127, 106, 109, 100, 99, 62,
    57, 48, 55, 34, 37, 44, 43, 6, 1, 8, 15, 26, 29, 20, 19, -82, -87, -96, -89, -78,
    -75, -68, -69, -106, -111, -104, -97, -118, -115, -124, -125, -34, -39, -48, -41,
    -62, -59, -52, -53, -26, -31, -24, -17, -6, -3, -12, -13,
])


def _chk_sum(b_arr: bytearray, start: int, length: int) -> int:
    acc = 0
    for i in range(start, start + length):
        acc = CHECKSUM_TABLE[(acc ^ b_arr[i]) & 0xFF]
    return acc


def cmd_feed_paper(dots: int) -> bytearray:
    b = bs([81, 120, -67, 0, 1, 0, dots & 0xFF, 0, 0xFF])
    b[7] = _chk_sum(b, 6, 1)
    return b


def cmd_set_energy(val: int) -> bytearray:
    b = bs([81, 120, -81, 0, 2, 0, (val >> 8) & 0xFF, val & 0xFF, 0, 0xFF])
    b[8] = _chk_sum(b, 6, 2)
    return b


def cmd_apply_energy() -> bytearray:
    b = bs([81, 120, -66, 0, 1, 0, 1, 0, 0xFF])
    b[7] = _chk_sum(b, 6, 1)
    return b


def _encode_run_length_repetition(n: int, val: int) -> list[int]:
    res = []
    while n > 0x7F:
        res.append(0x7F | (val << 7))
        n -= 0x7F
    if n > 0:
        res.append((val << 7) | n)
    return res


def _run_length_encode(img_row) -> list[int]:
    res = []
    count = 0
    last_val = -1
    for val in img_row:
        if val == last_val:
            count += 1
        else:
            res.extend(_encode_run_length_repetition(count, last_val))
            count = 1
        last_val = val
    if count > 0:
        res.extend(_encode_run_length_repetition(count, last_val))
    return res


def _byte_encode(img_row) -> list[int]:
    res = []
    for chunk_start in range(0, len(img_row), 8):
        byte = 0
        for bit_index in range(8):
            if img_row[chunk_start + bit_index]:
                byte |= 1 << bit_index
        res.append(byte)
    return res


def cmd_print_row(img_row) -> bytearray:
    """img_row is a sequence of PRINT_WIDTH booleans, True = print (black) dot."""
    encoded = _run_length_encode(img_row)
    if len(encoded) > PRINT_WIDTH // 8:
        encoded = _byte_encode(img_row)
        b = bs([81, 120, -94, 0, len(encoded), 0] + encoded + [0, 0xFF])
    else:
        b = bs([81, 120, -65, 0, len(encoded), 0] + encoded + [0, 0xFF])
    b[-2] = _chk_sum(b, 6, len(encoded))
    return b


def cmds_print_img(rows, energy: int = 0xFFFF) -> bytes:
    """rows: an iterable of PRINT_WIDTH-long boolean sequences, top row first."""
    data = bytearray()
    data += CMD_GET_DEV_STATE
    data += CMD_SET_QUALITY_200_DPI
    data += cmd_set_energy(energy)
    data += cmd_apply_energy()
    data += CMD_LATTICE_START
    for row in rows:
        data += cmd_print_row(row)
    data += cmd_feed_paper(25)
    data += CMD_SET_PAPER * 3
    data += CMD_LATTICE_END
    data += CMD_GET_DEV_STATE
    return bytes(data)
