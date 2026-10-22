"""Evaluacion del detector de EPP de CascoVision.

Mide dos cosas sobre un split del dataset:

1. **Metricas por clase** (mAP@0,5, mAP@0,5:0,95, precision y recall), que son
   las que usa el criterio de aceptacion RNF-05 del SRS.

2. **Metricas de negocio**: para cada persona real, si el sistema acierta al
   decir si lleva casco y si lleva chaleco. Es la metrica que importa para el
   producto: el SRS no busca detectar cajas, sino avisar cuando alguien no
   lleva EPP.

El ground truth de las reglas de negocio sale directo de las clases negativas
del dataset: `no_helmet` significa que esa persona NO lleva casco, `no_vest`
que NO lleva chaleco.

Los dos detectores que se comparan tienen vocabularios distintos, asi que cada
uno declara un "perfil" que traduce sus ids de clase a los roles semanticos
(casco, sin casco, chaleco, sin chaleco, persona). La evaluacion aplica a cada
modelo SU PROPIA regla de decision, sobre el mismo ground truth: es una
comparacion de comportamiento, no de ids de clase.

Uso:

    # Detector de 5 clases (el nuevo)
    uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/evaluacion.py" \
        --model "Fase 2/Evidencias Proyecto/models/cascovision_yolo26s.pt" \
        --perfil 5clases

    # Detector de 11 clases (el anterior, linea base)
    uv run python "Fase 2/Evidencias Proyecto/Yolo/modelamiento/evaluacion.py" \
        --model "Fase 2/Evidencias Proyecto/models/cascovision_yolo26s.pt" \
        --perfil 11clases
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image
from ultralytics import YOLO

RAIZ = next((p for p in Path(__file__).resolve().parents if (p / "Fase 2").is_dir()),
            Path(__file__).resolve().parents[4])

RUTA_DATOS = RAIZ / "Fase 2" / "Evidencias Proyecto" / "Yolo" / "dataset" / "construccion-implementos.yaml"

IOU_MIN = 0.30
SOLAPAMIENTO_EPP = 0.35

# Umbrales de zona del motor de 11 clases, para reproducir su reinterpretacion
# de la clase 'none' (caja generica de "sin implemento").
CORTE_CABEZA = 0.33
TAMANO_CHALECO = 0.25


class Perfil:
    """Traduce los ids de clase de un detector a los roles semanticos."""

    def __init__(self, nombre, persona, helmet, no_helmet, vest, no_vest,
                 none=None, zona_none=False):
        self.nombre = nombre
        self.persona = persona
        self.helmet = helmet
        self.no_helmet = no_helmet
        self.vest = vest
        self.no_vest = no_vest
        self.none = none
        self.zona_none = zona_none

    def roles(self, clase, caja, persona_caja):
        """Devuelve los roles semanticos que aporta una caja.

        Para el perfil de 11 clases, la clase 'none' se reinterpreta por zona
        del cuerpo (cabeza o torso), igual que hace `motor_cascovision.py`.
        """
        roles = []
        if clase == self.helmet:
            roles.append("helmet")
        elif clase == self.no_helmet:
            roles.append("no_helmet")
        elif clase == self.vest:
            roles.append("vest")
        elif clase == self.no_vest:
            roles.append("no_vest")
        elif self.none is not None and clase == self.none:
            if self.zona_none:
                rol = self._zona_none(caja, persona_caja)
                if rol:
                    roles.append(rol)
        return roles

    @staticmethod
    def _zona_none(caja, persona_caja):
        """Reinterpreta 'none' por zona: cabeza o torso (motor de 11 clases)."""
        px1, py1, px2, py2 = persona_caja
        alto = max(1.0, py2 - py1)
        rel_yc = ((caja[1] + caja[3]) / 2.0 - py1) / alto
        rel_h = (caja[3] - caja[1]) / alto
        if rel_yc >= CORTE_CABEZA:
            return "no_vest"
        if rel_h < TAMANO_CHALECO:
            return "no_helmet"
        return None


PERFILES = {
    # Detector de 5 clases: cada clase negativa declara ya su zona.
    "5clases": Perfil("5clases", persona=3, helmet=0, no_helmet=1, vest=4, no_vest=2),
    # Detector de 11 clases: 'none' es una caja generica que se reinterpreta.
    "11clases": Perfil("11clases", persona=6, helmet=0, no_helmet=7, vest=2,
                       no_vest=None, none=5, zona_none=True),
}

# Ground truth del dataset (5 clases, esquema fijo).
GT_PERSONA = 3
GT_HELMET, GT_NO_HELMET, GT_NO_VEST, GT_VEST = 0, 1, 2, 4


def cargar_gt(ruta_labels: Path, ancho: int, alto: int):
    """Personas reales y señales de EPP de un archivo de etiquetas.

    Las etiquetas de YOLO vienen normalizadas (0-1); se convertiran a pixeles
    para poder compararlas con las detecciones del modelo, que ya estan en
    pixeles.

    Returns:
        personas: lista de cajas [x1, y1, x2, y2] en pixeles de la clase Person.
        senales:  dict clase -> lista de cajas en pixeles, para el resto de clases.
    """
    personas, senales = [], defaultdict(list)
    for linea in ruta_labels.read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if len(partes) < 5:
            continue
        clase = int(partes[0])
        x, y, w, h = map(float, partes[1:5])
        caja = [(x - w / 2) * ancho, (y - h / 2) * alto,
                (x + w / 2) * ancho, (y + h / 2) * alto]
        if clase == GT_PERSONA:
            personas.append(caja)
        else:
            senales[clase].append(caja)
    return personas, dict(senales)


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def solapamiento(caja, contenedor) -> float:
    """Fraccion del area de 'caja' contenida en 'contenedor'."""
    ix = max(0.0, min(caja[2], contenedor[2]) - max(caja[0], contenedor[0]))
    iy = max(0.0, min(caja[3], contenedor[3]) - max(caja[1], contenedor[1]))
    inter = ix * iy
    area = max(1e-9, (caja[2] - caja[0]) * (caja[3] - caja[1]))
    return inter / area


def emparejar(detectadas, reales, iou_min=IOU_MIN):
    """Empareja detecciones con reales por IoU.

    Devuelve, para cada deteccion, el indice de la persona real con la que se
    empareja, o -1 si no hay coincidencia suficiente.

    La asignacion es global (no codiciosa): se ordenan todos los pares posibles
    por IoU descendente y se van fijando. Un emparejamiento codicioso puede
    dejar sin emparejar una deteccion correcta si una deteccion peor se lleva
    antes a la misma persona real.
    """
    pares = [-1] * len(detectadas)
    candidatos = []
    for i, det in enumerate(detectadas):
        for j, real in enumerate(reales):
            valor = iou(det, real)
            if valor >= iou_min:
                candidatos.append((valor, i, j))
    # Mayor IoU primero; a igual IoU se desempata por indice para que el
    # resultado sea determinista.
    candidatos.sort(key=lambda t: (-t[0], t[1], t[2]))
    usados_det, usados_real = set(), set()
    for valor, i, j in candidatos:
        if i in usados_det or j in usados_real:
            continue
        usados_det.add(i)
        usados_real.add(j)
        pares[i] = j
    return pares


def regla(roles, zona) -> str | None:
    """Decide 'si' / 'no' / None a partir de los roles semanticos de una zona.

    zona: 'casco' o 'chaleco'.
    """
    positivo = "helmet" if zona == "casco" else "vest"
    negativo = "no_helmet" if zona == "casco" else "no_vest"
    hay_pos = positivo in roles
    hay_neg = negativo in roles
    if hay_pos and not hay_neg:
        return "si"
    if hay_neg and not hay_pos:
        return "no"
    if hay_pos and hay_neg:
        return "si"  # el detector se contradice: se privilegia el positivo
    return None


def roles_en_zona(cajas, persona_caja, perfil, zona) -> set:
    """Roles semanticos de las cajas de EPP que caen dentro de la persona."""
    encontrados = set()
    for caja, clase in cajas:
        if solapamiento(caja, persona_caja) < SOLAPAMIENTO_EPP:
            continue
        for rol in perfil.roles(clase, caja, persona_caja):
            if (zona == "casco" and rol in ("helmet", "no_helmet")) or \
               (zona == "chaleco" and rol in ("vest", "no_vest")):
                encontrados.add(rol)
    return encontrados


def main() -> None:
    analizador = argparse.ArgumentParser(description="Evaluacion del detector de EPP")
    analizador.add_argument("--model", required=True, help="Ruta del checkpoint a evaluar")
    analizador.add_argument("--perfil", default="5clases", choices=sorted(PERFILES),
                            help="Vocabulario del detector")
    analizador.add_argument("--split", default="test", choices=["train", "val", "test"])
    analizador.add_argument("--conf", type=float, default=0.25)
    analizador.add_argument("--device", default="0")
    analizador.add_argument("--json", default=None, help="Guardar el informe en este JSON")
    args = analizador.parse_args()

    perfil = PERFILES[args.perfil]
    modelo = YOLO(args.model)
    print(f"Modelo: {args.model}")
    print(f"Perfil: {perfil.nombre}")
    print(f"Clases del modelo: {modelo.names}")

    carpeta = RUTA_DATOS.parent / args.split / "images"
    if not carpeta.is_dir():
        sys.exit(f"No existe el split '{args.split}': {carpeta}")

    # --- Metricas por clase (solo comparables entre detectores con el mismo
    #     vocabulario; se reportan igual para dejar constancia) ---
    try:
        metricas = modelo.val(data=str(RUTA_DATOS), split=args.split,
                              device=args.device, verbose=False)
        hay_metricas = True
    except Exception as exc:  # el vocabulario puede no encajar con el dataset
        print(f"  (metricas por clase no disponibles: {exc})")
        hay_metricas = False

    # --- Metricas de negocio ---
    confusion = {"casco": defaultdict(lambda: defaultdict(int)),
                 "chaleco": defaultdict(lambda: defaultdict(int))}
    n_personas_reales = 0
    n_sin_dato_casco = n_sin_dato_chaleco = 0

    archivos = sorted(carpeta.glob("*.jpg"))
    for indice, imagen in enumerate(archivos, 1):
        # OJO: los nombres llevan el sufijo de augmentation de Roboflow
        # ('.rf.<hash>'), asi que with_suffix() no sirve: hay que reemplazar solo
        # la extension final.
        etiqueta = imagen.parent.parent / "labels" / (imagen.stem + ".txt")
        if not etiqueta.is_file():
            continue
        # Las detecciones vienen en pixeles: el GT debe estar en la misma escala.
        with Image.open(imagen) as img_pil:
            ancho, alto = img_pil.size
        personas_gt, senales_gt = cargar_gt(etiqueta, ancho, alto)
        n_personas_reales += len(personas_gt)
        if not personas_gt:
            continue

        # Cajas de EPP del ground truth, en el formato (caja, clase).
        # 'cargar_gt' devuelve las cajas como [x1, y1, x2, y2] y la clave del
        # diccionario es el id de clase.
        cajas_gt = [(caja, clase) for clase, cajas in senales_gt.items()
                    for caja in cajas]

        resultado = modelo.predict(source=str(imagen), conf=args.conf,
                                   device=args.device, verbose=False)[0]
        # Cada elemento es (caja_xyxy, clase).
        cajas = []
        for indice_caja, caja in enumerate(resultado.boxes.xyxy.tolist()):
            clases = int(resultado.boxes.cls[indice_caja])
            cajas.append((caja, clases))

        detectadas = [c for c in cajas if c[1] == perfil.persona]
        epp = [(caja, clase) for caja, clase in cajas if clase != perfil.persona]

        # 'emparejar' trabaja con cajas sueltas, no con tuplas (caja, clase).
        pares = emparejar([caja for caja, _ in detectadas], personas_gt)
        emparejados = {i for i in pares if i >= 0}

        for indice_det, indice_real in enumerate(pares):
            if indice_real < 0:
                continue
            persona_det, persona_real = detectadas[indice_det][0], personas_gt[indice_real]

            for zona in ("casco", "chaleco"):
                roles_gt = roles_en_zona(cajas_gt, persona_real, _PERFIL_GT, zona)
                real = regla(roles_gt, zona)
                if real is None:
                    if zona == "casco":
                        n_sin_dato_casco += 1
                    else:
                        n_sin_dato_chaleco += 1
                    continue
                pred = regla(roles_en_zona(epp, persona_det, perfil, zona), zona)
                if pred is not None:
                    confusion[zona][real][pred] += 1

        # Personas reales que el detector no vio: no dice nada, lo que es un
        # falso negativo en ambas reglas.
        for indice_real, persona_real in enumerate(personas_gt):
            if indice_real in emparejados:
                continue
            for zona in ("casco", "chaleco"):
                roles_gt = roles_en_zona(cajas_gt, persona_real, _PERFIL_GT, zona)
                real = regla(roles_gt, zona)
                if real is None:
                    continue
                # Predecir 'si' (cumplimiento) sin haber visto a la persona es el
                # error mas grave: no avisa a quien va sin EPP.
                confusion[zona][real]["si"] += 1

        if indice % 50 == 0:
            print(f"  [{indice}/{len(archivos)}] personas reales: {n_personas_reales}")

    print()
    print("=" * 68)
    print("METRICAS POR CLASE")
    print("=" * 68)
    por_clase = {}
    if hay_metricas:
        print(f"  {'mAP@0,5':12} = {metricas.box.map50:.4f}")
        print(f"  {'mAP@0,5:0,95':12} = {metricas.box.map:.4f}")
        print(f"  {'precision':12} = {metricas.box.mp:.4f}")
        print(f"  {'recall':12} = {metricas.box.mr:.4f}")
        print()
        for i, nombre in metricas.names.items():
            try:
                p, r, ap50, ap = metricas.box.class_result(i)
            except IndexError:
                continue
            print(f"  clase {i} ({nombre}): mAP@0,5={ap50:.4f}  "
                  f"mAP@0,5:0,95={ap:.4f}  P={p:.4f}  R={r:.4f}")
            por_clase[nombre] = {"mAP50": float(ap50), "mAP50-95": float(ap),
                                 "precision": float(p), "recall": float(r)}
    else:
        print("  (no disponible: el vocabulario del modelo no encaja con el dataset)")

    print()
    print("=" * 68)
    print("METRICAS DE NEGOCIO (reglas de decision)")
    print("=" * 68)
    resumen = {}
    for zona in ("casco", "chaleco"):
        tabla = confusion[zona]
        aciertos = tabla["si"]["si"] + tabla["no"]["no"]
        fp = tabla["si"]["no"]
        fn = tabla["no"]["si"]
        total = aciertos + fp + fn
        precision = aciertos / (aciertos + fp) if (aciertos + fp) else 0.0
        recall = aciertos / (aciertos + fn) if (aciertos + fn) else 0.0
        exactitud = aciertos / total if total else 0.0
        print(f"\n  ¿Lleva {zona}?")
        print(f"    aciertos={aciertos}  falsos_positivos={fp}  falsos_negativos={fn}")
        print(f"    precision={precision:.4f}  recall={recall:.4f}  exactitud={exactitud:.4f}")
        print(f"    (personas con ground truth evaluable: {total})")
        resumen[zona] = {"aciertos": aciertos, "falsos_positivos": fp,
                         "falsos_negativos": fn, "precision": precision,
                         "recall": recall, "exactitud": exactitud,
                         "evaluadas": total}

    informe = {
        "modelo": args.model,
        "perfil": perfil.nombre,
        "split": args.split,
        "conf": args.conf,
        "metricas_clase": por_clase,
        "metricas_negocio": resumen,
        "personas_reales": n_personas_reales,
        "personas_sin_ground_truth": {"casco": n_sin_dato_casco,
                                      "chaleco": n_sin_dato_chaleco},
    }
    print()
    print("=" * 68)
    print("RESUMEN JSON")
    print("=" * 68)
    print(json.dumps(informe, indent=2, ensure_ascii=False))

    if args.json:
        Path(args.json).write_text(json.dumps(informe, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
        print(f"\nInforme guardado en {args.json}")


# Perfil del ground truth: el dataset siempre usa el esquema de 5 clases.
_PERFIL_GT = PERFILES["5clases"]


if __name__ == "__main__":
    main()
