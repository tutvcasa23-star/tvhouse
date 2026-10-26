# APK incluidos

Compilados por nosotros el 2026-10-25 desde el código de [Clean Your TV](https://github.com/Gathin23/cleanyourtv)
(commit `5ee685b02014fa502ea0951ee1f49abd7ee2e8c1`, licencia MIT), con JDK 17 y Android SDK 34. Firmados con la llave
de depuración local (no vienen de una tienda).

| Archivo | Paquete | Origen en el repo | SHA-256 |
|---|---|---|---|
| `lanzador.apk` | `com.gathin.tvhome` 3.0 | `launcher/` (con `config.xml` propio: barra Netflix, YouTube, Disney+, Max, TDMás, Spotify) | `cedccd77d47ec90790e81214df2a92b39094e18cbc17ae1e008c91c2f27b4e76` |
| `fotos.apk` | `com.gathin.photodream` | `addons/photo-screensaver/` | `dd0fa74d7a6a30120031d7a678ebd212c2be0970a63a44ec74157c9189242aac` |
| `smart-home.apk` | `io.github.maxhayim.smarthome` | `addons/smart-home/` | `a79e90a86a33497b8100cb7516d9b73c8612ba4049aa85eed82998a0d265281a` |

Permisos especiales que piden (ubicación, escribir ajustes seguros): la app **no** los concede.

El lanzador trae ajustes propios en `launcher/app/src/main/res/values/config.xml`: barra con Netflix, YouTube,
Disney+, Max, TDMás y Spotify, y "TV en vivo" = `com.sony.dtv.tvx` (Sony). En otras marcas ese botón no abre nada:
recompilar con el paquete de TV en vivo de la marca.

Para recompilar: clonar Clean Your TV en ese commit, ajustar `config.xml` y, con JDK 17 y Android SDK 34, correr
`gradlew assembleDebug` en `launcher/`, `addons/photo-screensaver/` y `addons/smart-home/`.
