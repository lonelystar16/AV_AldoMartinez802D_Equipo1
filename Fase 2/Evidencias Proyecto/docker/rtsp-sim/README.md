# Video de la cámara simulada

`rtsp-sim` (perfil `dev`) repite `video_prueba.mp4` como si fuera una cámara RTSP.

`video_prueba.mp4` viene en el repositorio (62 KB; es una excepción al `.gitignore`, que
excluye `*.mp4`). Es la imagen de prueba `Yolo/modelamiento/testeo.jpg` en bucle durante
40 s, seguida de 25 s en gris sin persona, así que el perfil `dev` funciona apenas se clona
el repositorio.

Para probar con otro video, reemplaza este archivo por uno con el mismo nombre. Usa solo
videos públicos o de stock, nunca grabaciones reales de una faena.
