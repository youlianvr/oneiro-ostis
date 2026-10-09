# Builds installer/payload: an embeddable Python with the pinned dependencies,
# the Oneiro sources, the ontology, the compose file and the launcher.
# The output folder must not exist; remove an old payload yourself, with the
# workspace trash tool, before rebuilding. Network access is needed for the
# Python archive and pip.
$ErrorActionPreference = 'Stop'

$Python = '3.14.3'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$Out = Join-Path $PSScriptRoot 'payload'
if (Test-Path $Out) { throw "payload already exists at $Out; move it to trash first" }

New-Item -ItemType Directory -Path $Out | Out-Null
$Runtime = Join-Path $Out 'python'
$Archive = Join-Path $env:TEMP "python-$Python-embed-amd64.zip"

Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$Python/python-$Python-embed-amd64.zip" -OutFile $Archive
Expand-Archive -Path $Archive -DestinationPath $Runtime

# The embeddable build ignores site-packages until its ._pth file says so.
# Its own app folder goes on the path too, so `python -m oneiro` finds the sources.
$pth = Get-ChildItem -Path $Runtime -Filter 'python*._pth' | Select-Object -First 1
$lines = Get-Content $pth.FullName | ForEach-Object { if ($_ -match '^#\s*import site') { 'import site' } else { $_ } }
$lines += '..\app\python'
Set-Content -Path $pth.FullName -Value $lines -Encoding ascii

# -s: ignore the developer's user site-packages, so nothing outside the payload
# is read or replaced while it is built.
$getPip = Join-Path $env:TEMP 'get-pip.py'
Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getPip
& (Join-Path $Runtime 'python.exe') -s $getPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip failed with exit $LASTEXITCODE" }

# --target with --ignore-installed puts every pinned package inside the payload,
# even where another copy exists elsewhere.
& (Join-Path $Runtime 'python.exe') -s -m pip install --no-warn-script-location --ignore-installed `
    --target (Join-Path $Runtime 'Lib\site-packages') `
    'fastapi==0.141.1' 'uvicorn==0.41.0' 'py-sc-client==0.4.0'
if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit $LASTEXITCODE" }

$App = Join-Path $Out 'app'
New-Item -ItemType Directory -Path (Join-Path $App 'python') | Out-Null
Copy-Item -Path (Join-Path $Root 'python\oneiro') -Destination (Join-Path $App 'python\oneiro') -Recurse `
    -Exclude '__pycache__'
Get-ChildItem -Path (Join-Path $App 'python\oneiro') -Recurse -Directory -Filter '__pycache__' |
    ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
New-Item -ItemType Directory -Path (Join-Path $App 'knowledge-base') | Out-Null
Copy-Item -Path (Join-Path $Root 'knowledge-base\ontology') -Destination (Join-Path $App 'knowledge-base\ontology') -Recurse
Copy-Item -Path (Join-Path $Root 'docker-compose.yml') -Destination $App

Copy-Item -Path (Join-Path $PSScriptRoot 'start-oneiro.cmd') -Destination $Out

Write-Output "payload ready: $Out"
