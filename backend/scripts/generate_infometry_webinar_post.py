from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "marketing"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "infometry_webinar_post_1200.png"

W = H = 1200


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


FONT_REG = "segoeui.ttf"
FONT_BOLD = "segoeuib.ttf"
FONT_SEMIBOLD = "seguisb.ttf"


def add_gradient_bg(img: Image.Image) -> None:
    px = img.load()
    for y in range(H):
        for x in range(W):
            nx = x / W
            ny = y / H
            diag = (nx * 0.45 + ny * 0.55)
            r = int(4 + 5 * (1 - diag))
            g = int(8 + 13 * (1 - ny) + 8 * nx)
            b = int(18 + 42 * (1 - diag) + 20 * nx)
            px[x, y] = (r, g, b, 255)


def glow(base: Image.Image, xy: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(radius / 2))
    base.alpha_composite(layer)


def rounded_panel(
    base: Image.Image,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    radius: int = 28,
    blur_shadow: int = 18,
) -> None:
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 8, y1 + 12, x2 + 8, y2 + 12), radius=radius, fill=(0, 170, 255, 36))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_shadow))
    base.alpha_composite(shadow)
    d = ImageDraw.Draw(base)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)
    d.line((x1 + 22, y1 + 1, x2 - 28, y1 + 1), fill=(125, 232, 255, 95), width=1)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if draw.textbbox((0, 0), candidate, font=fnt)[2] <= width:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines


def draw_text_block(
    d: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    max_width: int,
    line_gap: int,
) -> int:
    x, y = xy
    for line in wrap_text(d, text, fnt, max_width):
        d.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + line_gap
    return y


def draw_data_streams(base: Image.Image) -> None:
    random.seed(42)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    for i in range(22):
        y0 = 100 + i * 36 + random.randint(-14, 14)
        pts = []
        for x in range(-80, W + 100, 18):
            y = y0 + math.sin((x / 88) + i * 0.72) * (18 + i % 5) + (x - W / 2) * 0.04
            pts.append((x, y))
        color = (15, 210, 255, 26) if i % 2 else (70, 112, 255, 22)
        d.line(pts, fill=color, width=2)

    for _ in range(76):
        x = random.randint(580, 1130)
        y = random.randint(110, 1020)
        r = random.choice([2, 2, 3, 4])
        col = random.choice([(46, 225, 255, 120), (82, 127, 255, 100), (255, 255, 255, 70)])
        d.ellipse((x - r, y - r, x + r, y + r), fill=col)
        if random.random() < 0.45:
            x2 = x + random.randint(-80, 90)
            y2 = y + random.randint(-60, 70)
            d.line((x, y, x2, y2), fill=(63, 204, 255, 34), width=1)

    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.25)))


def draw_grid(base: Image.Image) -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(0, W, 60):
        alpha = 24 if x % 180 else 42
        d.line((x, 0, x, H), fill=(95, 217, 255, alpha), width=1)
    for y in range(0, H, 60):
        alpha = 20 if y % 180 else 38
        d.line((0, y, W, y), fill=(95, 217, 255, alpha), width=1)
    base.alpha_composite(layer)


def draw_logo(d: ImageDraw.ImageDraw) -> None:
    x, y = 78, 62
    d.rounded_rectangle((x, y, x + 46, y + 46), radius=13, fill=(5, 30, 54, 230), outline=(67, 223, 255, 155), width=1)
    d.line((x + 12, y + 29, x + 21, y + 20, x + 31, y + 27, x + 37, y + 15), fill=(52, 225, 255, 240), width=4)
    for cx, cy in [(x + 12, y + 29), (x + 21, y + 20), (x + 31, y + 27), (x + 37, y + 15)]:
        d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(255, 255, 255, 245))
    d.text((x + 62, y + 5), "INFOMETRY", font=font(FONT_BOLD, 30), fill=(235, 249, 255, 255))
    d.text((x + 63, y + 38), "DATA CLOUD WEBINAR", font=font(FONT_REG, 12), fill=(120, 207, 230, 210))


def draw_dashboard(base: Image.Image) -> None:
    d = ImageDraw.Draw(base)
    rounded_panel(base, (742, 128, 1102, 410), (8, 31, 59, 146), (73, 212, 255, 95), 28)
    d.text((776, 162), "LIVE DATA ACCESS", font=font(FONT_SEMIBOLD, 20), fill=(220, 247, 255, 235))
    d.text((778, 193), "Secure sharing mesh", font=font(FONT_REG, 14), fill=(135, 176, 196, 220))
    for i, h in enumerate([86, 122, 65, 150, 110, 176, 96]):
        x = 782 + i * 40
        d.rounded_rectangle((x, 352 - h, x + 22, 352), radius=8, fill=(22, 201, 255, 90 + i * 12))
    d.line((780, 354, 1058, 354), fill=(105, 207, 244, 85), width=1)

    rounded_panel(base, (792, 476, 1115, 734), (8, 26, 50, 132), (102, 124, 255, 80), 28)
    d.text((826, 510), "DATA PIPELINE STATUS", font=font(FONT_SEMIBOLD, 18), fill=(222, 247, 255, 230))
    statuses = [("ETL", "legacy", (255, 93, 120, 210)), ("COPY", "removed", (70, 220, 255, 220)), ("LIVE", "instant", (102, 255, 199, 220))]
    for idx, (name, label, col) in enumerate(statuses):
        yy = 558 + idx * 48
        d.rounded_rectangle((826, yy, 1084, yy + 34), radius=17, fill=(255, 255, 255, 18), outline=(255, 255, 255, 38))
        d.ellipse((844, yy + 11, 856, yy + 23), fill=col)
        d.text((870, yy + 6), name, font=font(FONT_BOLD, 16), fill=(238, 249, 255, 235))
        d.text((944, yy + 7), label, font=font(FONT_REG, 15), fill=(151, 188, 205, 220))


def draw_check_item(d: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    d.rounded_rectangle((x, y, x + 270, y + 58), radius=22, fill=(255, 255, 255, 22), outline=(86, 225, 255, 78), width=1)
    d.ellipse((x + 21, y + 17, x + 45, y + 41), fill=(21, 210, 255, 215))
    d.line((x + 27, y + 30, x + 33, y + 36, x + 41, y + 23), fill=(4, 21, 39, 255), width=3)
    d.text((x + 60, y + 16), text, font=font(FONT_SEMIBOLD, 22), fill=(234, 248, 255, 245))


def main() -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    add_gradient_bg(img)
    glow(img, (930, 220), 360, (18, 189, 255), 130)
    glow(img, (1180, 820), 410, (67, 86, 255), 92)
    glow(img, (220, 1000), 380, (0, 199, 255), 68)
    draw_grid(img)
    draw_data_streams(img)

    d = ImageDraw.Draw(img)
    d.polygon([(630, 116), (1080, 34), (1164, 136), (730, 258)], fill=(76, 149, 255, 26))
    d.polygon([(682, 852), (1148, 688), (1168, 1024), (748, 1114)], fill=(17, 208, 255, 22))

    rounded_panel(img, (66, 136, 704, 612), (4, 20, 42, 118), (101, 219, 255, 85), 34, 24)
    draw_logo(d)

    d.text((82, 168), "WEBINAR", font=font(FONT_SEMIBOLD, 21), fill=(66, 224, 255, 255))
    d.rounded_rectangle((188, 174, 300, 198), radius=12, fill=(43, 133, 255, 62), outline=(84, 219, 255, 90))
    d.text((206, 174), "SNOWFLAKE", font=font(FONT_BOLD, 12), fill=(195, 244, 255, 245))

    headline_font = font(FONT_BOLD, 58)
    d.text((82, 218), "Webinar: Still Using", font=headline_font, fill=(247, 252, 255, 255))
    d.text((82, 292), "ETL for Data Sharing?", font=headline_font, fill=(247, 252, 255, 255))
    d.rectangle((82, 370, 456, 374), fill=(22, 218, 255, 210))
    d.text((82, 402), "There's a Better Way: Snowflake", font=font(FONT_SEMIBOLD, 31), fill=(119, 229, 255, 255))

    body = (
        "Still relying on ETL pipelines to share data?\n"
        "It's time to rethink your approach.\n\n"
        "Join our upcoming webinar to learn how Snowflake eliminates data duplication "
        "and enables instant access to live data - securely and at scale."
    )
    y = draw_text_block(d, (84, 486), body, font(FONT_REG, 23), (198, 222, 235, 238), 560, 8)

    draw_dashboard(img)
    d = ImageDraw.Draw(img)

    rounded_panel(img, (70, 680, 728, 900), (5, 25, 48, 126), (86, 225, 255, 72), 30, 20)
    d.text((96, 712), "Modern data sharing without the drag", font=font(FONT_SEMIBOLD, 24), fill=(228, 248, 255, 245))
    draw_check_item(d, 96, 760, "No pipelines")
    draw_check_item(d, 394, 760, "No delays")
    draw_check_item(d, 96, 828, "No extra storage")

    cta = (82, 928, 418, 1002)
    glow(img, (250, 966), 135, (24, 208, 255), 80)
    d.rounded_rectangle(cta, radius=28, fill=(26, 205, 255, 245), outline=(189, 250, 255, 220), width=1)
    d.text((130, 946), "Save Your Seat", font=font(FONT_BOLD, 31), fill=(3, 19, 38, 255))

    d.rounded_rectangle((467, 928, 1068, 1002), radius=28, fill=(255, 255, 255, 16), outline=(87, 211, 255, 54), width=1)
    d.text((500, 948), "Built for CIOs, Data Leaders, and Enterprise Teams", font=font(FONT_REG, 22), fill=(185, 216, 231, 230))

    footer = "#Webinar  #ModernDataStack  #Snowflake  #DataLeaders  #CloudTransformation"
    d.text((76, 1090), footer, font=font(FONT_REG, 21), fill=(137, 183, 205, 225))

    # Subtle vignette for premium contrast.
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.rectangle((0, 0, W, H), fill=80)
    for r, a in [(520, 0), (690, 25), (820, 70)]:
        vd.ellipse((W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r), fill=a)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(vignette.filter(ImageFilter.GaussianBlur(70)))
    img.alpha_composite(dark)

    img.convert("RGB").save(OUT_FILE, quality=95, subsampling=0)
    print(OUT_FILE)


if __name__ == "__main__":
    main()
