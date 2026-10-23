# Mockups del dashboard

Actualizan el mockup de la Fase 1 para el diseño (D2, tarea 3.4).

## Cambios respecto del mockup de la Fase 1

- **Dos vistas nuevas:** inicio de sesión (RF-17) y configuración de cámaras, zonas y balizas (RF-04, RF-09 y RF-10). La de configuración incluye el dibujo del polígono de la zona, el estado de cada baliza según el *heartbeat* y el botón «Probar alerta».
- **Baliza zonal en vez de dispositivo vibratorio.** La trazabilidad de la alerta decía «buzzer + motor háptico»; ahora dice «sonido + pantalla» y sigue el orden del diseño: detección, baliza, registro y notificación.
- **Gestión del incidente (RF-14):** selector con los cuatro estados (abierto, revisado, cerrado y falso positivo) y un comentario obligatorio al cerrar.
- **Sin identificar a las personas:** el indicador «Trabajadores detectados hoy» pasa a «Personas analizadas hoy (sin identificar)», y el número de seguimiento se rotula como anónimo.

## Vistas

| Vista | Archivo | Usuario | Requisitos |
| --- | --- | --- | --- |
| Inicio de sesión | `Mockup_login.png` | Todos | RF-17, RNF-06 |
| Detección en vivo | `Mockup_live.png` | Prevencionista, supervisor | RF-02, RF-03, RF-06 |
| Dashboard de monitoreo | `Mockup_dashboard.png` | Prevencionista, supervisor | RF-13, RNF-04 |
| Detalle de incidente | `Mockup_incident.png` | Prevencionista | RF-05, RF-14, RF-19 |
| Reportes | `Mockup_reports.png` | Prevencionista, supervisor | RF-15 |
| Cámaras, zonas y balizas | `Mockup_config.png` | Administrador | RF-04, RF-09, RF-10, RF-18 |

El mockup interactivo es `CascoVision_Mockup_v2.html`. Se abre en el navegador; cada vista también se abre directamente con `#login`, `#dashboard`, `#incident`, `#reports` o `#config` al final de la dirección.

## Pendiente

- Decidir si el dashboard se construye con una librería de componentes o con CSS propio (tarea 4.18).
- Falta la vista de **gestión de usuarios** (CU-11), de baja prioridad para la demo.
