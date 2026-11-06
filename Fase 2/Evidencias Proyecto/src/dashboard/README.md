# Dashboard de CascoVision

Interfaz web del prevencionista (tareas 4.18 y parte de 4.19), en React con Vite.
Habla solo con la API REST, bajo `/api` (ver `docs/API.md`).

| Sección | Qué muestra | Requisito |
| --- | --- | --- |
| Monitoreo | Indicadores del día, incidentes abiertos, balizas y cámaras. Se actualiza cada 5 s sin recargar | RF-13 |
| Detalle del incidente | Evidencia difuminada, datos del aviso y revisión (estado y comentario) | RF-14, RF-19 |
| Historial | Incidentes por período, cámara, zona, infracción, estado y baliza, con resumen y paginación | RF-15 (consulta) |
| Usuarios (solo admin) | Lista de usuarios y alta de prevencionistas y supervisores | RF-16 |

El supervisor solo consulta; el prevencionista y el administrador revisan
incidentes. El token de sesión se guarda en `sessionStorage` y se borra al
cerrar la pestaña.

## Con Docker

Lo levanta `compose.yaml` como servicio `dashboard` en `http://127.0.0.1:8080`
(ver `docs/DESPLIEGUE_DOCKER.md`).

## En desarrollo

Con la API corriendo en `127.0.0.1:8000`:

```bash
cd "Fase 2/Evidencias Proyecto/src/dashboard"
npm install
npm run dev        # http://127.0.0.1:5173, /api va a la API local
```

## Pendiente

- Gestión de cámaras, zonas y balizas desde la interfaz (tarea 4.19): hoy se cargan en la base.
- Exportar reportes a PDF y Excel (tarea 4.12).
- Vista en vivo de la cámara: el agente guarda el último cuadro, pero hay que confirmar que difumina a todas las personas antes de mostrarlo.
