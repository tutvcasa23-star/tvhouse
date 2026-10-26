"""TV Casa: `python -m tvcasa` abre la pantalla en el navegador. `python -m tvcasa pruebas <ip>` corre solo las pruebas."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser

from . import acciones, web


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # la consola de Windows no es UTF-8
    ap = argparse.ArgumentParser(prog="tvcasa", description="Configura los TV de la casa por ADB.")
    ap.add_argument("comando", nargs="?", default="abrir", choices=["abrir", "info", "pruebas", "respaldo"])
    ap.add_argument("ip", nargs="?")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    ap.add_argument("--navegador", action="store_true", help="usar el navegador en vez de la ventana propia")
    a = ap.parse_args()

    if a.comando != "abrir":
        if not a.ip:
            ap.error("falta la IP del TV")
        tv = acciones.Tv(a.ip)
        tv.adb.conectar(a.ip)
        res = {"info": tv.info, "pruebas": tv.pruebas, "respaldo": lambda: str(tv.respaldo())}[a.comando]()
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if not a.navegador and not a.sin_navegador:
        try:
            from . import ventana
            ventana.abrir()
            return 0
        except ImportError:
            print("Sin pywebview: se abre en el navegador.")

    srv = web.servir(a.puerto)
    url = f"http://127.0.0.1:{a.puerto}/"
    print(f"TV Casa en {url}  (Ctrl+C para cerrar)")
    if not a.sin_navegador:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
