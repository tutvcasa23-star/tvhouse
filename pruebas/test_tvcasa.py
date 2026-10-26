"""Pruebas sin TV real: un TV simulado responde a los comandos ADB que usa la app."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from tvcasa import acciones, claude, imagenes, perfiles, web  # noqa: E402


class TvFalso:
    """Simula `adb shell` de un TV: paquetes instalados, desactivados y su inicio."""

    def __init__(self, fabricante="Sony", modelo="BRAVIA 4K GB", instalados=(), desactivados=(), usuario=()):
        self.props = {"ro.product.manufacturer": fabricante, "ro.product.model": modelo, "ro.product.device": "BRAVIA_ATV2",
                      "ro.product.name": "BRAVIA_ATV2_SA", "ro.build.version.release": "9",
                      "ro.build.version.security_patch": "2022-01-05"}
        self.instalados = set(instalados) | set(usuario)
        self.desactivados = set(desactivados)
        self.usuario = set(usuario)
        self.inicio = "com.google.android.tvlauncher/.MainActivity"
        self.comandos: list[str] = []
        self.accesibilidad = ""

    def shell(self, ip, cmd, tiempo=60):
        self.comandos.append(cmd)
        if cmd.startswith("getprop "):
            return self.props.get(cmd.split()[1], "") + "\n"
        if cmd.startswith("pm list packages"):
            f = cmd.split()[3] if len(cmd.split()) > 3 else ""
            conj = {"-d": self.desactivados, "-e": self.instalados - self.desactivados, "-3": self.usuario}.get(f, self.instalados)
            return "".join(f"package:{p}\n" for p in sorted(conj))
        if cmd.startswith("pm disable-user"):
            p = cmd.split()[-1]
            self.desactivados.add(p)
            return f"Package {p} new state: disabled-user\n"
        if cmd.startswith("pm enable"):
            self.desactivados.discard(cmd.split()[-1])
            return "ok\n"
        if cmd.startswith("cmd package resolve-activity"):
            return f"priority=0\n{self.inicio}\n"
        if cmd.startswith("df -k"):
            return "/dev/x 8000000 6000000 2000000 75% /data\n"
        if cmd.startswith("head -3 /proc/meminfo"):
            return "MemTotal: 2000000 kB\nMemFree: 1 kB\nMemAvailable: 400000 kB\n"
        if cmd.startswith("settings get secure enabled_accessibility_services"):
            return (self.accesibilidad or "null") + "\n"
        if "settings put secure enabled_accessibility_services" in cmd:
            self.accesibilidad = cmd.split("settings put secure enabled_accessibility_services", 1)[1].split(";")[0].strip().strip("'")
            return ""
        if cmd.startswith("dumpsys accessibility"):
            return "Enabled services:{{" + self.accesibilidad + "}}\n"
        if cmd.startswith("settings get"):
            return "null\n"
        return ""


class AdbFalso:
    def __init__(self, tv: TvFalso):
        self.tv = tv

    def instalar(self, ip, apk):
        self.tv.instalados.add("com.gathin.tvhome")
        return "Success"

    def push(self, ip, origen, destino):
        return "1 file pushed"

    def shell(self, ip, cmd, tiempo=60):
        return self.tv.shell(ip, cmd, tiempo)


def tv_simulado(falso: TvFalso, puertos=None, registro=None):
    estado = puertos if puertos is not None else {8009: True, 6466: True}
    return acciones.Tv("10.0.0.9", adb=AdbFalso(falso), log=(registro if registro is not None else []).append,
                       comprobar_puertos=lambda ip, p: estado[p])


class PruebasPerfiles(unittest.TestCase):
    def test_detecta_los_tres_tv_de_la_casa(self):
        self.assertEqual(perfiles.detectar("Sony", "BRAVIA 4K GB")["id"], "sony-bravia-atv9")
        self.assertEqual(perfiles.detectar("Changhong", "AI PONT SA")["id"], "jvc-changhong-gtv11")
        self.assertEqual(perfiles.detectar("KTC", "JVC 4K ISDB TV")["id"], "jvc-ktc-gtv11")
        self.assertEqual(perfiles.detectar("TCL", "Smart TV Pro")["id"], "generico")

    def test_nunca_toca_lo_critico(self):
        for p in ["com.google.android.apps.mediashell", "com.google.android.tv.remote.service", "com.android.vending",
                  "com.google.android.apps.tv.launcherx", "com.sony.dtv.tvinput.hdmi", "com.mediatek.wwtv.tvcenter",
                  "com.google.android.tungsten.setupwraith", "com.google.android.katniss", "com.google.android.gms"]:
            self.assertTrue(perfiles.prohibido(None, p), p)
        self.assertFalse(perfiles.prohibido(None, "com.google.android.feedback"))

    def test_ningun_perfil_propone_algo_prohibido(self):
        for pid, p in perfiles.cargar_todos().items():
            for c in p["desactivar"] + p.get("opcionales", []):
                self.assertFalse(perfiles.prohibido(p, c["paquete"]), f"{pid}: {c['paquete']}")

    def test_propuesta_de_perfil_solo_lo_activo(self):
        p = perfiles.cargar_todos()["sony-bravia-atv9"]
        r = perfiles.propuesta(p, {"tv.samba.ssm", "com.netflix.ninja"}, [])
        self.assertEqual([x["paquete"] for x in r["items"]], ["tv.samba.ssm"])
        self.assertTrue(r["items"][0]["marcado"])

    def test_tv_desconocido_usa_lista_de_la_comunidad_del_modelo(self):
        gen = perfiles.cargar_todos()["generico"]
        r = perfiles.propuesta(gen, {"tv.samba.ssm", "com.google.android.apps.mediashell"}, ["BRAVIA_ATV2"])
        self.assertIn("comunidad", r["fuente"])
        self.assertEqual([x["paquete"] for x in r["items"]], ["tv.samba.ssm"])

    def test_tv_desconocido_sin_lista_usa_catalogo(self):
        gen = perfiles.cargar_todos()["generico"]
        r = perfiles.propuesta(gen, {"com.google.android.feedback", "com.netflix.ninja",
                                     "com.google.android.apps.mediashell"}, ["zzzz-modelo-inexistente"],
                               visibles={"com.netflix.ninja"})
        self.assertIn("catálogo", r["fuente"])
        marcado = {x["paquete"]: x["marcado"] for x in r["items"]}
        self.assertTrue(marcado["com.google.android.feedback"])   # la desactivan más de 20 modelos
        self.assertFalse(marcado["com.netflix.ninja"])            # app visible: la decide la familia
        self.assertNotIn("com.google.android.apps.mediashell", marcado)


class PruebasAcciones(unittest.TestCase):
    def test_desactiva_y_verifica(self):
        falso = TvFalso(instalados={"tv.samba.ssm", "com.sony.dtv.sonyselect"})
        tv = tv_simulado(falso)
        hechas = tv.desactivar(["tv.samba.ssm", "com.sony.dtv.sonyselect", "no.instalada"], perfiles.cargar_todos()["sony-bravia-atv9"])
        self.assertEqual(hechas, ["tv.samba.ssm", "com.sony.dtv.sonyselect"])
        self.assertEqual(falso.desactivados, {"tv.samba.ssm", "com.sony.dtv.sonyselect"})

    def test_omite_prohibidas_aunque_se_pidan(self):
        falso = TvFalso(instalados={"com.google.android.apps.mediashell"})
        registro = []
        tv_simulado(falso, registro=registro).desactivar(["com.google.android.apps.mediashell"], perfiles.cargar_todos()["generico"])
        self.assertEqual(falso.desactivados, set())
        self.assertTrue(any("OMITIDA" in l for l in registro))

    def test_si_se_rompe_cast_reactiva_y_se_detiene(self):
        falso = TvFalso(instalados={"a.b.primera", "a.b.segunda"})
        puertos = {8009: True, 6466: True}
        tv = tv_simulado(falso, puertos)
        original = falso.shell

        def rompe_cast(ip, cmd, tiempo=60):
            if cmd.endswith("a.b.primera") and "disable" in cmd:
                puertos[8009] = False
            return original(ip, cmd, tiempo)

        falso.shell = rompe_cast
        with self.assertRaises(acciones.Detenido):
            tv.desactivar(["a.b.primera", "a.b.segunda"], perfiles.cargar_todos()["generico"])
        self.assertEqual(falso.desactivados, set())  # la primera se reactivó y la segunda ni se tocó

    def test_restaurar_reactiva_lo_desactivado_despues_del_respaldo(self):
        falso = TvFalso(instalados={"a.b.vieja", "a.b.nueva"}, desactivados={"a.b.vieja"})
        tv = tv_simulado(falso)
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "r.json"
            ruta.write_text(json.dumps({"fecha": "x", "desactivadas": ["a.b.vieja"], "inicio": falso.inicio}), encoding="utf-8")
            falso.desactivados.add("a.b.nueva")
            tv.restaurar(ruta)
        self.assertEqual(falso.desactivados, {"a.b.vieja"})

    def test_lanzador_permitido_en_android_tv_clasico_y_no_en_google_tv(self):
        falso = TvFalso(fabricante="TCL", modelo="X")
        tv = tv_simulado(falso)
        gen = perfiles.cargar_todos()["generico"]
        self.assertTrue(tv.lanzador_permitido(gen))
        falso.inicio = "com.google.android.apps.tv.launcherx/.home.HomeActivity"
        self.assertFalse(tv.lanzador_permitido(gen))


class PruebasGoogleTv(unittest.TestCase):
    def _gtv(self, servicios=""):
        falso = TvFalso(fabricante="Changhong", modelo="AI PONT SA",
                        instalados={"com.google.android.apps.tv.launcherx"})
        falso.inicio = "com.google.android.apps.tv.launcherx/.home.HomeActivity"
        falso.accesibilidad = servicios
        return falso, tv_simulado(falso)

    def test_en_google_tv_redirige_sin_desactivar_el_inicio_de_google(self):
        falso, tv = self._gtv("otra.app/.Servicio")
        acciones.time.sleep, original = (lambda s: None), acciones.time.sleep
        try:
            tv.lanzador(perfiles.cargar_todos()["jvc-changhong-gtv11"])
        finally:
            acciones.time.sleep = original
        self.assertNotIn("com.google.android.apps.tv.launcherx", falso.desactivados)
        self.assertEqual(falso.accesibilidad, "otra.app/.Servicio:com.gathin.tvhome/.HomeKeyService")

    def test_quitar_redireccion_deja_los_otros_servicios(self):
        falso, tv = self._gtv("otra.app/.Servicio:com.gathin.tvhome/.HomeKeyService")
        tv.quitar_redireccion()
        self.assertEqual(falso.accesibilidad, "otra.app/.Servicio")


class PruebasInforme(unittest.TestCase):
    def test_inicio_original_desactivado_no_es_falla_si_manda_el_nuevo(self):
        falso = TvFalso(instalados={"com.google.android.tvlauncher", "com.gathin.tvhome"},
                        desactivados={"com.google.android.tvlauncher"})
        falso.inicio = "com.gathin.tvhome/.MainActivity"
        tv = tv_simulado(falso)
        with tempfile.TemporaryDirectory() as t:
            acciones.DATOS, original = Path(t), acciones.DATOS
            try:
                r = tv.pruebas()
            finally:
                acciones.DATOS = original
        estado = {x["prueba"]: x["estado"] for x in r["pruebas"]}
        self.assertEqual(estado["Nada prohibido desactivado"], "ok")


class PruebasClaude(unittest.TestCase):
    def test_no_salen_mac_ni_tokens(self):
        t = claude.limpiar('mac 64:79:f0:ca:a8:23 token: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcDEF" password=hola123 sk-ant-api03-xyz')
        for secreto in ("64:79:f0", "eyJ", "hola123", "sk-ant"):
            self.assertNotIn(secreto, t)
        self.assertIn("com.sony.dtv.tvx", claude.limpiar("com.sony.dtv.tvx"))


class PruebasImagenes(unittest.TestCase):
    def test_recortes(self):
        with tempfile.TemporaryDirectory() as t:
            o = Path(t) / "vertical.png"
            Image.new("RGB", (1000, 3000), "red").save(o)
            imagenes.cubrir(o, Path(t) / "f.jpg")
            imagenes.achicar(o, Path(t) / "p.jpg")
            with Image.open(Path(t) / "f.jpg") as f, Image.open(Path(t) / "p.jpg") as p:
                self.assertEqual(f.size, (1920, 1080))
                self.assertEqual(max(p.size), 1920)
        self.assertEqual(imagenes.nombre_seguro(3, Path("Navidad 2025 (1).HEIC.jpg"), ".jpg"), "003-Navidad-2025--1--HEIC.jpg")


class PruebasWeb(unittest.TestCase):
    def test_restaurar_solo_acepta_respaldos(self):
        with self.assertRaises(ValueError):
            web.respaldo_valido(str(Path(__file__)))
        with self.assertRaises(ValueError):
            web.accion("10.0.0.9", "restaurar", {"respaldo": "C:/Windows/win.ini"})


if __name__ == "__main__":
    unittest.main()
