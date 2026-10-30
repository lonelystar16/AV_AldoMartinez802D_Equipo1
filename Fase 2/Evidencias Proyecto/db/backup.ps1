param(
    [Parameter(Mandatory = $true)][string]$Database,
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [Parameter(Mandatory = $true)][string]$User,
    [string]$Output = (Join-Path $env:TEMP "cascovision-backup.dump")
)
$ErrorActionPreference = "Stop"
if (-not $User) { throw "Defina POSTGRES_USER o indique -User." }
if (Test-Path -LiteralPath $Output) { throw "El respaldo ya existe: $Output" }
& pg_dump --format=custom --host=$HostName --port=$Port --username=$User --dbname=$Database --file=$Output
if ($LASTEXITCODE -ne 0) { Remove-Item -LiteralPath $Output -ErrorAction SilentlyContinue; throw "pg_dump fallo ($LASTEXITCODE)." }
Write-Output "Respaldo creado: $Output"
