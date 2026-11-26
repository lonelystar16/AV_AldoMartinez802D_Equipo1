# Fase 2 · Desarrollo del proyecto

En esta fase se especifica, diseña, construye y prueba CascoVision con una metodología tradicional en cascada. Los documentos de ingeniería (D1 a D4) tienen una copia en PDF junto a su `.docx`.

## Evidencias grupales

### Guías e informes APT

| Código | Documento | Archivo |
| --- | --- | --- |
| 2.4 | Guía del avance, completada en el formulario oficial | [2.4_GuiaEstudiante_Fase 2_DesarrolloProyecto APT (Español).docx](<Evidencias Grupales/2.4_GuiaEstudiante_Fase 2_DesarrolloProyecto APT (Español).docx>) |
| 2.4 | Anexo de la guía 2.4: informe de avance desarrollado, con abstract bilingüe, monitoreo del plan y ajustes | [2.4_GuiaEstudiante_Fase2_DesarrolloProyectoAPT_CascoVision.docx](<Evidencias Grupales/2.4_GuiaEstudiante_Fase2_DesarrolloProyectoAPT_CascoVision.docx>) |
| 2.6 | Informe final del proyecto APT. La sección 7 responde las preguntas de innovación (qué problema resuelve, qué la hace diferente y qué valor agrega), y la sección 6 tiene la reflexión de los cuatro integrantes | [.docx](<Evidencias Grupales/2.6_GuiaEstudiante_Fase 2_Informe Final Proyecto APT (Español).docx>) · [.pdf](<Evidencias Grupales/2.6_GuiaEstudiante_Fase 2_Informe Final Proyecto APT (Español).pdf>) |
| — | Planilla de evaluación del avance | [PLANILLA DE EVALUACION AVANCE FASE 2.xlsx](<Evidencias Grupales/PLANILLA DE EVALUACION AVANCE FASE 2.xlsx>) |
| — | Planilla de evaluación final de la Fase 2 | [PLANILLA DE EVALUACION FINAL FASE 2.xlsx](<Evidencias Grupales/PLANILLA DE EVALUACION FINAL FASE 2.xlsx>) |

## Evidencias del proyecto

Siguiendo la planilla de evidencias, [`Evidencias Proyecto/`](<Evidencias Proyecto/>) reúne la presentación, la documentación y el sistema.

### Presentación

| Documento | Archivo |
| --- | --- |
| Presentación del avance de la Fase 2 | [Presentación Proyecto.pptx](<Evidencias Proyecto/Presentación Proyecto.pptx>) |

### Documentación (metodología en cascada)

Los documentos D1 a D4 son los que pide el anexo de metodología para el enfoque tradicional. Están en [`Evidencias Proyecto/Documentacion/`](<Evidencias Proyecto/Documentacion/>).

| Código | Documento | Versión | Archivo |
| --- | --- | --- | --- |
| — | Carta Gantt del plan tradicional | — | [.xlsx](<Evidencias Proyecto/Documentacion/Gantt_CascoVision_Tradicional.xlsx>) · [.png](<Evidencias Proyecto/Documentacion/Gantt_CascoVision_Tradicional.png>) |
| D1 | Especificación de requisitos (SRS): problema, objetivos, requisitos funcionales y no funcionales, casos de uso | 1.1 | [.docx](<Evidencias Proyecto/Documentacion/D1_SRS_CascoVision.docx>) · [.pdf](<Evidencias Proyecto/Documentacion/D1_SRS_CascoVision.pdf>) |
| D2 | Documento de diseño consolidado: arquitectura, modelo de datos, UML, diseño Docker y componentes. Es el documento de diseño oficial | 1.1 | [.docx](<Evidencias Proyecto/Documentacion/D2_Diseno_CascoVision.docx>) · [.pdf](<Evidencias Proyecto/Documentacion/D2_Diseno_CascoVision.pdf>) |
| D2 | Anexo del D2: capítulo de arquitectura y despliegue, con el detalle que el D2 consolidado resume | 1.0 | [.docx](<Evidencias Proyecto/Documentacion/D2_Arquitectura_Despliegue_CascoVision.docx>) · [.pdf](<Evidencias Proyecto/Documentacion/D2_Arquitectura_Despliegue_CascoVision.pdf>) |
| D3 | Plan de pruebas: casos unitarios, de integración, de rendimiento, de seguridad y de aceptación | 0.9 | [.docx](<Evidencias Proyecto/Documentacion/D3_Plan_de_Pruebas_CascoVision.docx>) · [.pdf](<Evidencias Proyecto/Documentacion/D3_Plan_de_Pruebas_CascoVision.pdf>) |
| D3 | Informe de resultados de pruebas: unitarias e integración (411 aprobadas), rendimiento (PR-01 a PR-05, con 4 cámaras), seguridad (PS-01 a PS-09) y defectos DEF-03 a DEF-06 | 1.0 | [.docx](<Evidencias Proyecto/Documentacion/D3_Informe_Resultados_Pruebas_CascoVision.docx>) · [.pdf](<Evidencias Proyecto/Documentacion/D3_Informe_Resultados_Pruebas_CascoVision.pdf>) · [.md](<Evidencias Proyecto/Documentacion/D3_Informe_Resultados_Pruebas_CascoVision.md>) · [evidencias](<Evidencias Proyecto/Documentacion/D3_evidencias_2026-11-25/>) |
| D4 | Manual técnico y de despliegue: instalación, Docker Compose, variables de entorno, ejecución, baliza StickS3 y problemas frecuentes | 1.0 | [.docx](<Evidencias Proyecto/Documentacion/D4_Manual_Tecnico_CascoVision.docx>) · [.pdf](<Evidencias Proyecto/Documentacion/D4_Manual_Tecnico_CascoVision.pdf>) |

### Sistema: aplicación y base de datos

El resto de [`Evidencias Proyecto/`](<Evidencias Proyecto/>) es el sistema completo. Para levantarlo y correr las pruebas, sigue el [README principal](../README.md).

| Carpeta | Contenido | Documentación |
| --- | --- | --- |
| `src/api/` | API REST en FastAPI: incidentes, autenticación JWT, usuarios, reportes y avisos por correo | [docs/API.md](<Evidencias Proyecto/docs/API.md>) |
| `src/edge/` | Agente Edge: lee las cámaras, detecta con YOLO26 y reporta los incidentes a la API | [src/edge/README.md](<Evidencias Proyecto/src/edge/README.md>) · [docs/MODELO.md](<Evidencias Proyecto/docs/MODELO.md>) |
| `src/dashboard/` | Dashboard web en React + Vite | [src/dashboard/README.md](<Evidencias Proyecto/src/dashboard/README.md>) |
| `src/firmware/` | Firmware de la baliza StickS3, configurador por USB y receptor simulado | [docs/PROTOCOLO_BALIZA.md](<Evidencias Proyecto/docs/PROTOCOLO_BALIZA.md>) |
| `Yolo/` | Entrenamiento, evaluación y exportación del modelo, con las métricas de `train-10` | [Yolo/README.md](<Evidencias Proyecto/Yolo/README.md>) |
| `models/` | Modelo entrenado (`.pt` y `.onnx`) y detector de rostros para el difuminado | [models/README.md](<Evidencias Proyecto/models/README.md>) |
| `db/` | Migraciones de PostgreSQL, datos de ejemplo, roles y respaldo | [db/README.md](<Evidencias Proyecto/db/README.md>) · [docs/MODELO_DATOS.md](<Evidencias Proyecto/docs/MODELO_DATOS.md>) |
| `docker/`, `compose*.yaml` | Imágenes y despliegue con Docker Compose | [docs/DESPLIEGUE_DOCKER.md](<Evidencias Proyecto/docs/DESPLIEGUE_DOCKER.md>) · [docs/DISENO_DOCKER.md](<Evidencias Proyecto/docs/DISENO_DOCKER.md>) |
| `scripts/` | Configuración del StickS3 por USB y arranque con la webcam en Windows | README principal |
| `tests/` | Pruebas automatizadas con pytest, que la CI corre en cada PR | README principal |
| `docs/` | Documentación técnica, diagramas UML y mockups. Incluye la [guía de uv](<Evidencias Proyecto/docs/GUIA_UV.md>) | — |

## Evidencias individuales

Cada integrante tiene su carpeta en [`Evidencias Individuales/`](<Evidencias Individuales/>):

| Código | Evidencia |
| --- | --- |
| 2.1 | Diario de reflexión de la Fase 2 |
| 2.2 | Autoevaluación del avance de la Fase 2 |

| Integrante | Carpeta |
| --- | --- |
| Joaquín Armijo | [Armijo_Joaquin](<Evidencias Individuales/Armijo_Joaquin/>) |
| Benjamín Cáceres | [Caceres_Benjamin](<Evidencias Individuales/Caceres_Benjamin/>) |
| Fernando Muñoz | [Muñoz_Fernando](<Evidencias Individuales/Muñoz_Fernando/>) |
| Iahn Vera | [Vera_Iahn](<Evidencias Individuales/Vera_Iahn/>) |
