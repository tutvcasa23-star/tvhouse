"""Preparar fotos para el TV: respetar la orientación del teléfono, recortar o achicar y guardar como JPG."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

EXT_FOTO = {".jpg", ".jpeg", ".png", ".webp"}
EXT_VIDEO = {".mp4"}


def listar(carpeta: Path, videos: bool = False) -> list[Path]:
    ext = EXT_FOTO | (EXT_VIDEO if videos else set())
    return sorted(p for p in Path(carpeta).iterdir() if p.is_file() and p.suffix.lower() in ext)


def cubrir(origen: Path, destino: Path, ancho: int = 1920, alto: int = 1080) -> None:
    """Recorta al centro para llenar la pantalla (fondo del inicio)."""
    with Image.open(origen) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        ImageOps.fit(img, (ancho, alto), Image.Resampling.LANCZOS).save(destino, "JPEG", quality=85)


def achicar(origen: Path, destino: Path, lado: int = 1920) -> None:
    """Achica sin recortar (protector de fotos, que hace su propio zoom)."""
    with Image.open(origen) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((lado, lado), Image.Resampling.LANCZOS)
        img.save(destino, "JPEG", quality=88)


def nombre_seguro(i: int, origen: Path, ext: str) -> str:
    """El protector solo acepta letras, números, '-', '_' y '.'; el número mantiene el orden."""
    base = "".join(c if c.isalnum() and c.isascii() or c in "-_" else "-" for c in origen.stem).strip("-") or "foto"
    return f"{i:03d}-{base[:40]}{ext}"
