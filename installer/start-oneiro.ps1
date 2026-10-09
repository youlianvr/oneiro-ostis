# Starts Oneiro: the memory graph (OSTIS, in Docker Desktop) first, then the web app.
# Closing the window stops the app and the graph; the graph saves on SIGINT.
# Data: the Docker volume oneiro-graph-kb-v1 (graph) and %USERPROFILE%\.oneiro (app).
# Uninstalling the program leaves both in place.
$ErrorActionPreference = 'Continue'

$Here = $PSScriptRoot
$Image = 'oneiro-graph:0.2.0'
$Container = 'oneiro-graph'
$Volume = 'oneiro-graph-kb-v1'
$GraphPort = if ($env:ONEIRO_PORT) { $env:ONEIRO_PORT } else { '8090' }
$WebPort = if ($env:ONEIRO_WEB_PORT) { $env:ONEIRO_WEB_PORT } else { '9899' }
$KbDir = Join-Path $Here 'app\knowledge-base'
$Url = "http://127.0.0.1:$WebPort/"

function Stop-Graph {
    Write-Host 'Stopping the memory graph (saving)...'
    docker stop --time 90 $Container *> $null
}

function Fail([string]$Message) {
    Write-Host ''
    Write-Host $Message -ForegroundColor Red
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Fail 'Docker Desktop is not running. Start it, wait until it reports that it is running, then start Oneiro again.'
}

docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Loading the memory image (first run only)...'
    docker load -i (Join-Path $Here 'graph\oneiro-graph-0.2.0.tar')
    if ($LASTEXITCODE -ne 0) { Fail 'Loading the memory image failed. See the messages above.' }
}

docker container inspect $Container *> $null
if ($LASTEXITCODE -ne 0) {
    docker run -d --name $Container --restart no --stop-signal SIGINT --stop-timeout 90 `
        -p "127.0.0.1:${GraphPort}:8090" `
        -v "${Volume}:/kb.bin" `
        -v "${KbDir}:/knowledge-base:ro" `
        -e REBUILD_KB=0 `
        -e KB_PATH=/knowledge-base/repo.path `
        -e CONFIG_PATH=/knowledge-base/oneiro-ostis.ini `
        -e BINARY_PATH=/example-app/install/sc-machine/bin `
        -e "EXTENSIONS_PATH=/example-app/build/Release/extensions;/example-app/install/sc-machine/lib/extensions" `
        -e SC_SERVER_HOST=0.0.0.0 `
        -e SC_SERVER_PARALLEL_ACTIONS=0 `
        --health-cmd '. /example-app/.venv/bin/activate && python3 /example-app/scripts/healthcheck.py' `
        --health-interval 5s --health-timeout 10s --health-retries 3 --health-start-period 120s `
        $Image run *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the memory container. Is port 8090 free?' }
} else {
    docker start $Container *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'Could not start the memory container.' }
}

Write-Host 'Starting the memory. The first start builds the graph from the ontology and can take several minutes.'
$deadline = (Get-Date).AddMinutes(20)
while ($true) {
    $health = docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $Container 2>$null
    if ($health -eq 'healthy') { break }
    if ($health -eq 'exited' -or $health -eq 'dead' -or $health -eq 'unhealthy') {
        Fail "The memory container stopped ($health). Details: docker logs $Container"
    }
    if ((Get-Date) -gt $deadline) {
        Stop-Graph
        Fail "The memory did not become ready in 20 minutes. Details: docker logs $Container"
    }
    Start-Sleep -Seconds 5
}
Write-Host 'Memory is ready.'

# The packaged runtime must not read packages installed for another Python on this machine,
# and must not write bytecode caches into the program folder (uninstall would leave them).
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$app = Start-Process -FilePath (Join-Path $Here 'python\python.exe') -ArgumentList '-m', 'oneiro', 'serve' `
    -WorkingDirectory $Here -NoNewWindow -PassThru

$ready = $false
for ($i = 0; $i -lt 60 -and -not $app.HasExited -and -not $ready; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "${Url}api/status" -UseBasicParsing -TimeoutSec 3
        $ready = ($response.StatusCode -eq 200)
    } catch {
        $ready = $false
    }
}
if ($ready) {
    Write-Host "Oneiro is running: $Url"
    Start-Process $Url
    Write-Host 'Close this window to stop Oneiro and save the memory.'
} else {
    Write-Host 'Oneiro did not answer on its web port. The messages above show why.' -ForegroundColor Yellow
}

try {
    $app.WaitForExit()
} finally {
    Stop-Graph
}
if (-not $ready) {
    Read-Host 'Press Enter to close'
}
exit $app.ExitCode
