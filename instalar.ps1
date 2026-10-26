# Instala TV House en Windows: entorno de Python propio, librerías y ADB de Google. Luego corre las pruebas.
# Uso: powershell -ExecutionPolicy Bypass -File instalar.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw 'Falta Python 3.10 o más nuevo: instálalo desde python.org (marcar "Add to PATH").' }
& $py -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Python debe ser 3.10 o más nuevo.' }

if (-not (Test-Path .venv)) { & $py -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

if (-not (Test-Path herramientas\platform-tools\adb.exe)) {
    Write-Host 'Descargando ADB (Android SDK Platform-Tools) de dl.google.com…'
    $zip = Join-Path $env:TEMP 'platform-tools-windows.zip'
    Invoke-WebRequest -UseBasicParsing https://dl.google.com/android/repository/platform-tools-latest-windows.zip -OutFile $zip
    Expand-Archive $zip herramientas -Force
    Remove-Item $zip
    $firma = Get-AuthenticodeSignature herramientas\platform-tools\adb.exe
    if ($firma.Status -ne 'Valid' -or $firma.SignerCertificate.Subject -notmatch 'Google LLC') { throw 'La firma de adb.exe no es de Google: se aborta.' }
}

& .\.venv\Scripts\python.exe -m unittest discover -s pruebas -q
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas automáticas: revisar antes de usar.' }

# Accesos directos "TV House" (ventana propia, sin consola ni navegador): escritorio, menú Inicio y esta carpeta
$shell = New-Object -ComObject WScript.Shell
$destinos = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'TV House.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'TV House.lnk'),
    (Join-Path $PSScriptRoot 'TV House.lnk')
)
foreach ($d in $destinos) {
    $l = $shell.CreateShortcut($d)
    $l.TargetPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
    $l.Arguments = '-m tvcasa'
    $l.WorkingDirectory = $PSScriptRoot
    $l.IconLocation = Join-Path $PSScriptRoot 'tvcasa\static\tvcasa.ico'
    $l.Description = 'Configura los TV de la casa'
    $l.Save()
}
Remove-Item abrir-tvcasa.cmd -ErrorAction SilentlyContinue
Write-Host 'Listo. Abre "TV House" desde el escritorio o el menú Inicio.'
