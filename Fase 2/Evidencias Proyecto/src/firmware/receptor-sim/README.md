# Receptor simulado de baliza

Implementa `POST /alert` y `GET /health` del [protocolo de baliza](../../../docs/PROTOCOLO_BALIZA.md), sin hardware ni dependencias externas.

Desde `Fase 2/Evidencias Proyecto`, en PowerShell:

```powershell
$env:BALIZA_TOKEN = Read-Host "Token de al menos 32 caracteres"
$env:SIM_ZONE_ID = "zona-norte"
python src/firmware/receptor-sim/server.py
```

El servidor escucha en `127.0.0.1:8081`. Configura `SIM_HOST=0.0.0.0` si el agente Edge se ejecuta en otra máquina o contenedor. Usa el mismo `BALIZA_TOKEN` en el agente y apunta su URL de baliza a `http://127.0.0.1:8081`.

Variables opcionales: `SIM_BEACON_ID`, `SIM_ZONE_NAME`, `SIM_BATTERY_PCT` (87 por defecto), `SIM_LOG_PATH` (por defecto `alerts.jsonl` junto al servidor), `SIM_DELAY_MS` (0) y `SIM_FAIL_RATE` (0, fracción entre 0 y 1). Cada orden aceptada se agrega como una línea JSON al archivo de registro.

`GET /health` es público. `POST /alert` requiere `Authorization: Bearer <BALIZA_TOKEN>`, limita el cuerpo a 1 KB, valida el contrato, rechaza otra zona con 409 y responde reintentos con el mismo `alert_id` como duplicados. El simulador no activa sonido ni pantalla físicos.
