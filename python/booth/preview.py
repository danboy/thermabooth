"""One background thread reads the camera; everything else (live preview, photo capture) shares its frames.

Reading the camera from several places at once (one MJPEG generator per open connection, plus
photo capture) makes them steal frames from each other, which looks like a jumpy, torn preview.
Here the camera is read once, the preview JPEG is encoded once, and all viewers get the same bytes.
"""

import logging
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)

PREVIEW_WIDTH = 960
PREVIEW_QUALITY = 75


class FrameGrabber:
    def __init__(self, camera) -> None:
        self._camera = camera
        self._cond = threading.Condition()
        self._frame: np.ndarray | None = None
        self._preview: bytes | None = None
        self._seq = 0
        self._running = False

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._loop, name="frame-grabber", daemon=True).start()

    def stop(self) -> None:
        self._running = False

    def _open(self) -> None:
        started = self._camera.is_started
        if callable(started):  # a method in some brick versions, a property in others
            started = started()
        if not started:
            self._camera.start()

    def _loop(self) -> None:
        while self._running:
            try:
                self._open()
                frame = self._camera.capture()  # blocks to respect the camera fps
                if frame is None:
                    time.sleep(0.02)
                    continue
                self._publish(frame)
            except Exception as e:
                logger.warning("camera read failed: %s", e)
                time.sleep(0.5)

    def _publish(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)), interpolation=cv2.INTER_AREA) if w > PREVIEW_WIDTH else frame
        ok, jpg = cv2.imencode(".jpg", cv2.flip(small, 1), [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_QUALITY])  # mirrored, like a mirror
        if not ok:
            return
        with self._cond:
            self._frame = frame
            self._preview = jpg.tobytes()
            self._seq += 1
            self._cond.notify_all()

    def next_frame(self, timeout: float = 3.0) -> np.ndarray | None:
        """A frame captured after this call started (so a photo shows the moment of the click)."""
        with self._cond:
            seq = self._seq
            self._cond.wait_for(lambda: self._seq > seq, timeout)
            return self._frame if self._seq > seq else None

    def mjpeg(self):
        """Multipart MJPEG body: every viewer gets each preview frame at most once."""
        last = 0
        while True:
            with self._cond:
                if not self._cond.wait_for(lambda: self._seq != last, 2.0):
                    continue  # no new frame yet; loop so a closed connection ends the generator
                last, jpg = self._seq, self._preview
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
