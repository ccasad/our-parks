"""Draw the app icon (a white pine tree on a solid colour) and write every icon file.

    uv run python scripts/make_icons.py

One 1024 px master is drawn from simple shapes and scaled down to each size. The
background colour comes from the app's slug so every app looks different on a home screen:
hue = (sum of the slug's character codes x 47) mod 360, saturation 55%, lightness 42%.
"""

import colorsys
from pathlib import Path

from PIL import Image, ImageDraw

SLUG = "our-parks"
ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "app" / "static" / "icons"
MASTER = 1024

# The tree, in master coordinates, centred and about 60% of the icon high.
# Three stacked triangles (apex x, apex y, base y, half-width) and a trunk.
TIERS = [(512, 200, 440, 160), (512, 320, 620, 220), (512, 470, 775, 285)]
TRUNK = (467, 765, 557, 835)

SIZES = {
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-maskable-512.png": 512,
    "apple-touch-icon.png": 180,
}


def background() -> tuple[int, int, int]:
    hue = (sum(ord(c) for c in SLUG) * 47) % 360
    r, g, b = colorsys.hls_to_rgb(hue / 360, 0.42, 0.55)
    return round(r * 255), round(g * 255), round(b * 255)


def draw_master() -> Image.Image:
    scale = 2  # draw at 2x and shrink, for smooth edges
    image = Image.new("RGB", (MASTER * scale, MASTER * scale), background())
    draw = ImageDraw.Draw(image)
    for x, top, base, half in TIERS:
        points = [(x, top), (x - half, base), (x + half, base)]
        draw.polygon([(px * scale, py * scale) for px, py in points], fill="white")
    x0, y0, x1, y1 = TRUNK
    draw.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale], fill="white")
    return image.resize((MASTER, MASTER), Image.LANCZOS)


def svg() -> str:
    r, g, b = background()
    shapes = "".join(
        f'<path d="M{x} {top}L{x - half} {base}H{x + half}Z"/>' for x, top, base, half in TIERS
    )
    x0, y0, x1, y1 = TRUNK
    shapes += f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MASTER} {MASTER}">'
        f'<rect width="{MASTER}" height="{MASTER}" fill="#{r:02x}{g:02x}{b:02x}"/>'
        f'<g fill="#fff">{shapes}</g></svg>\n'
    )


def main() -> None:
    master = draw_master()
    for name, size in SIZES.items():
        master.resize((size, size), Image.LANCZOS).save(ICONS / name, optimize=True)
    (ICONS / "icon.svg").write_text(svg())


if __name__ == "__main__":
    main()
