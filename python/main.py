from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App

from booth import api, config
from booth.preview import FrameGrabber

config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

web_ui = WebUI()
camera = Camera(resolution=(1280, 720), fps=20)

# A single thread owns the camera; the live preview (/stream) and photo capture share its frames.
grabber = FrameGrabber(camera)
grabber.start()
api.register(web_ui, grabber)

App.run()
