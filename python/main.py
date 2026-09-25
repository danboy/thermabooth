from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App

from booth import api, config

config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

web_ui = WebUI()
camera = Camera(resolution=(1280, 720), fps=15)

# Start explicitly: WebUI.expose_camera() does not reliably start it.
camera.start()

# Live preview for the touch screen: <img src="/stream">
web_ui.expose_camera("/stream", camera)
api.register(web_ui, camera)

App.run()
