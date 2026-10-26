"""TV Casa en su propia ventana (Edge WebView2 en Windows, WebKit en Mac): sin navegador ni consola."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from . import web

ICONO = Path(__file__).resolve().parent / "static" / "tvcasa.ico"
APP_ID = "TVCasa.Casa.1"  # identidad propia en la barra de tareas de Windows (si no, agrupa con Python)


class Api:
    """Funciones que la pantalla puede llamar en la ventana (no existen en el modo navegador).

    Todo atributo público de esta clase lo recorre pywebview para exponerlo a la página: la ventana va en
    `_ventana` (privado). Como atributo público, pywebview recorría la ventana nativa entera y la app se colgaba.
    """

    def __init__(self):
        self._ventana = None

    def elegir_carpeta(self, inicial: str = "") -> str:
        import webview
        r = self._ventana.create_file_dialog(webview.FileDialog.FOLDER,
                                            directory=inicial if Path(inicial or ".").is_dir() else "")
        return r[0] if r else ""


def _identidad_windows() -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def _icono_windows(ventana) -> None:
    """La ventana de pywebview (WinForms) toma el ícono de pythonw.exe; se lo cambiamos por el de TV Casa."""
    if sys.platform != "win32" or not ICONO.exists():
        return
    try:
        import clr  # pythonnet, viene con pywebview en Windows
        clr.AddReference("System.Drawing")
        from System import Action
        from System.Drawing import Icon

        forma = ventana.native
        # BeginInvoke (sin esperar): con Invoke la ventana se colgaba, porque pywebview espera a este manejador
        # en el mismo hilo de la ventana al que Invoke le pide el cambio.
        forma.BeginInvoke(Action(lambda: setattr(forma, "Icon", Icon(str(ICONO)))))
    except Exception:
        pass  # sin ícono propio la app funciona igual


def _medidas(webview) -> tuple[int, int, int, int]:
    """1280x880 como máximo, sin pasar el 92 % de la pantalla, y centrada."""
    try:
        p = webview.screens[0]
        ancho, alto = min(1280, int(p.width * 0.92)), min(880, int(p.height * 0.88))
        return ancho, alto, p.x + (p.width - ancho) // 2, p.y + (p.height - alto) // 2
    except Exception:
        return 1100, 700, None, None


def abrir() -> None:
    import webview

    _identidad_windows()
    srv = web.servir(0)  # puerto libre cualquiera, solo en 127.0.0.1
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api = Api()
    ancho, alto, x, y = _medidas(webview)
    api._ventana = webview.create_window("TV Casa", f"http://127.0.0.1:{srv.server_address[1]}/", js_api=api,
                                        width=ancho, height=alto, x=x, y=y, min_size=(900, 600))
    api._ventana.events.shown += lambda: threading.Thread(target=_icono_windows, args=(api._ventana,), daemon=True).start()
    webview.start()
    srv.shutdown()
