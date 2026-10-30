param(
    [Parameter(Mandatory = $true)][string]$Database,
    [Parameter(Mandatory = $true)][string]$Backup,
    [Parameter(Mandatory = $true)][switch]$ConfirmReplace,
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [Parameter(Mandatory = $true)][string]$User
)
$ErrorActionPreference = "Stop"
if (-not $ConfirmReplace) { throw "Restaurar reemplaza objetos existentes. Repite con -ConfirmReplace tras verificar el destino." }
if (-not $User) { throw "Defina POSTGRES_USER o indique -User." }
if (-not (Test-Path -LiteralPath $Backup -PathType Leaf)) { throw "No existe el respaldo: $Backup" }
& pg_restore --clean --if-exists --no-owner --host=$HostName --port=$Port --username=$User --dbname=$Database $Backup
if ($LASTEXITCODE -ne 0) { throw "pg_restore fallo ($LASTEXITCODE)." }
Write-Output "Restauracion completada: $Database"
