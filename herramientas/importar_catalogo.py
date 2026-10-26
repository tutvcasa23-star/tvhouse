"""Arma el catálogo de apps desactivables a partir de las listas por modelo de Clean Your TV (licencia MIT).

Uso:  python herramientas/importar_catalogo.py <carpeta del repo cleanyourtv>

Genera tvcasa/catalogo/catalogo.json (paquete -> cuántos modelos lo desactivan, descripción, secciones) y
tvcasa/catalogo/modelos.json (lista por modelo, para usarla tal cual cuando el TV coincide).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "tvcasa" / "catalogo"
PAQUETE = re.compile(r"^([a-zA-Z][\w]*(?:\.[\w]+)+)\b\s*(?:#\s*(.*))?$")


def leer_lista(texto: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Devuelve (cabecera, [(paquete, comentario, sección)]) de las líneas activas (no comentadas)."""
    cabecera, entradas, seccion = [], [], ""
    for linea in texto.splitlines():
        s = linea.strip()
        if not s:
            continue
        if s.startswith("#"):
            t = s.lstrip("#").strip()
            if not entradas and len(cabecera) < 6:
                cabecera.append(t)
            elif t and not PAQUETE.match(t) and len(t) < 70:
                seccion = t
            continue
        m = PAQUETE.match(s)
        if m:
            entradas.append((m.group(1), (m.group(2) or "").strip(), seccion))
    return cabecera, entradas


def main(repo: Path) -> None:
    ejemplos = sorted((repo / "examples").glob("*/debloat.txt"))
    veces, comentarios, secciones = Counter(), defaultdict(Counter), defaultdict(Counter)
    modelos = {}
    for lista in ejemplos:
        cabecera, entradas = leer_lista(lista.read_text(encoding="utf-8", errors="replace"))
        tv_json = lista.parent / "tv.json"
        meta = json.loads(tv_json.read_text(encoding="utf-8")) if tv_json.exists() else {}
        paquetes = sorted({p for p, _, _ in entradas})
        modelos[lista.parent.name] = {"tv": meta.get("tv", ""), "os": meta.get("os", ""), "marca": meta.get("brand", ""),
                                      "cabecera": " ".join(cabecera)[:400], "paquetes": paquetes}
        for p, c, sec in entradas:
            veces[p] += 1
            if c:
                comentarios[p][c[:120]] += 1
            if sec:
                secciones[p][sec[:60]] += 1
    catalogo = {p: {"modelos": n,
                    "descripcion": comentarios[p].most_common(1)[0][0] if comentarios[p] else "",
                    "secciones": [s for s, _ in secciones[p].most_common(3)]}
                for p, n in sorted(veces.items(), key=lambda kv: (-kv[1], kv[0]))}
    DESTINO.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%h %ad", "--date=short"],
                            capture_output=True, text=True).stdout.strip()
    (DESTINO / "catalogo.json").write_text(json.dumps({"origen": f"github.com/Gathin23/cleanyourtv {commit}",
                                                       "modelos_leidos": len(ejemplos), "paquetes": catalogo},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    (DESTINO / "modelos.json").write_text(json.dumps(modelos, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copy(repo / "LICENSE", DESTINO / "LICENSE-cleanyourtv.txt")
    print(f"{len(ejemplos)} modelos, {len(catalogo)} paquetes -> {DESTINO}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
