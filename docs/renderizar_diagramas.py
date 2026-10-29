"""Convierte los diagramas HTML de docs/diagramas a PNG (requiere Playwright + Chromium)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

D = Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1344, "height": 800}, device_scale_factor=2)
    for html in sorted((D / "diagramas").glob("*.html")):
        pg.goto(html.as_uri())
        pg.locator(".wrap").screenshot(path=str(D / "img" / f"{html.stem}.png"))
        print("ok", html.stem)
    b.close()
