"""Qué se le propone a cada TV.

1. Perfil propio probado en la casa (perfiles/*.json): se usa tal cual.
2. Si no, lista de la comunidad para ese mismo modelo (catalogo/modelos.json, de Clean Your TV).
3. Si no, catálogo general: lo instalado que otros modelos ya desactivaron (cuantos más, más confiable).
En todos los casos se descarta lo que coincide con NUNCA (global) o con el 'nunca' del perfil.
"""
from __future__ import annotations

import fnmatch
import json
import re
from functools import lru_cache
from pathlib import Path

CARPETA = Path(__file__).resolve().parent / "perfiles"
CATALOGO = Path(__file__).resolve().parent / "catalogo"

# Lo que ninguna acción toca en ningún TV (advertencias de Clean Your TV y TV Detox + lo que usa la casa).
NUNCA = [
    "android", "com.android.systemui", "com.android.shell", "com.android.phone", "com.android.settings",
    "com.android.tv.settings*", "com.android.providers.*", "*permissioncontroller*", "*packageinstaller*",
    "com.android.vending", "com.google.android.gms*", "com.google.android.gsf*", "*inputmethod*", "*bluetooth*",
    "*tvinput*", "*.tv.framework*", "*setup*", "*wraith*", "*provision*", "*launcher*", "*tvhome*",
    "com.google.android.katniss", "com.google.android.apps.mediashell", "com.google.android.tv.remote.service",
    "*factory*", "*tvcenter*", "com.sony.dtv.tvx", "com.mediatek.*", "mtktvapi.*", "*systemupdate*", "*upgrade*",
    "*.ext.services", "*.ext.shared", "*modulemetadata*", "*overlay*", "com.dolby.*", "*remotepairing*",
    "*rcpowerkey*", "*uinputservice*", "*imeproxy*", "*keychain*", "com.google.android.onetimeinitializer",
    "com.google.android.partnersetup", "*networkstack*", "com.android.wifi*", "*wifi.resources*", "*webview*", "*tvx*", "*livetv*",
    "com.gathin.*", "io.github.maxhayim.*",
]


def cargar_todos() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(CARPETA.glob("*.json"))}


@lru_cache(maxsize=1)
def catalogo() -> dict:
    return json.loads((CATALOGO / "catalogo.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def modelos() -> dict:
    return json.loads((CATALOGO / "modelos.json").read_text(encoding="utf-8"))


def detectar(fabricante: str, modelo: str, perfiles: dict[str, dict] | None = None) -> dict:
    """El primer perfil propio que coincida; si ninguno, el genérico."""
    perfiles = perfiles or cargar_todos()
    for pid, p in perfiles.items():
        if pid == "generico":
            continue
        reg = p["detectar"]
        if re.search(reg["fabricante"], fabricante or "", re.I) and re.search(reg["modelo"], modelo or "", re.I):
            return p
    return perfiles["generico"]


def prohibido(perfil: dict | None, paquete: str) -> bool:
    patrones = NUNCA + list((perfil or {}).get("nunca", []))
    return any(fnmatch.fnmatchcase(paquete, p) for p in patrones)


def candidatos(perfil: dict, incluir_opcionales: bool = False) -> list[dict]:
    lista = list(perfil.get("desactivar", []))
    if incluir_opcionales:
        lista += perfil.get("opcionales", [])
    return [c for c in lista if not prohibido(perfil, c["paquete"])]


def modelo_comunidad(claves: list[str]) -> tuple[str, dict] | None:
    """Busca la lista de la comunidad del mismo modelo por device/product/model (palabras de 4+ letras)."""
    claves = [c.lower() for c in claves if c and len(c) >= 4]
    mejor = None
    for mid, m in modelos().items():
        texto = f"{m['tv']} {m['cabecera']}".lower()
        aciertos = sum(1 for c in claves if re.search(rf"\b{re.escape(c)}\b", texto))
        if aciertos and (not mejor or aciertos > mejor[0]):
            mejor = (aciertos, mid, m)
    return (mejor[1], mejor[2]) if mejor else None


def propuesta(perfil: dict, habilitadas: set[str], claves_modelo: list[str], visibles: set[str] = frozenset()) -> dict:
    """Lista para la pantalla: [{paquete, descripcion, grupo, marcado, origen}] solo de apps instaladas y activas.

    En TV sin perfil propio, las apps que se ven en el inicio (`visibles`) nunca van marcadas: la comunidad a veces
    desactiva Netflix o YouTube por gusto propio, y eso lo decide la familia.
    """
    cat = catalogo()["paquetes"]

    def item(p: str, desc: str, grupo: str, marcado: bool, origen: str) -> dict:
        return {"paquete": p, "descripcion": desc or cat.get(p, {}).get("descripcion", ""), "grupo": grupo,
                "marcado": marcado, "origen": origen, "modelos": cat.get(p, {}).get("modelos", 0)}

    if perfil["id"] != "generico":
        base = [item(c["paquete"], c["descripcion"], c["grupo"], True, "perfil probado en casa") for c in candidatos(perfil)]
        base += [item(c["paquete"], c["descripcion"], c["grupo"], False, "opcional")
                 for c in perfil.get("opcionales", []) if not prohibido(perfil, c["paquete"])]
        return {"fuente": f"perfil {perfil['nombre']}", "items": [x for x in base if x["paquete"] in habilitadas]}

    mc = modelo_comunidad(claves_modelo)
    if mc:
        mid, m = mc
        items = [item(p, "", (cat.get(p, {}).get("secciones") or [""])[0], p not in visibles,
                      f"lista de la comunidad: {mid}" + (" · app visible: ¿la usan?" if p in visibles else ""))
                 for p in m["paquetes"] if p in habilitadas and not prohibido(perfil, p)]
        return {"fuente": f"lista de la comunidad para {m['tv'] or mid}", "items": items}

    items = []
    for p in sorted(habilitadas):
        datos = cat.get(p)
        if not datos or datos["modelos"] < 3 or prohibido(perfil, p):
            continue
        visible = p in visibles
        items.append(item(p, "", (datos["secciones"] or [""])[0], datos["modelos"] >= 20 and not visible,
                          f"catálogo: lo desactivan {datos['modelos']} modelos" + (" · app visible: ¿la usan?" if visible else "")))
    items.sort(key=lambda x: -x["modelos"])
    return {"fuente": "catálogo general (sin perfil ni lista de este modelo): revisar cada una", "items": items}
