# Experimentos de detección

Scripts de experimentación que se usaron durante el desarrollo. **No forman
parte del pipeline de CascoVision** y no se ejecutan en ninguna prueba ni en
ninguna demostración.

El pipeline real es:

| Componente | Ruta |
| --- | --- |
| Motor de detección | `../testing y modelamiento/motor_cascovision.py` |
| Agente Edge (con API) | `../testing y modelamiento/monitoreo_api.py` |
| Monitoreo local | `../testing y modelamiento/monitoreo_v2.py` |
| Entrenamiento | `../testing y modelamiento/entrenamiento.py` |
| Evaluación | `../testing y modelamiento/evaluacion.py` |

## Estado de estos scripts

Los cuatro quedaron desactualizados y **no funcionan con el detector actual**:

| Script | Problema |
| --- | --- |
| `test-1.py` | Rutas absolutas al modelo. Escrito para el modelo de 11 clases |
| `test-2.py` | Usa `cv2.CascadeClassifier`, que OpenCV 5.0 eliminó. El detector de ojos se reemplazó por YuNet en el motor |
| `test-3.py` | Igual que `test-2.py`: cascada Haar de ojos |
| `deteccion sin modelo.py` | Rutas absolutas. Ejercita la inferencia cruda del modelo |

Los motivos por los que se conservan:

1. Documentan cómo se fue descartando la cascada Haar de ojos: el
   `README.md` del modelo registra que YuNet acierta en el 100 % de las personas
   frente al 17 % de la cascada frontal, con 16,9 ms frente a 58,9 ms.
2. Sirven de referencia si hay que volver a un experimento de esos.

Si se retoman, la migración al estado actual es:

- Sustituir `cv2.CascadeClassifier` por `cv2.FaceDetectorYN`, que es lo que
  hace `motor_cascovision.py`.
- Resolver el modelo con `motor_cascovision.RUTA_MODELO_EPP` en vez de una
  ruta absoluta.
- Actualizar el mapa de clases: el detector actual tiene 5 clases
  (`helmet`, `no_helmet`, `no_vest`, `Person`, `vest`).
