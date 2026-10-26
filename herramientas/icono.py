"""Genera tvcasa/static/tvcasa.ico (un TV simple) para los accesos directos."""
from pathlib import Path

from PIL import Image, ImageDraw

DESTINO = Path(__file__).resolve().parent.parent / "tvcasa" / "static" / "tvcasa.ico"
img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 36, 240, 196), radius=26, fill=(47, 111, 237))
d.rounded_rectangle((34, 54, 222, 178), radius=14, fill=(18, 21, 27))
d.polygon([(104, 88), (104, 146), (156, 117)], fill=(255, 255, 255))
d.rounded_rectangle((92, 204, 164, 222), radius=8, fill=(47, 111, 237))
img.save(DESTINO, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)], bitmap_format="bmp")  # .NET no lee bien PNG dentro del .ico
print(DESTINO)
