import { useState } from "react";
import { api, consulta } from "./api.js";
import { BALIZA, ESTADO, INFRACCION, duracion, fecha, infracciones } from "./formato.js";
import usarDatos from "./usarDatos.js";

const POR_PAGINA = 20;
const VACIO = { desde: "", hasta: "", camera_id: "", zone_id: "", violation_type: "",
                status: "", beacon_status: "" };

// El día de los <input type="date"> se toma en hora local de la faena.
const dia = (valor, fin) => (valor ? new Date(`${valor}T${fin ? "23:59:59" : "00:00:00"}`).toISOString() : "");

export default function Historial({ abrir, version }) {
  const [filtros, setFiltros] = useState(VACIO);
  const [pagina, setPagina] = useState(1);
  const [descarga, setDescarga] = useState({ formato: "", error: "" });
  const catalogo = usarDatos(() => Promise.all([api("/cameras"), api("/zones")]), []);
  const { datos, error } = usarDatos(
    () => api("/reports" + consulta({
      ...filtros, desde: dia(filtros.desde, false), hasta: dia(filtros.hasta, true),
      page: pagina, limit: POR_PAGINA,
    })),
    [filtros, pagina, version],
  );

  const [camaras, zonas] = catalogo.datos ?? [[], []];
  const nombreZona = Object.fromEntries(zonas.map((z) => [z.id, z.name]));
  const cambiar = (campo) => (e) => {
    setFiltros({ ...filtros, [campo]: e.target.value });
    setPagina(1);
  };
  const paginas = datos ? Math.max(1, Math.ceil(datos.total / POR_PAGINA)) : 1;

  // El reporte en archivo usa los mismos filtros que la tabla (RF-15).
  async function descargar(formato) {
    setDescarga({ formato, error: "" });
    try {
      const blob = await api("/reports/export" + consulta({
        ...filtros, desde: dia(filtros.desde, false), hasta: dia(filtros.hasta, true), formato,
      }), { binario: true });
      const url = URL.createObjectURL(blob);
      const enlace = Object.assign(document.createElement("a"), {
        href: url, download: `reporte_cascovision.${formato}`,
      });
      enlace.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDescarga({ formato: "", error: "" });
    } catch (e) {
      setDescarga({ formato: "", error: e.message });
    }
  }

  return (
    <div className="rejilla">
      <section className="panel ancho">
        <h2>Filtros</h2>
        <div className="filtros">
          <label>Desde<input type="date" value={filtros.desde} onChange={cambiar("desde")} /></label>
          <label>Hasta<input type="date" value={filtros.hasta} onChange={cambiar("hasta")} /></label>
          <Selector etiqueta="Cámara" valor={filtros.camera_id} alCambiar={cambiar("camera_id")}
                    opciones={camaras.map((c) => [c.id, c.name])} />
          <Selector etiqueta="Zona" valor={filtros.zone_id} alCambiar={cambiar("zone_id")}
                    opciones={zonas.map((z) => [z.id, z.name])} />
          <Selector etiqueta="Infracción" valor={filtros.violation_type} alCambiar={cambiar("violation_type")}
                    opciones={Object.entries(INFRACCION)} />
          <Selector etiqueta="Estado" valor={filtros.status} alCambiar={cambiar("status")}
                    opciones={Object.entries(ESTADO)} />
          <Selector etiqueta="Baliza" valor={filtros.beacon_status} alCambiar={cambiar("beacon_status")}
                    opciones={Object.entries(BALIZA)} />
          <button className="secundario" onClick={() => { setFiltros(VACIO); setPagina(1); }}>
            Limpiar
          </button>
        </div>
        <div className="acciones exportar">
          <button onClick={() => descargar("pdf")} disabled={Boolean(descarga.formato)}>
            {descarga.formato === "pdf" ? "Generando…" : "Descargar PDF"}
          </button>
          <button onClick={() => descargar("xlsx")} disabled={Boolean(descarga.formato)}>
            {descarga.formato === "xlsx" ? "Generando…" : "Descargar Excel"}
          </button>
          {descarga.error && <p className="error" role="alert">{descarga.error}</p>}
        </div>
      </section>

      {error && <p className="error ancho" role="alert">{error}</p>}
      {datos && (
        <>
          <section className="kpis" aria-label="Resumen del período">
            <div className="kpi"><span>Incidentes</span><b>{datos.resumen.total}</b></div>
            <div className="kpi"><span>En curso</span><b>{datos.resumen.en_curso}</b></div>
            <div className="kpi"><span>Duración media</span><b>{duracion(datos.resumen.duracion_media_s)}</b></div>
            <div className="kpi"><span>Cerrados</span><b>{datos.resumen.por_estado.closed}</b></div>
            <div className="kpi"><span>Falsos positivos</span><b>{datos.resumen.por_estado.false_positive}</b></div>
          </section>

          <section className="panel ancho">
            <h2>Incidentes ({datos.total})</h2>
            {datos.incidentes.length === 0 ? (
              <p className="suave">No hay incidentes con esos filtros.</p>
            ) : (
              <div className="tabla">
                <table>
                  <thead>
                    <tr>
                      <th>Inicio</th><th>Fin</th><th>Duración</th><th>Zona</th><th>Infracción</th>
                      <th>Baliza</th><th>Estado</th><th><span className="oculto">Acción</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.incidentes.map((i) => (
                      <tr key={i.id}>
                        <td>{fecha(i.started_at ?? i.detected_at)}</td>
                        <td>{i.ended_at ? fecha(i.ended_at) : <span className="chip activo">En curso</span>}</td>
                        <td>{duracion(i.duration_s)}</td>
                        <td>{nombreZona[i.zone_id] ?? i.zone_id}</td>
                        <td>{infracciones(i)}</td>
                        <td className={i.beacon_alert.status}>{BALIZA[i.beacon_alert.status]}</td>
                        <td>{ESTADO[i.status]}</td>
                        <td><button className="secundario" onClick={() => abrir(i)}>Ver</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="paginacion">
              <button className="secundario" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>
                Anterior
              </button>
              <span>Página {pagina} de {paginas}</span>
              <button className="secundario" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>
                Siguiente
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Selector({ etiqueta, valor, alCambiar, opciones }) {
  return (
    <label>
      {etiqueta}
      <select value={valor} onChange={alCambiar}>
        <option value="">Todas</option>
        {opciones.map(([id, nombre]) => <option key={id} value={id}>{nombre}</option>)}
      </select>
    </label>
  );
}
