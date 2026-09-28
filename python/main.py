from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App

from booth import api, config
from booth.preview import FrameGrabber

config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

web_ui = WebUI()
# codec="MJPG" pins the USB capture format. Left on auto, some cameras negotiate an
# uncompressed mode that this resolution/fps can't sustain over USB, and frames come
# back torn/tiled (scrambled blocks) instead of failing cleanly.
camera = Camera(resolution=(1280, 720), fps=20, codec="MJPG")

# A single thread owns the camera; the live preview (/stream) and photo capture share its frames.
grabber = FrameGrabber(camera)
grabber.start()
api.register(web_ui, grabber)

App.run()
