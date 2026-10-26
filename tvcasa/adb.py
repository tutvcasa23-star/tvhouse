"""Acceso a los TV por ADB (depuración de red). Todo pasa por esta clase para poder probarla sin TV."""
from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Sin esto, desde la ventana (pythonw) cada llamada a adb.exe abre una consola negra en Windows.
OCULTO = {"creationflags": subprocess.CREATE_NO_WINDOW} if platform.system() == "Windows" else {}

PUERTO_CAST = 8009      # Google Cast: de esto dependen las fotos por HA
PUERTO_CONTROL = 6466   # Android TV Remote: lo usa Home Assistant


class AdbError(RuntimeError):
    pass


def buscar_adb() -> str:
    """adb incluido en la app, luego el de herramientas del usuario, luego el del PATH."""
    exe = "adb.exe" if platform.system() == "Windows" else "adb"
    candidatos = [
        RAIZ / "herramientas" / "platform-tools" / exe,
        Path.home() / "herramientas" / "platform-tools" / exe,
    ]
    for c in candidatos:
        if c.is_file():
            return str(c)
    en_path = shutil.which("adb")
    if en_path:
        return en_path
    raise AdbError("No encuentro ADB. Corre el instalador (instalar.ps1 / instalar.sh).")


def puerto_abierto(ip: str, puerto: int, espera: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, puerto), timeout=espera):
            return True
    except OSError:
        return False


class Adb:
    def __init__(self, ruta: str | None = None):
        self.ruta = ruta or buscar_adb()

    def _correr(self, args: list[str], tiempo: int = 60) -> str:
        r = subprocess.run([self.ruta, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=tiempo, **OCULTO)
        salida = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            raise AdbError(salida.strip() or f"adb {' '.join(args)} falló ({r.returncode})")
        return salida

    # --- conexión -------------------------------------------------------------------------
    def conectar(self, ip: str) -> str:
        out = self._correr(["connect", f"{ip}:5555"], 30).strip()
        estado = self.estado(ip)
        if estado != "device":
            if estado == "unauthorized":
                raise AdbError("El TV pide autorización: acepta 'Permitir depuración' en la pantalla del TV.")
            raise AdbError(f"No conecta con {ip}: {out}. ¿Está activa la depuración de red?")
        return out

    def estado(self, ip: str) -> str:
        for linea in self._correr(["devices"], 15).splitlines():
            partes = linea.split()
            if len(partes) >= 2 and partes[0] == f"{ip}:5555":
                return partes[1]
        return "desconectado"

    def descubrir(self, escuchar: float = 6.0) -> list[str]:
        """IPs de TV que anuncian ADB por la red (mDNS). Recién arrancado, adb necesita unos segundos para oír
        los anuncios: se pregunta varias veces durante `escuchar` segundos."""
        encontrados: set[str] = set()
        fin = time.monotonic() + escuchar
        while True:
            try:
                out = self._correr(["mdns", "services"], 15)
                encontrados |= set(re.findall(r"_adb\._tcp\.?\s+(\d+\.\d+\.\d+\.\d+):5555", out))
            except AdbError:
                pass
            if time.monotonic() >= fin:
                return sorted(encontrados)
            time.sleep(1.5)

    # --- comandos -------------------------------------------------------------------------
    def shell(self, ip: str, comando: str, tiempo: int = 60) -> str:
        return self._correr(["-s", f"{ip}:5555", "shell", comando], tiempo)

    def push(self, ip: str, origen: str, destino: str) -> str:
        return self._correr(["-s", f"{ip}:5555", "push", origen, destino], 600)

    def instalar(self, ip: str, apk: str) -> str:
        out = self._correr(["-s", f"{ip}:5555", "install", "-r", apk], 300)
        if "Success" not in out:
            raise AdbError(f"No se pudo instalar {Path(apk).name}: {out}")
        return out

    def captura(self, ip: str) -> bytes:
        r = subprocess.run([self.ruta, "-s", f"{ip}:5555", "exec-out", "screencap", "-p"],
                           capture_output=True, timeout=60, **OCULTO)
        datos = r.stdout
        i = datos.find(b"\x89PNG")  # algunos firmwares imprimen basura antes del PNG
        if r.returncode != 0 or i < 0:
            raise AdbError("No se pudo capturar la pantalla")
        return datos[i:]

