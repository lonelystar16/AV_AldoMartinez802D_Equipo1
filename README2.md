Si se necesita cambiar el modelo yolo26s A uno yolo26N, aqui se encuentran la forma correcta para entrenar el modelo
tiempo estimado de entrenamiento del modelo: 14-18horas

Al momento de abrir el programa y querer entrenarlo nuevamente, se debe de cambiar la ruta en las siguientes caracteristicas:
construccion-implementos.yalm se debe cambiar a la ruta de la carpeta en el PATH como se muestra a continuacion para garantizar donde se encuentran los datos para entrenar el modelo
path: C:/Users/jikonyx/Documents/vscode/AV_AldoMartinez802D_Equipo1/Fase 2/Evidencias Proyecto/Yolo/dataset

y en entrenamiento.py se debe de cambiar la información dentro de los siguientes elementos:
model = YOLO("yolo26s.pt") por el modelo a usar y
model.train(data=r"Ruta del construccion-implementos", epochs=100, imgsz=640)
