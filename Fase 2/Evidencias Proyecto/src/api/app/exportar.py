"""Reporte de incidentes en PDF y Excel (RF-15, CU-08, tarea 4.12).

Recibe lo mismo que entrega `GET /reports` (con toda la selección, no una
página) y lo pasa a archivo. Las horas van en hora de Santiago, que es la de
la faena; la API sigue respondiendo en UTC.
"""

from datetime import datetime
from io import BytesIO
from typing import Any

import xlsxwriter
from fpdf import FPDF

from .almacen import ZONA_LOCAL

INFRACCION = {"missing_helmet": "Sin casco", "missing_reflective_vest": "Sin chaleco"}
ESTADO = {"open": "Abierto", "reviewed": "Revisado", "closed": "Cerrado",
          "false_positive": "Falso positivo"}
BALIZA = {"alerted": "Alertada", "failed": "Falló", "skipped_offline": "Fuera de línea"}
COLUMNAS = ["Inicio", "Fin", "Duración (min)", "Cámara", "Zona", "Infracciones",
            "Confianza (%)", "Baliza", "Latencia (ms)", "Revisión", "Persona"]


def _local(valor: datetime | None) -> datetime | None:
    return valor.astimezone(ZONA_LOCAL).replace(tzinfo=None) if valor else None


def _texto_fecha(valor: datetime | None) -> str:
    return f"{_local(valor):%d-%m-%Y %H:%M:%S}" if valor else "—"


def _filtros(filtros: dict, nombres: dict) -> list[tuple[str, str]]:
    """Los filtros aplicados, en palabras, para que el archivo diga qué contiene."""
    traducir = {
        "desde": ("Desde", _texto_fecha),
        "hasta": ("Hasta", _texto_fecha),
        "camera_id": ("Cámara", lambda v: nombres["camaras"].get(v, v)),
        "zone_id": ("Zona", lambda v: nombres["zonas"].get(v, v)),
        "violation_type": ("Infracción", lambda v: INFRACCION.get(v, v)),
        "status": ("Revisión", lambda v: ESTADO.get(v, v)),
        "beacon_status": ("Baliza", lambda v: BALIZA.get(v, v)),
    }
    return [(etiqueta, formato(filtros[campo]))
            for campo, (etiqueta, formato) in traducir.items() if campo in filtros]


def _fila(inc: dict, nombres: dict) -> list[Any]:
    tipos = inc.get("violation_types") or [inc["violation_type"]]
    alerta = inc["beacon_alert"]
    duracion = inc.get("duration_s")
    return [
        _local(inc.get("started_at") or inc["detected_at"]),
        _local(inc.get("ended_at")),
        round(duracion / 60, 1) if duracion is not None else None,
        nombres["camaras"].get(inc["camera_id"], inc["camera_id"]),
        nombres["zonas"].get(inc["zone_id"], inc["zone_id"]),
        ", ".join(INFRACCION.get(t, t) for t in tipos),
        round(inc["confidence"] * 100, 1),
        BALIZA.get(alerta["status"], alerta["status"]),
        alerta.get("latency_ms"),
        ESTADO.get(inc["status"], inc["status"]),
        inc.get("person_track_id"),
    ]


def _totales(resumen: dict) -> list[tuple[str, Any]]:
    media = resumen.get("duracion_media_s")
    return [
        ("Incidentes", resumen["total"]),
        ("Avisos en curso", resumen["en_curso"]),
        ("Avisos terminados", resumen["terminados"]),
        ("Duración media (min)", round(media / 60, 1) if media is not None else "—"),
        *[(f"Revisión: {ESTADO.get(k, k)}", v) for k, v in resumen["por_estado"].items()],
        *[(f"Baliza: {BALIZA.get(k, k)}", v) for k, v in resumen["balizas"].items()],
    ]


def _grupos(resumen: dict) -> list[tuple[str, list[str], list[list[Any]]]]:
    return [
        ("Por zona", ["Zona", "Incidentes", "Alertas abiertas"],
         [[g["zone_name"], g["total_incidentes"], g["alertas_activas"]] for g in resumen["por_zona"]]),
        ("Por turno", ["Turno", "Incidentes", "Alertas abiertas"],
         [[g["shift_name"], g["total_incidentes"], g["alertas_activas"]] for g in resumen["por_turno"]]),
        ("Por hora", ["Fecha", "Hora", "Incidentes", "Alertas abiertas"],
         [[g["fecha_local"], f"{int(g['hora_local']):02d}:00", g["total_incidentes"],
           g["alertas_activas"]] for g in resumen["por_hora"]]),
    ]


def _aviso_truncado(reporte: dict) -> str | None:
    mostradas, total = len(reporte["incidentes"]), reporte["total"]
    if mostradas < total:
        return f"Se incluyen {mostradas} de {total} incidentes: acote el periodo para verlos todos."
    return None


# ---------- Excel ----------

def a_excel(reporte: dict, nombres: dict, filtros: dict) -> bytes:
    salida = BytesIO()
    # Un nombre de zona como "=1+1" queda como texto: no se ejecuta como fórmula.
    libro = xlsxwriter.Workbook(salida, {"in_memory": True, "strings_to_formulas": False,
                                         "strings_to_urls": False})
    negrita = libro.add_format({"bold": True})
    titulo = libro.add_format({"bold": True, "font_size": 14})
    fecha = libro.add_format({"num_format": "dd-mm-yyyy hh:mm:ss"})

    hoja = libro.add_worksheet("Resumen")
    hoja.set_column(0, 0, 28)
    hoja.set_column(1, 3, 16)
    hoja.write(0, 0, "Reporte de incidentes CascoVision", titulo)
    hoja.write(1, 0, f"Generado el {datetime.now(ZONA_LOCAL):%d-%m-%Y %H:%M} (hora de Santiago)")
    fila = 3
    for etiqueta, valor in _filtros(filtros, nombres) or [("Filtros", "Sin filtros")]:
        hoja.write(fila, 0, etiqueta, negrita)
        hoja.write(fila, 1, valor)
        fila += 1
    aviso = _aviso_truncado(reporte)
    if aviso:
        hoja.write(fila, 0, aviso, negrita)
        fila += 1
    fila += 1
    for etiqueta, valor in _totales(reporte["resumen"]):
        hoja.write(fila, 0, etiqueta)
        hoja.write(fila, 1, valor)
        fila += 1
    for nombre, cabecera, filas in _grupos(reporte["resumen"]):
        fila += 1
        hoja.write(fila, 0, nombre, negrita)
        fila += 1
        hoja.write_row(fila, 0, cabecera, negrita)
        for datos in filas:
            fila += 1
            hoja.write_row(fila, 0, datos)
        fila += 1

    hoja = libro.add_worksheet("Incidentes")
    hoja.write_row(0, 0, COLUMNAS, negrita)
    hoja.set_column(0, 1, 20)
    hoja.set_column(2, 2, 14)
    hoja.set_column(3, 5, 24)
    hoja.set_column(6, 10, 14)
    for i, inc in enumerate(reporte["incidentes"], start=1):
        for j, valor in enumerate(_fila(inc, nombres)):
            if isinstance(valor, datetime):
                hoja.write_datetime(i, j, valor, fecha)
            elif valor is not None:
                hoja.write(i, j, valor)
    hoja.autofilter(0, 0, max(1, len(reporte["incidentes"])), len(COLUMNAS) - 1)
    hoja.freeze_panes(1, 0)
    libro.close()
    return salida.getvalue()


# ---------- PDF ----------

def _latin1(valor: Any) -> str:
    # Las fuentes base del PDF solo tienen Latin-1; un emoji o una flecha se ven como "?".
    texto = "—" if valor is None else valor if isinstance(valor, str) else str(valor)
    texto = texto.replace("—", "-")
    return texto.encode("latin-1", "replace").decode("latin-1")


def _celda(valor: Any) -> str:
    if isinstance(valor, datetime):
        return f"{valor:%d-%m-%Y %H:%M}"
    if isinstance(valor, float):
        return f"{valor:.1f}".replace(".", ",")
    return _latin1(valor)


def _tabla(pdf: FPDF, cabecera: list[str], filas: list[list[Any]], anchos=None, ancho=None) -> None:
    with pdf.table(width=ancho, col_widths=anchos, align="LEFT", text_align="LEFT",
                   line_height=5) as tabla:
        for datos in [cabecera, *filas]:
            fila = tabla.row()
            for valor in datos:
                fila.cell(_celda(valor))
    pdf.ln(4)


def a_pdf(reporte: dict, nombres: dict, filtros: dict) -> bytes:
    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, _latin1("Reporte de incidentes CascoVision"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 5, _latin1(f"Generado el {datetime.now(ZONA_LOCAL):%d-%m-%Y %H:%M} (hora de Santiago)"),
             new_x="LMARGIN", new_y="NEXT")
    textos = [f"{e}: {v}" for e, v in _filtros(filtros, nombres)] or ["Sin filtros"]
    pdf.multi_cell(0, 5, _latin1("Filtros: " + " | ".join(textos)),
                   new_x="LMARGIN", new_y="NEXT")
    aviso = _aviso_truncado(reporte)
    if aviso:
        pdf.set_font("Helvetica", "B", 9)
        pdf.multi_cell(0, 5, _latin1(aviso), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)
    pdf.ln(3)

    pdf.set_font("Helvetica", size=8)
    _tabla(pdf, ["Indicador", "Valor"], [list(t) for t in _totales(reporte["resumen"])], (60, 30), 90)
    for nombre, cabecera, filas in _grupos(reporte["resumen"]):
        if filas:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, _latin1(nombre), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=8)
            anchos = (60, 30, 30, 30)[:len(cabecera)]
            _tabla(pdf, cabecera, filas, anchos, sum(anchos))

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _latin1(f"Incidentes ({len(reporte['incidentes'])})"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=7)
    if reporte["incidentes"]:
        _tabla(pdf, COLUMNAS, [_fila(i, nombres) for i in reporte["incidentes"]],
               (26, 26, 16, 32, 30, 34, 16, 22, 16, 22, 13))
    else:
        pdf.cell(0, 5, _latin1("No hay incidentes con estos filtros."), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
