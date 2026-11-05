import { api, consulta } from "./api.js";
import { BALIZA, ESTADO, fecha, infracciones } from "./formato.js";
import usarDatos from "./usarDatos.js";

const CADA_MS = 5000;

function inicioDelDia() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

async function cargar() {
  const [hoy, abiertos, balizas, camaras, zonas] = await Promise.all([
    api("/reports" + consulta({ desde: inicioDelDia(), limit: 1 })),
    api("/incidents" + consulta({ status: "open", limit: 50 })),
    api("/beacons"),
    api("/cameras"),
    api("/zones"),
  ]);
  return { hoy: hoy.resumen, abiertos, balizas, camaras, zonas };
}

export default function Monitoreo({ abrir, version }) {
  const { datos, error, actualizado } = usarDatos(cargar, [version], CADA_MS);

  if (!datos) return <p className="suave">{error ?? "Cargando monitoreo…"}</p>;
  const { hoy, abiertos, balizas, camaras, zonas } = datos;
  const nombreZona = Object.fromEntries(zonas.map((z) => [z.id, z.name]));
  const enCurso = abiertos.filter((i) => !i.ended_at);

  return (
    <div className="rejilla">
      <p className="estado-red" aria-live="polite">
        {error ? <span className="error">Sin conexión: {error}</span>
               : `Actualizado ${actualizado?.toLocaleTimeString("es-CL")} · cada 5 s`}
      </p>

      <section className="kpis" aria-label="Resumen del día">
        <Kpi titulo="Infracciones en curso" valor={enCurso.length} alerta={enCurso.length > 0} />
        <Kpi titulo="Abiertos sin revisar" valor={abiertos.length} />
        <Kpi titulo="Incidentes de hoy" valor={hoy.total} />
        <Kpi titulo="Balizas en línea" valor={`${balizas.filter((b) => b.online).length}/${balizas.length}`} />
        <Kpi titulo="Alertas fallidas hoy" valor={hoy.balizas.failed} alerta={hoy.balizas.failed > 0} />
      </section>

      <section className="panel ancho">
        <h2>Incidentes abiertos</h2>
        {abiertos.length === 0 ? (
          <p className="suave">No hay incidentes abiertos.</p>
        ) : (
          <div className="tabla">
            <table>
              <thead>
                <tr>
                  <th>Inicio</th><th>Zona</th><th>Infracción</th><th>Aviso</th>
                  <th>Baliza</th><th>Estado</th><th><span className="oculto">Acción</span></th>
                </tr>
              </thead>
              <tbody>
                {abiertos.map((i) => (
                  <tr key={i.id}>
                    <td>{fecha(i.started_at ?? i.detected_at)}</td>
                    <td>{nombreZona[i.zone_id] ?? i.zone_id}</td>
                    <td>{infracciones(i)}</td>
                    <td>
                      {i.ended_at ? "Terminado"
                        : <span className="chip activo">En curso</span>}
                    </td>
                    <td className={i.beacon_alert.status}>{BALIZA[i.beacon_alert.status]}</td>
                    <td>{ESTADO[i.status]}</td>
                    <td><button className="secundario" onClick={() => abrir(i)}>Ver</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>Balizas zonales</h2>
        <ul className="lista">
          {balizas.map((b) => (
            <li key={b.id}>
              <span className={b.online ? "punto ok" : "punto mal"} aria-hidden="true" />
              <b>{b.name}</b> · {nombreZona[b.zone_id] ?? "sin zona"}
              <span className="suave">
                {b.online ? "En línea" : "Fuera de línea"}
                {b.battery_pct !== null && ` · batería ${b.battery_pct} %`}
                {` · visto ${fecha(b.last_seen_at)}`}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2>Cámaras</h2>
        <ul className="lista">
          {camaras.map((c) => (
            <li key={c.id}>
              <span className={c.active ? "punto ok" : "punto apagado"} aria-hidden="true" />
              <b>{c.name}</b> · {c.location ?? c.id}
              <span className="suave">
                {c.active ? "Activa" : "Desactivada"}
                {` · zonas: ${zonas.filter((z) => z.camera_id === c.id).map((z) => z.name).join(", ") || "ninguna"}`}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Kpi({ titulo, valor, alerta = false }) {
  return (
    <div className={alerta ? "kpi alerta" : "kpi"}>
      <span>{titulo}</span>
      <b>{valor}</b>
    </div>
  );
}
