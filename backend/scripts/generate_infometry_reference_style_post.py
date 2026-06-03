from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "marketing"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "infometry_webinar_reference_style_1200.png"

W = H = 1200
FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


REG = "segoeui.ttf"
BOLD = "segoeuib.ttf"
SEMIBOLD = "seguisb.ttf"


def gradient_background() -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    px = img.load()
    for y in range(H):
        for x in range(W):
            nx, ny = x / W, y / H
            vignette = math.sqrt((nx - 0.25) ** 2 + (ny - 0.55) ** 2)
            r = int(3 + 14 * nx + 8 * (1 - vignette))
            g = int(6 + 18 * nx + 8 * (1 - ny))
            b = int(13 + 34 * nx + 16 * (1 - vignette))
            px[x, y] = (r, g, b, 255)
    return img


def add_glow(base: Image.Image, cx: int, cy: int, rx: int, color: tuple[int, int, int], alpha: int) -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((cx - rx, cy - rx, cx + rx, cy + rx), fill=(*color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(rx / 2.2))
    base.alpha_composite(layer)


def draw_infometry_logo(d: ImageDraw.ImageDraw, x: int, y: int) -> None:
    d.arc((x, y + 2, x + 64, y + 58), start=102, end=252, fill=(255, 255, 255, 248), width=9)
    d.arc((x + 11, y + 12, x + 58, y + 50), start=104, end=252, fill=(255, 255, 255, 230), width=6)
    d.polygon([(x + 12, y + 31), (x + 52, y + 13), (x + 40, y + 31), (x + 55, y + 48)], fill=(255, 255, 255, 246))
    d.text((x + 76, y + 5), "INFOMETRY INC.", font=font(BOLD, 44), fill=(255, 255, 255, 252))
    d.text((x + 80, y + 52), "Enabling AI for Every Enterprise", font=font(SEMIBOLD, 17), fill=(207, 217, 223, 230))


def draw_line_icon(d: ImageDraw.ImageDraw, kind: str, x: int, y: int) -> None:
    cyan = (37, 190, 255, 255)
    d.rounded_rectangle((x, y, x + 58, y + 58), radius=16, outline=cyan, width=4)
    if kind == "calendar":
        d.rectangle((x + 8, y + 19, x + 50, y + 23), fill=cyan)
        for sx in (16, 30, 44):
            d.line((sx + x, y + 10, sx + x, y + 18), fill=cyan, width=4)
        for yy in (31, 42):
            for xx in (15, 28, 41):
                d.rectangle((x + xx - 3, y + yy - 3, x + xx + 3, y + yy + 3), fill=cyan)
    elif kind == "clock":
        d.ellipse((x + 11, y + 11, x + 47, y + 47), outline=cyan, width=4)
        d.line((x + 29, y + 29, x + 29, y + 17), fill=cyan, width=4)
        d.line((x + 29, y + 29, x + 41, y + 36), fill=cyan, width=4)
    elif kind == "globe":
        d.ellipse((x + 8, y + 8, x + 50, y + 50), outline=cyan, width=4)
        d.arc((x + 16, y + 8, x + 42, y + 50), 82, 278, fill=cyan, width=3)
        d.arc((x + 16, y + 8, x + 42, y + 50), -98, 98, fill=cyan, width=3)
        d.line((x + 11, y + 29, x + 47, y + 29), fill=cyan, width=3)
    elif kind == "mail":
        d.rounded_rectangle((x + 7, y + 14, x + 51, y + 45), radius=4, outline=cyan, width=4)
        d.line((x + 9, y + 17, x + 29, y + 33, x + 49, y + 17), fill=cyan, width=4)


def draw_person(base: Image.Image) -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # Premium corporate portrait illustration, intentionally not copied from the reference.
    d.rounded_rectangle((718, 352, 1126, 1135), radius=176, fill=(229, 235, 239, 255))
    d.polygon([(764, 1135), (842, 586), (1008, 586), (1130, 1135)], fill=(245, 247, 249, 255))
    d.polygon([(850, 602), (922, 760), (1004, 602)], fill=(252, 252, 253, 255))
    d.polygon([(862, 604), (912, 794), (772, 1135), (700, 1135), (728, 706)], fill=(210, 216, 221, 255))
    d.polygon([(988, 604), (938, 794), (1102, 1135), (1178, 1135), (1114, 706)], fill=(213, 219, 224, 255))
    d.ellipse((815, 176, 1010, 421), fill=(219, 168, 137, 255))
    d.rectangle((867, 386, 956, 625), fill=(217, 167, 137, 255))
    d.ellipse((782, 130, 1038, 438), fill=(62, 42, 36, 255))
    d.ellipse((818, 160, 1016, 430), fill=(222, 171, 142, 255))
    d.pieslice((780, 120, 1018, 474), 175, 312, fill=(76, 51, 44, 255))
    d.pieslice((890, 116, 1060, 470), 210, 20, fill=(86, 59, 50, 255))
    d.ellipse((805, 274, 832, 312), fill=(221, 166, 138, 255))
    d.ellipse((1002, 274, 1029, 312), fill=(221, 166, 138, 255))
    d.ellipse((872, 271, 882, 280), fill=(35, 35, 36, 255))
    d.ellipse((946, 271, 956, 280), fill=(35, 35, 36, 255))
    d.arc((890, 338, 946, 371), 18, 160, fill=(145, 70, 72, 255), width=4)
    d.line((915, 276, 906, 324, 928, 324), fill=(175, 112, 96, 210), width=3)
    d.line((852, 248, 888, 240), fill=(70, 47, 40, 255), width=5)
    d.line((934, 240, 973, 248), fill=(70, 47, 40, 255), width=5)
    d.rounded_rectangle((768, 850, 1080, 930), radius=38, fill=(219, 224, 228, 255))
    d.rounded_rectangle((874, 842, 1162, 916), radius=37, fill=(230, 234, 237, 255))
    d.ellipse((804, 1024, 832, 1052), fill=(42, 52, 61, 255))
    d.ellipse((1042, 1022, 1070, 1050), fill=(42, 52, 61, 255))
    d.line((861, 604, 922, 762, 988, 604), fill=(198, 205, 211, 255), width=5)
    d.line((920, 760, 920, 1130), fill=(202, 208, 214, 255), width=3)

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse((660, 1044, 1190, 1195), fill=(0, 0, 0, 145))
    shadow = shadow.filter(ImageFilter.GaussianBlur(38))
    base.alpha_composite(shadow)
    # Gentle directional highlights make the vector portrait feel less flat.
    shine = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    spx = shine.load()
    for yy in range(H):
        for xx in range(640, W):
            a = max(0, int(42 - abs(xx - 870) / 7 - abs(yy - 610) / 18))
            if a:
                spx[xx, yy] = (255, 255, 255, a)
    layer.alpha_composite(shine)
    layer = layer.filter(ImageFilter.GaussianBlur(0.25))
    base.alpha_composite(layer)


def draw_cta(d: ImageDraw.ImageDraw) -> None:
    x, y, w, h = 34, 808, 360, 90
    d.rounded_rectangle((x, y, x + w, y + h), radius=45, fill=(38, 190, 255, 255), outline=(225, 250, 255, 255), width=3)
    d.text((x + 42, y + 25), "REGISTER NOW", font=font(BOLD, 28), fill=(2, 18, 30, 255))
    d.ellipse((x + 268, y + 12, x + 342, y + 78), fill=(255, 255, 255, 252))
    d.line((x + 298, y + 31, x + 320, y + 45, x + 298, y + 59), fill=(9, 55, 92, 255), width=10, joint="curve")


def main() -> None:
    img = gradient_background()
    add_glow(img, 930, 325, 430, (255, 255, 255), 46)
    add_glow(img, 1120, 1030, 470, (25, 170, 255), 70)
    add_glow(img, 210, 530, 250, (0, 169, 255), 42)

    d = ImageDraw.Draw(img)
    for y in range(120, 1080, 95):
        d.line((442, y, 1160, y + 70), fill=(70, 190, 255, 18), width=1)
    for x in range(460, 1120, 94):
        d.line((x, 90, x + 70, 1120), fill=(70, 190, 255, 12), width=1)
    d.polygon([(486, 0), (1200, 0), (1200, 1200), (720, 1200), (630, 640)], fill=(255, 255, 255, 16))

    draw_person(img)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, 690, H), fill=(0, 0, 0, 118))
    od.rectangle((590, 0, 790, H), fill=(0, 0, 0, 76))
    img.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(18)))

    d = ImageDraw.Draw(img)
    draw_infometry_logo(d, 34, 42)
    d.text((36, 222), "WEBINAR", font=font(BOLD, 82), fill=(33, 185, 255, 255))
    d.line((39, 324, 520, 324), fill=(207, 214, 218, 205), width=3)

    d.text((38, 370), "Webinar: Zero-Copy Data", font=font(BOLD, 34), fill=(255, 255, 255, 255))
    d.text((38, 417), "Sharing with Snowflake", font=font(BOLD, 34), fill=(44, 190, 255, 255))
    d.text((38, 480), "Learn how modern data sharing removes ETL drag,", font=font(REG, 25), fill=(214, 224, 231, 235))
    d.text((38, 516), "cuts duplication, and unlocks live access at scale.", font=font(REG, 25), fill=(214, 224, 231, 235))

    draw_line_icon(d, "calendar", 38, 596)
    d.text((136, 607), "29 MAY, 2026", font=font(BOLD, 28), fill=(255, 255, 255, 255))
    d.text((136, 643), "Friday", font=font(REG, 21), fill=(169, 197, 212, 230))
    draw_line_icon(d, "clock", 38, 720)
    d.text((136, 736), "8:30 AM PST | 10 PM IST", font=font(BOLD, 26), fill=(255, 255, 255, 255))

    draw_cta(d)

    draw_line_icon(d, "globe", 38, 968)
    d.text((136, 981), "www.infometry.net", font=font(BOLD, 24), fill=(255, 255, 255, 245))
    draw_line_icon(d, "mail", 38, 1060)
    d.text((136, 1074), "info@infometry.net", font=font(BOLD, 24), fill=(255, 255, 255, 245))

    right_tint = Image.new("RGBA", (W, H), (2, 16, 31, 0))
    rt = ImageDraw.Draw(right_tint)
    rt.rectangle((665, 0, W, H), fill=(2, 16, 31, 74))
    rt.rectangle((835, 0, W, H), fill=(16, 183, 255, 20))
    img.alpha_composite(right_tint.filter(ImageFilter.GaussianBlur(22)))

    d.rounded_rectangle((740, 76, 1126, 140), radius=32, fill=(0, 0, 0, 118), outline=(75, 201, 255, 110), width=1)
    d.text((778, 94), "LIVE WEBINAR  |  SNOWFLAKE", font=font(SEMIBOLD, 21), fill=(214, 243, 255, 245))

    final = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(final)
    fd.rectangle((0, 0, W, H), outline=(32, 188, 255, 120), width=6)
    img.alpha_composite(final)
    img.convert("RGB").save(OUT_FILE, quality=95, subsampling=0)
    print(OUT_FILE)


if __name__ == "__main__":
    main()
