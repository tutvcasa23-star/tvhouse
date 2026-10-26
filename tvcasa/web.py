"""Servidor local (solo 127.0.0.1) con la pantalla de TV Casa. Las acciones corren en segundo plano con registro."""
from __future__ import annotations

import json
import secrets
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import acciones, claude, perfiles
from .adb import RAIZ, Adb, AdbError

ESTATICO = Path(__file__).resolve().parent / "static"
CONFIG = RAIZ / "datos" / "config.json"
CLAVE = secrets.token_urlsafe(24)   # protege contra páginas web que intenten usar el servidor local
TRABAJOS: dict[str, dict] = {}


def config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {"tvs": [], "carpeta_fondo": str(Path.home() / "Fotos-TV"),
            "carpeta_protector": str(Path.home() / "Fotos-TV" / "protector")}


def guardar_config(c: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def lanzar(nombre: str, ip: str, fn) -> str:
    tid = uuid.uuid4().hex[:10]
    t = {"id": tid, "accion": nombre, "ip": ip, "estado": "corriendo", "registro": [], "resultado": None}
    TRABAJOS[tid] = t

    def correr():
        tv = acciones.Tv(ip, log=t["registro"].append)
        try:
            t["resultado"] = fn(tv)
            t["estado"] = "listo"
        except acciones.Detenido as e:
            t["registro"].append(f"DETENIDO: {e}")
            t["estado"] = "detenido"
        except AdbError as e:
            t["registro"].append(f"ERROR ADB: {e}")
            t["estado"] = "error"
        except Exception as e:  # cualquier otra cosa queda en el registro para consultarla
            t["registro"].append(f"ERROR: {e}\n{traceback.format_exc(limit=3)}")
            t["estado"] = "error"

    threading.Thread(target=correr, daemon=True).start()
    return tid


def accion(ip: str, nombre: str, p: dict) -> str:
    cfg = config()

    def perfil_de(tv: acciones.Tv) -> dict:
        i = tv.info()
        return perfiles.cargar_todos()[i["perfil"]]

    tabla = {
        "info": lambda tv: recordar_nombre(tv.info()),
        "propuesta": lambda tv: tv.propuesta(),
        "respaldo": lambda tv: str(tv.respaldo()),
        "limpieza": lambda tv: (tv.respaldo(), tv.desactivar(p.get("paquetes", []), perfil_de(tv)))[1],
        "desinstalar": lambda tv: (tv.respaldo(), tv.desinstalar(p.get("paquetes", [])))[1],
        "cache": lambda tv: tv.liberar_cache(),
        "lanzador": lambda tv: (tv.respaldo(), tv.lanzador(perfil_de(tv), bool(p.get("forzar"))))[1],
        "quitar_redireccion": lambda tv: tv.quitar_redireccion(),
        "complementos": lambda tv: [tv.complemento(c) for c in p.get("complementos", ["fotos", "smarthome"])],
        "fondo": lambda tv: tv.fondo(Path(p.get("carpeta") or cfg["carpeta_fondo"]), perfil_de(tv),
                                    int(p.get("minutos", 10)), int(p.get("oscurecer", 25)), bool(p.get("sobrio"))),
        "fotos": lambda tv: tv.fotos(Path(p.get("carpeta") or cfg["carpeta_protector"]),
                                    int(p.get("segundos", 20)), int(p.get("minutos", 10))),
        "pruebas": lambda tv: tv.pruebas(),
        "restaurar": lambda tv: tv.restaurar(respaldo_valido(p.get("respaldo", ""))),
    }
    if nombre not in tabla:
        raise ValueError(f"acción desconocida: {nombre}")
    if nombre == "restaurar":
        respaldo_valido(p.get("respaldo", ""))  # rechazar antes de lanzar el trabajo
    return lanzar(nombre, ip, tabla[nombre])


def recordar_nombre(info: dict) -> dict:
    """Guarda en la lista de TV el nombre del perfil o el modelo, para no ver solo la IP."""
    cfg = config()
    nombre = info["perfil_nombre"] if info["perfil"] != "generico" else f"{info['fabricante']} {info['modelo']}"
    tv = next((t for t in cfg["tvs"] if t["ip"] == info["ip"]), None)
    if tv is None:
        cfg["tvs"].append({"ip": info["ip"], "nombre": nombre})
    elif not tv.get("nombre"):
        tv["nombre"] = nombre
    else:
        return info
    guardar_config(cfg)
    return info


def respaldo_valido(ruta: str) -> Path:
    """Solo archivos dentro de datos/respaldos (la página no puede pedir otro archivo del disco)."""
    base = (RAIZ / "datos" / "respaldos").resolve()
    r = Path(ruta).resolve()
    if base not in r.parents or r.suffix != ".json" or not r.is_file():
        raise ValueError("respaldo inválido")
    return r


def respaldos(ip: str) -> list[str]:
    base = RAIZ / "datos" / "respaldos"
    return sorted((str(p) for p in base.glob(f"*-{ip.replace('.', '-')}/*.json")), reverse=True) if base.exists() else []


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencioso en la consola
        pass

    def _json(self, datos, codigo: int = 200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _autorizado(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-TVCasa", ""), CLAVE)

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta in ("/", "/index.html"):
            html = (ESTATICO / "index.html").read_text(encoding="utf-8").replace("__CLAVE__", CLAVE)
            cuerpo = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        if not self._autorizado():
            return self._json({"error": "no autorizado"}, 403)
        if ruta == "/api/tvs":   # los ya conocidos, al instante
            cfg = config()
            return self._json({"tvs": cfg["tvs"], "config": cfg})
        if ruta == "/api/buscar":   # escucha la red unos segundos (mDNS) y devuelve los TV que se anuncian
            try:
                return self._json({"encontrados": Adb().descubrir()})
            except AdbError as e:
                return self._json({"error": str(e)}, 500)
        if ruta.startswith("/api/trabajo/"):
            t = TRABAJOS.get(ruta.rsplit("/", 1)[1])
            return self._json(t or {"error": "no existe"}, 200 if t else 404)
        if ruta.startswith("/api/respaldos/"):
            return self._json({"respaldos": respaldos(ruta.rsplit("/", 1)[1])})
        if ruta.startswith("/api/perfil/"):
            return self._json(perfiles.cargar_todos().get(ruta.rsplit("/", 1)[1], {}))
        self._json({"error": "no existe"}, 404)

    def do_POST(self):
        if not self._autorizado():
            return self._json({"error": "no autorizado"}, 403)
        largo = int(self.headers.get("Content-Length", "0") or 0)
        p = json.loads(self.rfile.read(largo) or b"{}")
        ruta = urlparse(self.path).path
        try:
            if ruta == "/api/conectar":
                Adb().conectar(p["ip"])
                cfg = config()
                if not any(t["ip"] == p["ip"] for t in cfg["tvs"]):
                    cfg["tvs"].append({"ip": p["ip"], "nombre": p.get("nombre", "")})
                    guardar_config(cfg)
                return self._json({"ok": True})
            if ruta == "/api/accion":
                return self._json({"trabajo": accion(p["ip"], p["accion"], p.get("parametros", {}))})
            if ruta == "/api/claude":
                t = TRABAJOS.get(p.get("trabajo", ""))
                registro = t["registro"] if t else None
                contexto = p.get("contexto")
                return self._json({"respuesta": claude.consultar(p["pregunta"], contexto, registro)})
        except (AdbError, KeyError, ValueError) as e:
            return self._json({"error": str(e)}, 400)
        self._json({"error": "no existe"}, 404)


def servir(puerto: int = 8765) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    srv.daemon_threads = True   # al cerrar la ventana, no esperar consultas a TV que estén en curso
    return srv
