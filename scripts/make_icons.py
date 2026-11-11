"""Render the extension icons from icon/icon_rounded.svg."""
import io
import os
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
source = (root / "icon" / "icon_rounded.svg").as_uri()
destination = root / "extension" / "icons"
destination.mkdir(exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=os.environ.get("BROWSER_PATH"))
    page = browser.new_page(viewport={"width": 512, "height": 512}, device_scale_factor=1)
    page.goto(source)
    screenshot = page.screenshot(omit_background=True)
    browser.close()

with Image.open(io.BytesIO(screenshot)) as image:
    for size in (16, 32, 48, 128):
        image.resize((size, size), Image.Resampling.LANCZOS).save(destination / f"{size}.png")
