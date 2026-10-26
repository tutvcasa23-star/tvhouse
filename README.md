# TV House

[Español](README.es.md) · **English**

Set up any **Android TV / Google TV** over your home network, no AI required: remove bloatware, get a clean
Apple TV-style home screen, use your family photos and videos as wallpaper and screensaver, back up and roll back,
and get a test report. AI is only used if you press **"Consultar a Claude"** (Ask Claude) when something goes wrong.

Runs on **Windows and Mac**. The app's interface is in **Spanish**. Samsung (Tizen), LG (webOS) and other systems:
planned, see "Roadmap".

![Cleaning up a Sony BRAVIA: suggests what to disable and pre-selects the safest items](docs/img/limpieza.png)

| On launch | Test report |
|---|---|
| ![Welcome screen with the TVs on the network](docs/img/bienvenida.png) | ![Tests: Cast, remote, storage and home screen](docs/img/pruebas.png) |

![Home & photos in dark mode: clean home screen, add-ons, wallpaper and family photo screensaver](docs/img/inicio-oscuro.png)

*Screenshots use sample data. The app switches between light and dark mode automatically, following Windows or macOS.*

## Install

1. Python 3.10 or newer ([python.org](https://www.python.org/downloads/)).
2. Download the repo (**Code → Download ZIP**, or `git clone`) and, in that folder:
   - Windows: `powershell -ExecutionPolicy Bypass -File instalar.ps1`
   - Mac: `bash instalar.sh`

   It creates its own Python environment, installs `anthropic`, `pillow` and `pywebview`, downloads Google's official
   ADB (verifying its signature on Windows) and **runs the automated tests**. If any test fails, the app won't open.
3. Open it:
   - Windows: the **TV House** icon on the desktop or Start menu. It opens in **its own window** (Edge WebView2, built
     into Windows 11), with no browser or console. The "Elegir…" (Choose…) buttons open a folder picker.
   - Mac: double-click `abrir-tvhouse.command` (its own WebKit window).
   - To use a browser instead: `python -m tvcasa --navegador` (serves `http://127.0.0.1:8765`, this computer only).

On each TV: **Settings → System → About → click "Build" 7 times**, then **Developer options → Network / USB
debugging**. The first connection asks you to accept "Allow debugging" on the TV screen.

## What it does

| Tab | What it does | Safety |
|---|---|---|
| Limpieza (Cleanup) | Suggests what to disable and disables apps one at a time | Backup first; after each app it checks Google Cast (8009) and the remote (6466); if something breaks, it re-enables the app and stops. Never uninstalls system apps |
| Inicio y fotos (Home & photos) | Clean home screen (Clean Your TV), Photos and Smart Home add-ons, photo wallpaper, photo and video screensaver | If the new home screen doesn't take over, it switches back to the original on its own. On Google TV only with "forzar" (force) |
| Respaldo (Backup) | Saves the TV's state and restores any backup | Re-enables what was disabled afterwards, restores home screen and screensaver |
| Pruebas (Tests) | Cast, remote, storage, home screen, pending cleanup, nothing critical touched | `.md` and `.json` report in `datos/informes` |

### Where the cleanup suggestions come from (any TV)

1. **Profiles tested on real TVs** (`tvcasa/perfiles/`): Sony BRAVIA (Android TV 9), JVC/Changhong and JVC/KTC
   (Google TV 11).
2. **Community list for the same model**: 307 models from 87 brands from
   [Clean Your TV](https://github.com/Gathin23/cleanyourtv) (MIT), in `tvcasa/catalogo/`.
3. **General catalog**: apps active on your TV that other models have disabled. Pre-selected only if 20+ models did
   so; apps visible on the home screen (Netflix, YouTube…) are **never pre-selected**.

In all three cases, anything on the **NUNCA** (never) list in `perfiles.py` is excluded: Google Play, Cast, remote
service, assistant, tuner/HDMI, settings, the original home screen, keyboards, Bluetooth, updates, factory menus…

Update the catalog: `python herramientas/importar_catalogo.py <path to the cleanyourtv repo>`.

## Ask Claude

Optional. Needs an Anthropic API key in the `ANTHROPIC_API_KEY` environment variable (or `ant auth login`)
**before** opening the app; the app doesn't store it. It sends your question, the TV's state and the action log,
**with MAC addresses, tokens and passwords removed** first. Model `claude-opus-5-5`; costs cents per question.

## Command line

```
.venv/Scripts/python -m tvcasa pruebas 192.168.1.50     # Windows (Mac: .venv/bin/python)
.venv/Scripts/python -m tvcasa info 192.168.1.50
.venv/Scripts/python -m unittest discover -s pruebas    # automated tests (simulated TV)
```

## When you're done

Turn off **network debugging** on each TV: while it's on, any device on your network can control the TV.

## Roadmap

- Samsung Tizen / LG webOS: another "connector" with the same design (profile, suggestions, checks, backup).
- Video wallpaper on the home screen (today video works in the Photos screensaver).
- Schedule photos by date (Christmas, birthdays) from the app.
- English interface.

## Disclaimer

Use at your own risk. It disables system apps (never uninstalls them) and always saves a backup first, but every
manufacturer is different. "Ask Claude" uses your own Anthropic API key. ADB isn't bundled: the installer downloads
it from Google. MIT license (see `LICENSE`).

## Support the project

TV House is free and open source. If it saved you time or made your TV feel new again, you can support it on
[GitHub Sponsors](https://github.com/sponsors/tutvcasa23-star). It helps buy TVs from other brands for testing and
add Samsung and LG support.
