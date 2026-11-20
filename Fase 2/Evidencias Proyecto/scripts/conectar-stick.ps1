[CmdletBinding()]
param(
    [string]$Port,
    [int]$ApiPort = 8000,
    [switch]$ActualizarClave
)

try {
$ErrorActionPreference = "Stop"

function Invoke-StickCommand([hashtable]$Command, [int]$TimeoutMs = 5000) {
    $serial.WriteLine(($Command | ConvertTo-Json -Compress))
    $vence = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    while ([DateTime]::UtcNow -lt $vence) {
        try {
            $linea = $serial.ReadLine()
        }
        catch [System.TimeoutException] {
            continue
        }
        if ($linea.StartsWith("CVCFG:")) {
            return $linea.Substring(6) | ConvertFrom-Json
        }
    }
    throw "El Stick no respondió por USB. Cierra el Monitor Serial y vuelve a ejecutar el script."
}

$nombresPuerto = [System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object
if (-not $nombresPuerto) {
    throw "No encontré un puerto serial. Conecta el Stick por USB y revisa el cable/driver."
}
if (-not $Port) {
    if ($nombresPuerto.Count -eq 1) {
        $Port = $nombresPuerto[0]
    }
    else {
        Write-Host "Puertos seriales detectados:"
        for ($i = 0; $i -lt $nombresPuerto.Count; $i++) {
            Write-Host "  $($i + 1). $($nombresPuerto[$i])"
        }
        $seleccion = [int](Read-Host "Selecciona el puerto del Stick")
        if ($seleccion -lt 1 -or $seleccion -gt $nombresPuerto.Count) {
            throw "Selección de puerto inválida."
        }
        $Port = $nombresPuerto[$seleccion - 1]
    }
}
if ($Port -notin $nombresPuerto) {
    throw "El puerto $Port no está disponible. Puertos detectados: $($nombresPuerto -join ', ')"
}

$netsh = (& netsh wlan show interfaces 2>$null | Out-String)
$ssidMatch = [regex]::Match($netsh, '(?m)^\s*SSID\s*:\s*(.+?)\s*$')
if (-not $ssidMatch.Success) {
    throw "La PC no aparece conectada a una red Wi-Fi. Conéctala al Wi-Fi y reintenta."
}
$ssid = $ssidMatch.Groups[1].Value.Trim()
$interfazMatch = [regex]::Match(
    $netsh, '(?m)^\s*(?:Name|Interface Name|Nombre(?: de(?: la)? interfaz)?)\s*:\s*(.+?)\s*$'
)
if (-not $interfazMatch.Success) {
    throw "No pude identificar el nombre de la interfaz Wi-Fi."
}
$interfaz = $interfazMatch.Groups[1].Value.Trim()
$direccion = Get-NetIPAddress -InterfaceAlias $interfaz -AddressFamily IPv4 |
    Where-Object {
        $_.AddressState -eq "Preferred" -and
        $_.IPAddress -notmatch '^(127\.|169\.254\.)'
    } |
    Select-Object -First 1
if (-not $direccion) {
    throw "No encontré una IPv4 utilizable en la interfaz '$interfaz'."
}
$apiUrl = "http://$($direccion.IPAddress):$ApiPort"

$serial = [System.IO.Ports.SerialPort]::new(
    $Port, 115200, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One
)
$serial.Encoding = [System.Text.Encoding]::UTF8
$serial.NewLine = "`n"
$serial.ReadTimeout = 250
$serial.WriteTimeout = 3000
$serial.DtrEnable = $false
$serial.RtsEnable = $false

try {
    $serial.Open()
    Start-Sleep -Milliseconds 800
    $serial.DiscardInBuffer()

    $estado = Invoke-StickCommand @{ cmd = "status" } 15000
    if (-not $estado.ok -or -not $estado.configured) {
        throw "El Stick no tiene configuración inicial. Cárgala primero con configurador_nvs."
    }

    $clave = $null
    if ($ActualizarClave -or $estado.ssid -ne $ssid) {
        $segura = Read-Host "Contraseña Wi-Fi para '$ssid' (no se mostrará)" -AsSecureString
        if ($segura.Length -lt 8 -or $segura.Length -gt 63) {
            $segura.Dispose()
            throw "La contraseña debe tener entre 8 y 63 caracteres."
        }
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
        try {
            $clave = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
            $segura.Dispose()
        }
    }

    $guardado = Invoke-StickCommand @{
        cmd = "configure"
        ssid = $ssid
        password = $clave
        api_url = $apiUrl
    }
    $clave = $null
    if (-not $guardado.ok -or $guardado.status -ne "saved") {
        throw "El Stick rechazó la configuración: $($guardado.error)"
    }

    Write-Host "Configuración guardada; esperando conexión del Stick y API..."
    $vence = [DateTime]::UtcNow.AddSeconds(40)
    do {
        Start-Sleep -Seconds 2
        $estado = Invoke-StickCommand @{ cmd = "status" } 3000
        if ($estado.wifi_connected -and $estado.api_ok) {
            Write-Host "Listo: Stick conectado a '$ssid'; API accesible en $apiUrl."
            return
        }
    } while ([DateTime]::UtcNow -lt $vence)

    throw "Los datos se guardaron, pero no se confirmó acceso a la API. Revisa que escuche en 0.0.0.0:$ApiPort y que el firewall permita TCP $ApiPort."
}
finally {
    if ($serial.IsOpen) { $serial.Close() }
    $clave = $null
}
}
catch {
    Write-Host "`nError: $($_.Exception.Message)" -ForegroundColor Red
    throw
}
finally {
    Write-Host "`nPresiona cualquier tecla para cerrar..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
