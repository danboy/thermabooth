"""BLE transport for cat-thermal-printer-protocol devices. Adapted from rbaron/catprinter (MIT)."""

import asyncio
import contextlib
import logging
import uuid

from bleak import BleakClient, BleakScanner

try:
    from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
except ImportError:
    BleakClientBlueZDBus = None

logger = logging.getLogger(__name__)

# bleak reports 0xaf30 on some platforms and 0xae30 (the correct one) on others.
POSSIBLE_SERVICE_UUIDS = [
    "0000ae30-0000-1000-8000-00805f9b34fb",
    "0000af30-0000-1000-8000-00805f9b34fb",
]

TX_CHARACTERISTIC_UUID = "0000ae01-0000-1000-8000-00805f9b34fb"
RX_CHARACTERISTIC_UUID = "0000ae02-0000-1000-8000-00805f9b34fb"

PRINTER_READY_NOTIFICATION = b"\x51\x78\xae\x01\x01\x00\x00\x00\xff"

SCAN_TIMEOUT_S = 10
WAIT_AFTER_EACH_CHUNK_S = 0.02
WAIT_FOR_PRINTER_DONE_TIMEOUT_S = 30


async def _scan(name: str | None, address: str | None, timeout: int):
    if address:
        with contextlib.suppress(ValueError):
            return str(uuid.UUID(address))
        if address.count(":") == 5:
            return address

    autodiscover = not name

    def filter_fn(device, adv_data):
        if autodiscover:
            return any(u in adv_data.service_uuids for u in POSSIBLE_SERVICE_UUIDS)
        return device.name == name

    device = await BleakScanner.find_device_by_filter(filter_fn, timeout=timeout)
    if device is None:
        raise RuntimeError("Printer not found. Turn it on and keep it close.")
    return device


def _chunkify(data: bytes, chunk_size: int):
    return (data[i : i + chunk_size] for i in range(0, len(data), chunk_size))


async def send(data: bytes, device_name: str | None, device_address: str | None) -> None:
    address = await _scan(device_name, device_address, SCAN_TIMEOUT_S)
    logger.info("Connecting to %s...", address)
    async with BleakClient(address) as client:
        # BlueZ reports a fixed 23-byte MTU unless negotiated manually.
        if BleakClientBlueZDBus and isinstance(client, BleakClientBlueZDBus):
            await client._acquire_mtu()

        chunk_size = max(20, client.mtu_size - 3)
        done = asyncio.Event()

        def on_notify(_sender, payload):
            if payload == PRINTER_READY_NOTIFICATION:
                done.set()

        await client.start_notify(RX_CHARACTERISTIC_UUID, on_notify)

        logger.info("Sending %d bytes in chunks of %d...", len(data), chunk_size)
        for chunk in _chunkify(data, chunk_size):
            await client.write_gatt_char(TX_CHARACTERISTIC_UUID, chunk)
            await asyncio.sleep(WAIT_AFTER_EACH_CHUNK_S)

        try:
            await asyncio.wait_for(done.wait(), timeout=WAIT_FOR_PRINTER_DONE_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise RuntimeError("Timed out waiting for the printer to finish.")


def print_sync(data: bytes, device_name: str | None, device_address: str | None) -> None:
    """Blocking wrapper - call from a worker thread, not the event loop."""
    asyncio.run(send(data, device_name or None, device_address or None))
