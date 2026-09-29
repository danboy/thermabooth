"""BLE transport for the MXW01 cat-printer protocol. Adapted from jeremy46231/MXW01-catprinter (MIT)."""

import asyncio
import contextlib
import logging
import uuid

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from . import cmds

logger = logging.getLogger(__name__)

PACING_DELAY_S = 0.015
NOTIFICATION_TIMEOUT_S = 7.0
PRINT_COMPLETE_BASE_TIMEOUT_S = 15.0
PRINT_COMPLETE_LINES_PER_SEC = 15.0
SCAN_TIMEOUT_S = 10


async def _scan(name: str | None, address: str | None, timeout: int):
    if address:
        with contextlib.suppress(ValueError):
            return str(uuid.UUID(address))
        if address.count(":") == 5:
            return address

    autodiscover = not name
    service_uuids = {cmds.MAIN_SERVICE_UUID, cmds.MAIN_SERVICE_UUID_ALT}

    def filter_fn(device, adv_data):
        if autodiscover:
            return any(u.lower() in service_uuids for u in adv_data.service_uuids)
        return device.name == name

    device = await BleakScanner.find_device_by_filter(filter_fn, timeout=timeout)
    if device is None:
        raise RuntimeError("Printer not found. Turn it on and keep it close.")
    return device


class _Waiter:
    def __init__(self):
        self.received: dict[int, bytes] = {}
        self.condition = asyncio.Condition()

    def on_notify(self, _sender, data: bytearray):
        parsed = cmds.parse_notification(bytes(data))
        if parsed is None:
            logger.debug("Ignoring malformed notification: %s", bytes(data).hex())
            return
        cmd_id, payload = parsed
        asyncio.create_task(self._store(cmd_id, payload))

    async def _store(self, cmd_id: int, payload: bytes) -> None:
        async with self.condition:
            self.received[cmd_id] = payload
            self.condition.notify_all()

    async def wait_for(self, cmd_id: int, timeout: float) -> bytes | None:
        async with self.condition:
            self.received.pop(cmd_id, None)
            try:
                await asyncio.wait_for(self.condition.wait_for(lambda: cmd_id in self.received), timeout=timeout)
            except asyncio.TimeoutError:
                return None
            return self.received.pop(cmd_id)


async def send(image_data: bytes, device_name: str | None, device_address: str | None, intensity: int) -> None:
    address = await _scan(device_name, device_address, SCAN_TIMEOUT_S)
    logger.info("Connecting to %s...", address)

    async with BleakClient(address, timeout=20.0) as client:
        service_uuids = {cmds.MAIN_SERVICE_UUID, cmds.MAIN_SERVICE_UUID_ALT}
        service = next((s for s in client.services if s.uuid.lower() in service_uuids), None)
        if service is None:
            raise RuntimeError("Printer doesn't expose the expected BLE service. Is it an MXW01-protocol printer?")

        control_char = service.get_characteristic(cmds.CONTROL_CHARACTERISTIC_UUID)
        notify_char = service.get_characteristic(cmds.NOTIFY_CHARACTERISTIC_UUID)
        data_char = service.get_characteristic(cmds.DATA_CHARACTERISTIC_UUID)
        if not (control_char and notify_char and data_char):
            raise RuntimeError("Printer is missing one of the control/notify/data BLE characteristics.")

        waiter = _Waiter()
        await client.start_notify(notify_char.uuid, waiter.on_notify)

        try:
            await client.write_gatt_char(control_char.uuid, cmds.cmd_set_intensity(intensity), response=False)
            await asyncio.sleep(0.1)

            await client.write_gatt_char(control_char.uuid, cmds.cmd_get_status(), response=False)
            status = await waiter.wait_for(cmds.CommandIDs.GET_STATUS, NOTIFICATION_TIMEOUT_S)
            if status is None:
                raise RuntimeError("Printer didn't respond to a status request.")
            err = cmds.status_error(status)
            if err:
                raise RuntimeError(err)

            line_count = len(image_data) // cmds.PRINT_WIDTH_BYTES
            await client.write_gatt_char(control_char.uuid, cmds.cmd_print_request(line_count), response=False)
            print_ack = await waiter.wait_for(cmds.CommandIDs.PRINT, NOTIFICATION_TIMEOUT_S)
            if print_ack is None:
                raise RuntimeError("Printer didn't respond to the print request.")
            if not print_ack or print_ack[0] != 0:
                raise RuntimeError("Printer rejected the print request.")

            logger.info("Sending %d bytes of image data...", len(image_data))
            chunk_size = cmds.PRINT_WIDTH_BYTES
            for i in range(0, len(image_data), chunk_size):
                await client.write_gatt_char(data_char.uuid, image_data[i : i + chunk_size], response=False)
                await asyncio.sleep(PACING_DELAY_S)

            await client.write_gatt_char(control_char.uuid, cmds.cmd_flush(), response=False)

            timeout = PRINT_COMPLETE_BASE_TIMEOUT_S + line_count / PRINT_COMPLETE_LINES_PER_SEC
            completion = await waiter.wait_for(cmds.CommandIDs.PRINT_COMPLETE, timeout)
            if completion is None:
                logger.warning("Timed out waiting for print-complete notification; print may still have finished.")
        finally:
            with contextlib.suppress(BleakError, Exception):
                await client.stop_notify(notify_char.uuid)


def print_sync(image_data: bytes, device_name: str | None, device_address: str | None, intensity: int) -> None:
    """Blocking wrapper - call from a worker thread, not the event loop."""
    asyncio.run(send(image_data, device_name or None, device_address or None, intensity))
