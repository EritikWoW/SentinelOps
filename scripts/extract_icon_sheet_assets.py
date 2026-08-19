from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/web/assets/sentinelops-icon-sheet.png"
CONTROL_SOURCE = ROOT / "src/web/assets/ChatGPT Image 20 авг. 2026 г., 00_50_50.png"
DEST = ROOT / "src/web/assets/sheet"


# Measured from the supplied 1536 x 1024 icon sheet. These are the clean,
# transparent icon variants below the labeled cards, plus the seven brand
# primitives in the upper inventory row.
TOP = {
    "brand-lockup": (0, 0, 565, 225),
    "button-shield": (645, 28, 750, 142),
    "button-flow": (765, 28, 870, 142),
    "button-add": (890, 28, 995, 142),
    "button-sparkle": (1015, 28, 1120, 142),
    "button-heartbeat": (1135, 28, 1240, 142),
    "button-gear": (1255, 28, 1360, 142),
    "button-shield-check": (1375, 28, 1480, 142),
    "shield": (660, 165, 735, 245),
    "flow": (780, 165, 855, 245),
    "add": (900, 165, 980, 245),
    "sparkle": (1025, 165, 1100, 245),
    "heartbeat": (1150, 165, 1230, 245),
    "gear": (1275, 165, 1350, 245),
    "shield-check": (1395, 165, 1475, 245),
}

NAV_BUTTONS = {
    "button-workflow-layers": (158, 286, 232, 354),
}

SMALL = {
    "home": (30, 380, 90, 432),
    "incidents": (98, 380, 158, 432),
    "workflow": (165, 380, 225, 432),
    "safety": (232, 380, 292, 432),
    "reports": (298, 380, 358, 432),
    "settings": (365, 380, 425, 432),
    "user": (432, 380, 492, 432),
    "critical": (540, 380, 600, 432),
    "high": (607, 380, 667, 432),
    "medium": (674, 380, 734, 432),
    "low": (741, 380, 801, 432),
    "info": (808, 380, 868, 432),
    "success": (875, 380, 935, 432),
    "warning": (942, 380, 1002, 432),
    "play": (1040, 380, 1100, 432),
    "pause": (1107, 380, 1167, 432),
    "stop": (1174, 380, 1234, 432),
    "refresh": (1241, 380, 1301, 432),
    "search": (1308, 380, 1368, 432),
    "filter": (1375, 380, 1435, 432),
    "more": (1442, 380, 1502, 432),
    "server": (30, 565, 90, 617),
    "logs": (674, 565, 734, 617),
    "container": (365, 565, 425, 617),
}

# Controls added in the revised sheet. These are complete, transparent button
# assets intended for window chrome and the collapsible sidebar control.
CONTROLS = {
    "sidebar-collapse": (63, 915, 117, 971),
    "sidebar-expand": (176, 915, 230, 971),
    "window-minimize": (353, 915, 409, 971),
    "window-maximize": (475, 915, 531, 971),
    "window-close": (600, 915, 656, 971),
}


def extract_close_icon(image: Image.Image) -> Image.Image:
    """Extract only the cyan close glyph from the complete window button."""

    crop = image.crop((612, 927, 644, 959)).convert("RGBA")
    pixels = crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue, alpha = pixels[x, y]
            if green < 90 or blue < 100:
                pixels[x, y] = (red, green, blue, 0)
    return trim_with_padding(crop, padding=1)


def trim_with_padding(image: Image.Image, padding: int = 4) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return image
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def clean_brand_background(image: Image.Image) -> Image.Image:
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 24:
                pixels[x, y] = (red, green, blue, 0)
    return image


def clean_button_background(image: Image.Image, threshold: int = 80) -> Image.Image:
    """Remove low-alpha sheet haze while preserving the opaque button art."""

    alpha = image.getchannel("A").point(lambda value: 0 if value < threshold else value)
    image.putalpha(alpha)
    return image


def main() -> None:
    source = Image.open(SOURCE).convert("RGBA")
    DEST.mkdir(parents=True, exist_ok=True)
    for name, bounds in {**TOP, **NAV_BUTTONS, **SMALL}.items():
        cropped = trim_with_padding(source.crop(bounds))
        if name.startswith("button-") or name == "gear":
            cropped = clean_button_background(cropped)
        if name == "brand-lockup":
            cropped = clean_brand_background(cropped)
            cropped = trim_with_padding(cropped, padding=2)
        cropped.save(DEST / f"{name}.png", optimize=True)
    control_source = Image.open(CONTROL_SOURCE).convert("RGBA")
    for name, bounds in CONTROLS.items():
        cropped = trim_with_padding(control_source.crop(bounds), padding=2)
        cropped = clean_button_background(cropped)
        cropped.save(DEST / f"{name}.png", optimize=True)
    extract_close_icon(control_source).save(DEST / "close-icon.png", optimize=True)


if __name__ == "__main__":
    main()
