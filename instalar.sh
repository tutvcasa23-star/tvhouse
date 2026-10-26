#!/usr/bin/env bash
# Instala TV Casa en Mac (o Linux): entorno de Python propio, librerías y ADB de Google. Luego corre las pruebas.
# Uso: bash instalar.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "Falta Python 3.10+ (en Mac: https://www.python.org/downloads/)" >&2; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python debe ser 3.10 o más nuevo" >&2; exit 1; }

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

if [ ! -x herramientas/platform-tools/adb ]; then
  case "$(uname -s)" in Darwin) SO=darwin ;; Linux) SO=linux ;; *) echo "Sistema no soportado" >&2; exit 1 ;; esac
  echo "Descargando ADB (Android SDK Platform-Tools) de dl.google.com…"
  TMP=$(mktemp -d)
  curl -fsSL "https://dl.google.com/android/repository/platform-tools-latest-$SO.zip" -o "$TMP/pt.zip"
  mkdir -p herramientas && unzip -q -o "$TMP/pt.zip" -d herramientas && rm -rf "$TMP"
fi

.venv/bin/python -m unittest discover -s pruebas -q

cat > abrir-tvcasa.command <<'EOF'
#!/usr/bin/env bash
cd "$(dirname "$0")" && .venv/bin/python -m tvcasa
EOF
chmod +x abrir-tvcasa.command
echo "Listo. Para abrir: doble clic en $(pwd)/abrir-tvcasa.command"
