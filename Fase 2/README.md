# Fase 2 · Desarrollo del proyecto

En esta fase se especifica, diseña, construye y prueba CascoVision con una metodología tradicional en cascada. Los documentos de ingeniería (D1 a D3) tienen una copia en PDF junto a su `.docx`.

## Evidencias grupales

### Guías e informes APT

| Código | Documento | Archivo |
| --- | --- | --- |
| 2.4 | Guía del avance, completada en el formulario oficial | [2.4_GuiaEstudiante_Fase 2_DesarrolloProyecto APT.docx](<Evidencias Grupales/2.4_GuiaEstudiante_Fase 2_DesarrolloProyecto APT.docx>) |
| 2.4 | Informe de avance desarrollado: abstract bilingüe, monitoreo del plan y ajustes | [2.4_GuiaEstudiante_Fase2_DesarrolloProyectoAPT_CascoVision.docx](<Evidencias Grupales/2.4_GuiaEstudiante_Fase2_DesarrolloProyectoAPT_CascoVision.docx>) |
| 2.6 | Informe final del proyecto APT. La sección 7 responde las preguntas de innovación (qué problema resuelve, qué la hace diferente y qué valor agrega). Faltan las reflexiones individuales de la sección 6 de Joaquín, Benjamín y Fernando | [.docx](<Evidencias Grupales/2.6_GuiaEstudiante_Fase 2_Informe Final Proyecto APT (Español).docx>) · [.pdf](<Evidencias Grupales/2.6_GuiaEstudiante_Fase 2_Informe Final Proyecto APT (Español).pdf>) |
| — | Presentación del avance | [Presentacion_Fase2_CascoVision.pptx](<Evidencias Grupales/Presentacion_Fase2_CascoVision.pptx>) |
| — | Planilla de evaluación del avance | [PLANILLA DE EVALUACION AVANCE FASE 2.xlsx](<Evidencias Grupales/PLANILLA DE EVALUACION AVANCE FASE 2.xlsx>) |

### Documentos de ingeniería

| Código | Documento | Versión | Archivo |
| --- | --- | --- | --- |
| — | Carta Gantt del plan tradicional | — | [.xlsx](<Evidencias Grupales/Gantt_CascoVision_Tradicional.xlsx>) · [.png](<Evidencias Grupales/Gantt_CascoVision_Tradicional.png>) |
| D1 | Especificación de requisitos (SRS) | 1.1 | [.docx](<Evidencias Grupales/D1_SRS_CascoVision.docx>) · [.pdf](<Evidencias Grupales/D1_SRS_CascoVision.pdf>) |
| D2 | Documento de diseño consolidado | 1.1 | [.docx](<Evidencias Grupales/D2_Diseno_CascoVision.docx>) · [.pdf](<Evidencias Grupales/D2_Diseno_CascoVision.pdf>) |
| D2 | Capítulo de arquitectura y despliegue, con el detalle que el D2 consolidado resume | 1.0 | [.docx](<Evidencias Grupales/D2_Arquitectura_Despliegue_CascoVision.docx>) · [.pdf](<Evidencias Grupales/D2_Arquitectura_Despliegue_CascoVision.pdf>) |
| D3 | Plan de pruebas | 0.9 | [.docx](<Evidencias Grupales/D3_Plan_de_Pruebas_CascoVision.docx>) · [.pdf](<Evidencias Grupales/D3_Plan_de_Pruebas_CascoVision.pdf>) |
| D3 | Informe de resultados de pruebas | borrador 0.1 | [.md](<Evidencias Grupales/D3_Informe_Resultados_Pruebas_CascoVision.md>) |
| D4 | Manual técnico y de despliegue | en preparación | — |

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

## Evidencias del proyecto (código)

[`Evidencias Proyecto/`](<Evidencias Proyecto/>) contiene el sistema completo. Para levantarlo y correr las pruebas, sigue el [README principal](../README.md).

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
