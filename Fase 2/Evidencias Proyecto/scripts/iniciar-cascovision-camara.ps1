$ErrorActionPreference = "Stop"

$evidenceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $evidenceRoot "..\..")).Path
$envFile = Join-Path $evidenceRoot ".env"
$dockerConfig = Join-Path $evidenceRoot "docker\edge\config.json"
$agent = Join-Path $evidenceRoot "src\edge\agente.py"
$model = Join-Path $evidenceRoot "models\cascovision_yolo26s.pt"
$tempConfig = Join-Path ([System.IO.Path]::GetTempPath()) "cascovision-edge-host-$PID.json"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "No existe $envFile. Completa primero el archivo .env."
}

function Get-EnvValue([string]$Name, [string]$Default = "") {
    $line = Get-Content -LiteralPath $envFile |
        Where-Object { $_.Trim().StartsWith("$Name=") } |
        Select-Object -Last 1
    if (-not $line) { return $Default }

    $value = ([string]$line).Trim().Substring($Name.Length + 1).Trim()
    if ($value.Length -ge 2 -and
        (($value.StartsWith('"') -and $value.EndsWith('"')) -or
         ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    return $value
}

$oldEdgeToken = [Environment]::GetEnvironmentVariable("EDGE_API_TOKEN", "Process")
$oldBeaconToken = [Environment]::GetEnvironmentVariable("BALIZA_TOKEN", "Process")
$oldYoloAutoInstall = [Environment]::GetEnvironmentVariable("YOLO_AUTOINSTALL", "Process")
Push-Location $evidenceRoot
try {
    $env:EDGE_API_TOKEN = Get-EnvValue "EDGE_API_TOKEN"
    $env:BALIZA_TOKEN = Get-EnvValue "BALIZA_TOKEN"
    $apiPort = Get-EnvValue "API_PUERTO" "8000"
    $dashboardPort = Get-EnvValue "DASHBOARD_PUERTO" "8080"

    if ([string]::IsNullOrWhiteSpace($env:EDGE_API_TOKEN)) {
        throw "Falta EDGE_API_TOKEN en .env."
    }
    if ([string]::IsNullOrWhiteSpace($env:BALIZA_TOKEN)) {
        throw "Falta BALIZA_TOKEN en .env."
    }
    if ($apiPort -notmatch '^\d{1,5}$' -or $dashboardPort -notmatch '^\d{1,5}$') {
        throw "API_PUERTO o DASHBOARD_PUERTO no es un puerto válido en .env."
    }
    if (-not (Test-Path -LiteralPath $model)) {
        throw "No se encontró el modelo local: $model"
    }
    $env:YOLO_AUTOINSTALL = "false"

    Write-Host "Deteniendo el Edge de Docker y el video de presentación..."
    & docker compose stop edge
    if ($LASTEXITCODE -ne 0) { throw "No se pudo detener el servicio Edge de Docker." }
    & docker compose --profile dev stop rtsp-sim
    if ($LASTEXITCODE -ne 0) { throw "No se pudo detener el simulador RTSP." }

    Write-Host "Iniciando base de datos, API y dashboard..."
    New-Item -ItemType Directory -Force -Path (Join-Path $evidenceRoot "incidents") | Out-Null
    & docker compose -f compose.yaml -f compose.camera.yaml up -d --build --wait db api dashboard
    if ($LASTEXITCODE -ne 0) { throw "Docker no pudo iniciar db, api y dashboard." }

    $config = Get-Content -LiteralPath $dockerConfig -Raw | ConvertFrom-Json
    $config.fuente = "1"
    $config.api = "http://127.0.0.1:$apiPort"
    $config.carpeta_datos = Join-Path $env:LOCALAPPDATA "CascoVision\edge-data"
    $json = ConvertTo-Json -InputObject $config -Depth 10
    [System.IO.File]::WriteAllText($tempConfig, $json, [System.Text.UTF8Encoding]::new($false))

    $dashboardUrl = "http://127.0.0.1:$dashboardPort"
    Write-Host "Abriendo dashboard: $dashboardUrl"
    Start-Process $dashboardUrl
    Write-Host "Abriendo la cámara 1. Presiona q en la ventana de video para salir."
    & uv run --project $repoRoot --group yolo python $agent --config $tempConfig --fuente 1 --modelo $model
    if ($LASTEXITCODE -ne 0) { throw "El agente de cámara terminó con error ($LASTEXITCODE)." }
}
finally {
    if (Test-Path -LiteralPath $tempConfig) {
        Remove-Item -LiteralPath $tempConfig -Force
    }
    [Environment]::SetEnvironmentVariable("EDGE_API_TOKEN", $oldEdgeToken, "Process")
    [Environment]::SetEnvironmentVariable("BALIZA_TOKEN", $oldBeaconToken, "Process")
    [Environment]::SetEnvironmentVariable("YOLO_AUTOINSTALL", $oldYoloAutoInstall, "Process")
    Pop-Location
}
