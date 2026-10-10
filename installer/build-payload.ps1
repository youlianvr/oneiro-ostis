# Builds installer/payload: an embeddable Python with the pinned dependencies,
# the Oneiro sources, the ontology, the graph image and the launcher.
# The output folder must not exist; remove an old payload yourself, with the
# workspace trash tool, before rebuilding. Network access is needed for the
# Python archive and pip. The graph image must already exist locally (docker).
$ErrorActionPreference = 'Stop'

$Python = '3.14.3'
$GraphImage = 'oneiro-rewrite-machine:checkpoint'
$GraphTag = 'oneiro-graph:0.2.0'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$Out = Join-Path $PSScriptRoot 'payload'
if (Test-Path $Out) { throw "payload already exists at $Out; move it to trash first" }

docker image inspect $GraphImage *> $null
if ($LASTEXITCODE -ne 0) { throw "graph image $GraphImage is not present; build or load it first" }

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

# Only the files the graph container reads. kb.bin, logs and the vendor menu
# are the owner's runtime state and never ship.
$KbApp = Join-Path $App 'knowledge-base'
New-Item -ItemType Directory -Path $KbApp | Out-Null
Copy-Item -Path (Join-Path $Root 'knowledge-base\ontology') -Destination (Join-Path $KbApp 'ontology') -Recurse
Copy-Item -Path (Join-Path $Root 'knowledge-base\repo.path') -Destination $KbApp
Copy-Item -Path (Join-Path $Root 'knowledge-base\oneiro-ostis.ini') -Destination $KbApp

# The image is saved under the name the launcher runs. The tag is only an alias.
$GraphDir = Join-Path $Out 'graph'
New-Item -ItemType Directory -Path $GraphDir | Out-Null
docker tag $GraphImage $GraphTag
if ($LASTEXITCODE -ne 0) { throw "docker tag failed with exit $LASTEXITCODE" }
docker save -o (Join-Path $GraphDir 'oneiro-graph-0.2.0.tar') $GraphTag
if ($LASTEXITCODE -ne 0) { throw "docker save failed with exit $LASTEXITCODE" }

# The MIT grant travels with every copy of the sources it covers.
Copy-Item -Path (Join-Path $Root 'LICENSE') -Destination $Out

Copy-Item -Path (Join-Path $PSScriptRoot 'start-oneiro.cmd') -Destination $Out
Copy-Item -Path (Join-Path $PSScriptRoot 'start-oneiro.ps1') -Destination $Out

Write-Output "payload ready: $Out"
