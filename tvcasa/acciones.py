"""Todo lo que la app le hace a un TV. Cada acción verifica y, si algo se rompe, deshace lo último.

Reglas (las mismas que se probaron a mano en TVs reales):
- Desactivar, nunca desinstalar apps del sistema; de a una; comprobar Cast (8009) y control (6466) después de cada una.
- Nunca tocar lo que el perfil marca como 'nunca'.
- Antes de cambiar algo, respaldo del estado.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import imagenes, perfiles
from .adb import PUERTO_CAST, PUERTO_CONTROL, RAIZ, Adb, puerto_abierto

DATOS = RAIZ / "datos"
APKS = RAIZ / "apks"
LANZADOR = "com.gathin.tvhome"
FOTOS = "com.gathin.photodream"
SMART_HOME = "io.github.maxhayim.smarthome"
TMP_TV = "/data/local/tmp/tvcasa"


class Detenido(RuntimeError):
    """Se detuvo una acción para proteger el TV (lo que se alcanzó a cambiar ya se deshizo)."""


class Tv:
    def __init__(self, ip: str, adb: Adb | None = None, log: Callable[[str], None] = print,
                 comprobar_puertos: Callable[[str, int], bool] = puerto_abierto):
        self.ip = ip
        self.adb = adb or Adb()
        self.log = log
        self._puerto = comprobar_puertos

    # --- utilidades ---------------------------------------------------------------------
    def sh(self, comando: str, tiempo: int = 60) -> str:
        return self.adb.shell(self.ip, comando, tiempo).replace("\r", "")

    def prop(self, nombre: str) -> str:
        return self.sh(f"getprop {nombre}").strip()

    def puertos(self) -> dict[str, bool]:
        return {"cast": self._puerto(self.ip, PUERTO_CAST), "control": self._puerto(self.ip, PUERTO_CONTROL)}

    def paquetes(self, filtro: str = "") -> set[str]:
        return {l.split(":", 1)[1].strip() for l in self.sh(f"pm list packages {filtro}").splitlines() if l.startswith("package:")}

    def inicio_actual(self) -> str:
        lineas = [l.strip() for l in self.sh(
            "cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME").splitlines() if l.strip()]
        return lineas[-1] if lineas else ""

    def pantalla_actual(self) -> str:
        m = re.search(r"mResumedActivity: \S+ \S+ (\S+)", self.sh("dumpsys activity activities | grep -m1 mResumedActivity"))
        return m.group(1) if m else ""

    def libre(self) -> dict:
        partes = self.sh("df -k /data | tail -1").split()
        total, usado, libre = (int(x) * 1024 for x in partes[1:4])
        return {"total": total, "usado": usado, "libre": libre, "pct": round(usado * 100 / total) if total else 0}

    # --- información -----------------------------------------------------------------------
    def info(self) -> dict:
        fab, mod = self.prop("ro.product.manufacturer"), self.prop("ro.product.model")
        perfil = perfiles.detectar(fab, mod)
        mem = dict(re.findall(r"(MemTotal|MemAvailable):\s+(\d+)", self.sh("head -3 /proc/meminfo")))
        return {
            "ip": self.ip, "fabricante": fab, "modelo": mod,
            "android": self.prop("ro.build.version.release"),
            "parche": self.prop("ro.build.version.security_patch"),
            "perfil": perfil["id"], "perfil_nombre": perfil["nombre"],
            "almacenamiento": self.libre(),
            "ram_mb": {k: int(v) // 1024 for k, v in mem.items()},
            "inicio": self.inicio_actual(),
            "desactivadas": sorted(self.paquetes("-d")),
            "apps_usuario": sorted(self.paquetes("-3")),
            "puertos": self.puertos(),
        }

    def propuesta(self) -> dict:
        fab, mod = self.prop("ro.product.manufacturer"), self.prop("ro.product.model")
        perfil = perfiles.detectar(fab, mod)
        claves = [mod, self.prop("ro.product.device"), self.prop("ro.product.name")] + mod.replace("_", " ").split()
        prop = perfiles.propuesta(perfil, self.paquetes("-e"), claves, self.visibles())
        prop["desinstalar"] = [c for c in perfil.get("desinstalar", []) if c["paquete"] in self.paquetes("-3")]
        prop["lanzador_permitido"] = self.lanzador_permitido(perfil)
        return prop

    def visibles(self) -> set[str]:
        """Apps con ícono en el inicio del TV (las que la familia ve y quizá usa)."""
        out = self.sh("cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LEANBACK_LAUNCHER")
        return {l.strip().split("/")[0] for l in out.splitlines() if "/" in l}

    def lanzador_permitido(self, perfil: dict) -> bool:
        """Probado en casa, o Android TV clásico (inicio tvlauncher): ahí la comunidad no reporta bucles de reinicio."""
        return bool(perfil.get("lanzador_permitido")) or self.inicio_actual().startswith("com.google.android.tvlauncher/")

    # --- respaldo y restauración -----------------------------------------------------------
    def respaldo(self) -> Path:
        i = self.info()
        estado = {
            "fecha": datetime.now().isoformat(timespec="seconds"), **i,
            "protector": self.sh("settings get secure screensaver_components").strip(),
            "protector_activo": self.sh("settings get secure screensaver_enabled").strip(),
            "apagado_pantalla_ms": self.sh("settings get system screen_off_timeout").strip(),
        }
        carpeta = DATOS / "respaldos" / f"{i['perfil']}-{self.ip.replace('.', '-')}"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{datetime.now():%Y%m%d-%H%M%S}.json"
        ruta.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(f"Respaldo guardado: {ruta.name} ({len(estado['desactivadas'])} apps desactivadas, inicio {estado['inicio']})")
        return ruta

    def restaurar(self, ruta: Path) -> None:
        r = json.loads(Path(ruta).read_text(encoding="utf-8"))
        antes = set(r["desactivadas"])
        for p in sorted(self.paquetes("-d") - antes):
            self.log(f"Reactivo {p}: {self.sh(f'pm enable {p}').strip()}")
        inicio = r.get("inicio", "")
        if inicio and self.inicio_actual() != inicio:
            pkg = inicio.split("/")[0]
            self.sh(f"pm enable {pkg}")
            self.log(f"Inicio vuelve a {inicio}: {self.sh(f'cmd package set-home-activity --user 0 {inicio}').strip()}")
            self.sh("input keyevent KEYCODE_HOME")
        for clave, comando in (("protector", "settings put secure screensaver_components"),
                               ("protector_activo", "settings put secure screensaver_enabled"),
                               ("apagado_pantalla_ms", "settings put system screen_off_timeout")):
            valor = r.get(clave, "")
            if valor and valor != "null":
                self.sh(f"{comando} {valor}")
        self.log(f"Restaurado al estado del {r['fecha']}. Puertos: {self.puertos()}")

    # --- limpieza ------------------------------------------------------------------------
    def desactivar(self, lista: list[str], perfil: dict) -> list[str]:
        base = self.puertos()
        instaladas, ya = self.paquetes(), self.paquetes("-d")
        hechas = []
        for p in lista:
            if perfiles.prohibido(perfil, p):
                self.log(f"OMITIDA {p}: el perfil la marca como 'nunca tocar'")
                continue
            if p not in instaladas:
                continue
            if p in ya:
                self.log(f"{p}: ya estaba desactivada")
                continue
            self.log(f"Desactivo {p}: {self.sh(f'pm disable-user --user 0 {p}').strip()}")
            time.sleep(1)
            ahora = self.puertos()
            rotos = [k for k in base if base[k] and not ahora[k]]
            if rotos:
                self.sh(f"pm enable {p}")
                raise Detenido(f"Al desactivar {p} dejó de responder {', '.join(rotos)}: la reactivé y me detuve.")
            hechas.append(p)
        self.log(f"Listo: {len(hechas)} desactivadas. Cast {'OK' if base['cast'] else 'no estaba'}, control {'OK' if base['control'] else 'no estaba'}.")
        return hechas

    def desinstalar(self, lista: list[str]) -> None:
        de_usuario = self.paquetes("-3")
        for p in lista:
            if p in de_usuario:
                self.log(f"Desinstalo {p}: {self.adb._correr(['-s', f'{self.ip}:5555', 'uninstall', p]).strip()}")

    def liberar_cache(self) -> None:
        antes = self.libre()["libre"]
        self.sh("pm trim-caches 100G", 300)
        despues = self.libre()["libre"]
        self.log(f"Caché borrada: +{(despues - antes) // 2**20} MB (libres {despues // 2**20} MB)")

    # --- archivos dentro de una app (fondo, fotos) -----------------------------------------
    def _escribir_en_app(self, pkg: str, autoridad: str, relativo: str, local: Path) -> None:
        """Por el ContentProvider de la app (queda como dueña); si el TV no lo soporta (Android 9), copia directa."""
        tmp = f"{TMP_TV}-{relativo.replace('/', '-')}"
        self.adb.push(self.ip, str(local), tmp)
        destino = f"/sdcard/Android/data/{pkg}/files/{relativo}"
        self.sh(f"rm -f {destino}; o=$(content write --uri content://{autoridad}/{relativo} < {tmp} 2>&1) "
                f"&& case \"$o\" in *Unsupported*|*rror*) false ;; esac "
                f"|| {{ mkdir -p $(dirname {destino}); cp {tmp} {destino}; }}; rm -f {tmp}", 300)

    def _reiniciar_inicio(self) -> None:
        self.sh(f"am force-stop {LANZADOR}; am start -a android.intent.action.MAIN -c android.intent.category.HOME")

    # --- lanzador, fondo, fotos ----------------------------------------------------------
    def es_google_tv(self) -> bool:
        return self.inicio_actual().startswith("com.google.android.apps.tv.launcherx/") or             "com.google.android.apps.tv.launcherx" in self.paquetes("-d")

    def _config_inicio(self, extra: dict) -> None:
        """config.json del inicio nuevo; en Google TV siempre incluye la redirección del inicio de Google."""
        cfg = dict(extra)
        if self.es_google_tv():
            cfg["stock_home_redirect"] = "com.google.android.apps.tv.launcherx"
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "config.json"
            p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            self._escribir_en_app(LANZADOR, f"{LANZADOR}.theme", "config.json", p)

    def lanzador_redireccion(self, perfil: dict) -> None:
        """Google TV: el inicio de Google queda activo (quitarlo causa reinicios en bucle en algunos equipos) y el
        servicio 'Botón Inicio' del inicio nuevo lo reemplaza cada vez que aparece. Se revierte con quitar_redireccion."""
        self.log(f"Instalo el inicio nuevo: {self.adb.instalar(self.ip, str(APKS / 'lanzador.apk')).strip().splitlines()[-1]}")
        self._config_inicio({"live_tv_package": perfil["tv_en_vivo"]} if perfil.get("tv_en_vivo") else {})
        svc = f"{LANZADOR}/.HomeKeyService"
        actuales = self.sh("settings get secure enabled_accessibility_services").strip()
        lista = svc if actuales in ("", "null") else (actuales if svc in actuales else f"{actuales}:{svc}")
        self.sh(f"am force-stop {LANZADOR}; cmd appops set {LANZADOR} AUTO_START allow 2>/dev/null; "
                f"settings put secure enabled_accessibility_services {lista}; settings put secure accessibility_enabled 1")
        time.sleep(3)
        if "HomeKeyService" not in self.sh("dumpsys accessibility | grep -i 'enabled services' || true"):
            raise Detenido("El servicio 'Botón Inicio' no quedó activo; el inicio de Google sigue como estaba.")
        self.log(f"Redirección activa: al apretar Inicio se abre el inicio nuevo. Puertos: {self.puertos()}")

    def quitar_redireccion(self) -> None:
        svc = f"{LANZADOR}/.HomeKeyService"
        actuales = [s for s in self.sh("settings get secure enabled_accessibility_services").strip().split(":") if s and s != "null"]
        resto = ":".join(s for s in actuales if s != svc)
        self.sh(f"settings put secure enabled_accessibility_services '{resto}'" + ("" if resto else "; settings put secure accessibility_enabled 0"))
        self.log("Redirección quitada: el inicio de Google vuelve a ser el único.")

    def lanzador(self, perfil: dict, forzar: bool = False) -> None:
        if self.es_google_tv() and not forzar:
            return self.lanzador_redireccion(perfil)
        if not self.lanzador_permitido(perfil) and not forzar:
            raise Detenido(f"El perfil {perfil['id']} no permite cambiar el inicio todavía ({perfil.get('nota', '')}).")
        original = perfil.get("inicio_original") or self.inicio_actual().split("/")[0]
        anterior = self.inicio_actual()
        self.log(f"Instalo el inicio nuevo: {self.adb.instalar(self.ip, str(APKS / 'lanzador.apk')).strip().splitlines()[-1]}")
        self.log(f"Desactivo el inicio original {original}: {self.sh(f'pm disable-user --user 0 {original}').strip()}")
        self.sh(f"cmd package set-home-activity --user 0 {LANZADOR}/.MainActivity")
        self.sh("input keyevent KEYCODE_HOME")
        time.sleep(6)
        if LANZADOR not in self.pantalla_actual():
            self.sh(f"pm enable {original}")
            self.sh(f"cmd package set-home-activity --user 0 {anterior}")
            self.sh("input keyevent KEYCODE_HOME")
            raise Detenido("El inicio nuevo no tomó el control; volví al original.")
        self.log(f"Inicio nuevo activo. Puertos: {self.puertos()}")

    def complemento(self, nombre: str) -> None:
        apk = {"fotos": "fotos.apk", "smarthome": "smart-home.apk"}[nombre]
        self.log(f"Instalo {apk}: {self.adb.instalar(self.ip, str(APKS / apk)).strip().splitlines()[-1]}")

    def fondo(self, carpeta: Path, perfil: dict, minutos: int = 10, oscurecer: int = 25, sobrio: bool = False) -> int:
        if LANZADOR not in self.paquetes():
            raise Detenido("Primero hay que instalar el inicio nuevo.")
        fotos = imagenes.listar(carpeta)
        if not fotos:
            raise Detenido(f"No hay fotos en {carpeta}")
        cfg = {"wallpaper": True, "wallpaper_rotation_minutes": minutos if len(fotos) > 1 else 0,
               "wallpaper_order": "shuffle", "wallpaper_dim": oscurecer, "dock_glass": True, "dock_opacity": 50}
        if perfil.get("tv_en_vivo"):
            cfg["live_tv_package"] = perfil["tv_en_vivo"]
        if not sobrio:
            cfg.update(cinematic_home=True, cinematic_art=35, cinematic_scrim=60, app_glow=True, advanced_effects=True,
                       fade_rows=True, home_idle_clock_minutes=10, clock_wallpaper=True)
        self.sh(f"rm -rf /sdcard/Android/data/{LANZADOR}/files/wallpapers /sdcard/Android/data/{LANZADOR}/files/wallpaper.jpg")
        with tempfile.TemporaryDirectory() as t:
            for i, f in enumerate(fotos, 1):
                local = Path(t) / f"{i:03d}.jpg"
                imagenes.cubrir(f, local)
                self._escribir_en_app(LANZADOR, f"{LANZADOR}.theme", f"wallpapers/{local.name}", local)
                if len(fotos) == 1:
                    self._escribir_en_app(LANZADOR, f"{LANZADOR}.theme", "wallpaper.jpg", local)
            self._config_inicio(cfg)
        self._reiniciar_inicio()
        self.log(f"Fondo: {len(fotos)} foto(s), cambia cada {minutos} min, estilo {'sobrio' if sobrio else 'interactivo'}.")
        return len(fotos)

    def fotos(self, carpeta: Path, segundos: int = 20, minutos: int = 10) -> int:
        if FOTOS not in self.paquetes():
            raise Detenido("Primero hay que instalar el complemento Fotos.")
        archivos = imagenes.listar(carpeta, videos=True)[:100]
        if not archivos:
            raise Detenido(f"No hay fotos ni videos en {carpeta}")
        antes = "/data/local/tmp/cyt-screensaver-before"
        self.sh(f"[ -f {antes} ] || {{ settings get secure screensaver_components; settings get secure screensaver_enabled; "
                f"settings get system screen_off_timeout; }} > {antes}")
        self.sh(f"content delete --uri content://{FOTOS}.files/pictures 2>/dev/null; rm -f /sdcard/Android/data/{FOTOS}/files/pictures/*")
        with tempfile.TemporaryDirectory() as t:
            for i, f in enumerate(archivos, 1):
                es_video = f.suffix.lower() == ".mp4"
                local = Path(t) / imagenes.nombre_seguro(i, f, ".mp4" if es_video else ".jpg")
                shutil.copy(f, local) if es_video else imagenes.achicar(f, local)
                self.log(f"Subo {local.name}")
                self._escribir_en_app(FOTOS, f"{FOTOS}.files", f"pictures/{local.name}", local)
            seg = Path(t) / "seconds.txt"
            seg.write_text(str(segundos), encoding="ascii")
            self._escribir_en_app(FOTOS, f"{FOTOS}.files", "seconds.txt", seg)
        self.sh(f"settings put secure screensaver_components {FOTOS}/.PhotoDream; settings put secure screensaver_enabled 1; "
                f"settings put system screen_off_timeout {minutos * 60000}")
        self.log(f"Protector Fotos: {len(archivos)} archivo(s), {segundos} s por foto, arranca tras {minutos} min.")
        return len(archivos)

    def captura(self, destino: Path) -> Path:
        destino.write_bytes(self.adb.captura(self.ip))
        return destino

    # --- pruebas e informe -----------------------------------------------------------------
    def pruebas(self) -> dict:
        i = self.info()
        perfil = perfiles.cargar_todos()[i["perfil"]]
        r: list[dict] = []

        def anota(nombre: str, ok: bool | None, detalle: str):
            r.append({"prueba": nombre, "estado": "ok" if ok else ("aviso" if ok is None else "falla"), "detalle": detalle})

        anota("Google Cast (8009)", i["puertos"]["cast"], "Fotos desde HA y transmitir desde el teléfono")
        anota("Control remoto (6466)", i["puertos"]["control"], "Home Assistant enciende/apaga y maneja el volumen")
        a = i["almacenamiento"]
        anota("Espacio libre", a["libre"] >= 1.5 * 2**30 or (None if a["libre"] >= 500 * 2**20 else False),
              f"{a['libre'] // 2**20} MB libres ({a['pct']} % usado); para actualizar conviene ≥ 1,5 GB")
        anota("Inicio", True if i["inicio"] else False, i["inicio"] or "sin inicio: revisar ya")
        pendientes = [x["paquete"] for x in self.propuesta()["items"] if x["marcado"]]
        anota("Limpieza propuesta", None if pendientes else True,
              f"pendientes: {', '.join(pendientes)}" if pendientes else "nada pendiente de lo recomendado")
        # El inicio original desactivado es lo esperado cuando manda el inicio nuevo.
        reemplazado = i["inicio"].startswith(LANZADOR) and (perfil.get("inicio_original") or "com.google.android.tvlauncher")
        tocadas = [p for p in i["desactivadas"] if perfiles.prohibido(perfil, p) and p != reemplazado]
        anota("Nada prohibido desactivado", not tocadas, ", ".join(tocadas) or "ok")
        anota("Parche de seguridad", None, i["parche"])
        anota("Depuración de red activa", None, "recordar apagarla al terminar (cualquiera en la red puede controlar el TV)")
        resultado = {"fecha": datetime.now().isoformat(timespec="seconds"), "tv": i, "pruebas": r}
        carpeta = DATOS / "informes"
        carpeta.mkdir(parents=True, exist_ok=True)
        base = carpeta / f"{datetime.now():%Y%m%d-%H%M}-{i['perfil']}-{self.ip.replace('.', '-')}"
        base.with_suffix(".json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        base.with_suffix(".md").write_text(informe_md(resultado), encoding="utf-8")
        self.log(f"Informe: {base.name}.md — " + ", ".join(f"{x['prueba']}: {x['estado']}" for x in r))
        return resultado


def informe_md(res: dict) -> str:
    t = res["tv"]
    icono = {"ok": "✅", "aviso": "⚠️", "falla": "❌"}
    filas = "\n".join(f"| {x['prueba']} | {icono[x['estado']]} | {x['detalle']} |" for x in res["pruebas"])
    return (f"# Informe {t['perfil_nombre']} ({t['ip']}) · {res['fecha']}\n\n"
            f"{t['fabricante']} {t['modelo']}, Android {t['android']}, parche {t['parche']}. "
            f"RAM libre {t['ram_mb'].get('MemAvailable', '?')} MB.\n\n"
            f"| Prueba | Estado | Detalle |\n|---|---|---|\n{filas}\n")
