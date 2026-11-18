import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { BALIZA, ESTADO, fecha, infracciones, puedeRevisar } from "./formato.js";

// Panel lateral con la evidencia y la revisión del incidente (RF-14, RF-19).
export default function Detalle({ incidente: i, usuario, cerrar, alCambiar }) {
  const panel = useRef(null);

  useEffect(() => {
    panel.current?.focus();
    const alTeclear = (e) => e.key === "Escape" && cerrar();
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, [cerrar]);

  return (
    <div className="fondo" onClick={cerrar}>
      <aside className="detalle" role="dialog" aria-modal="true" aria-labelledby="titulo-detalle"
             tabIndex={-1} ref={panel} onClick={(e) => e.stopPropagation()}>
        <div className="cabecera">
          <h2 id="titulo-detalle">{infracciones(i)}</h2>
          <button className="secundario" onClick={cerrar} aria-label="Cerrar detalle">✕</button>
        </div>
        <Evidencia id={i.id} />
        <dl>
          <dt>Cámara · zona</dt><dd>{i.camera_id} · {i.zone_id}</dd>
          <dt>Inicio</dt><dd>{fecha(i.started_at ?? i.detected_at)}</dd>
          <dt>Fin</dt><dd>{i.ended_at ? fecha(i.ended_at) : "En curso"}</dd>
          <dt>Avisos repetidos</dt><dd>{i.ping_count}</dd>
          <dt>Confianza</dt><dd>{Math.round(i.confidence * 100)} %</dd>
          <dt>Baliza</dt>
          <dd>
            {BALIZA[i.beacon_alert.status]}
            {i.beacon_alert.latency_ms !== null && ` en ${i.beacon_alert.latency_ms} ms`}
          </dd>
          <dt>Persona (seguimiento)</dt><dd>{i.person_track_id ?? "—"}</dd>
          <dt>Rostro difuminado</dt><dd>{i.face_blurred ? "Sí" : "No informado"}</dd>
          <dt>Estado</dt><dd>{ESTADO[i.status]}</dd>
        </dl>
        {puedeRevisar(usuario) ? (
          // La key reinicia el formulario cuando cambia el estado guardado.
          <Revision key={i.status} incidente={i} alCambiar={alCambiar} />
        ) : (
          <p className="suave">Tu rol (supervisor) solo puede consultar.</p>
        )}
      </aside>
    </div>
  );
}

function Evidencia({ id }) {
  const [url, setUrl] = useState(null);
  const [falta, setFalta] = useState(false);

  useEffect(() => {
    let vigente = true;
    let creada = null;
    setUrl(null);
    setFalta(false);
    api(`/incidents/${id}/evidence`, { binario: true })
      .then((blob) => {
        if (!vigente) return;
        creada = URL.createObjectURL(blob);
        setUrl(creada);
      })
      .catch(() => vigente && setFalta(true));
    return () => {
      vigente = false;
      if (creada) URL.revokeObjectURL(creada);
    };
  }, [id]);

  if (falta) return <p className="evidencia suave">Sin imagen de evidencia.</p>;
  if (!url) return <p className="evidencia suave">Cargando evidencia…</p>;
  return <img className="evidencia" src={url} alt="Evidencia del incidente con rostros difuminados" />;
}

function Revision({ incidente, alCambiar }) {
  const [estado, setEstado] = useState(incidente.status === "open" ? "reviewed" : incidente.status);
  const [comentario, setComentario] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const exigeComentario = estado === "closed" || estado === "false_positive";

  async function guardar(evento) {
    evento.preventDefault();
    setError("");
    setGuardando(true);
    try {
      const nuevo = await api(`/incidents/${incidente.id}`, {
        metodo: "PATCH",
        cuerpo: { status: estado, comment: comentario.trim() || null },
      });
      setComentario("");
      alCambiar(nuevo);
    } catch (e) {
      setError(e.message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form className="revision" onSubmit={guardar}>
      <h3>Revisión</h3>
      <label>
        Nuevo estado
        <select value={estado} onChange={(e) => setEstado(e.target.value)}>
          {Object.entries(ESTADO).map(([id, nombre]) => (
            <option key={id} value={id} disabled={id === incidente.status}>{nombre}</option>
          ))}
        </select>
      </label>
      <label>
        Comentario{exigeComentario ? " (obligatorio)" : ""}
        <textarea rows={3} maxLength={500} required={exigeComentario} value={comentario}
                  onChange={(e) => setComentario(e.target.value)} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" disabled={guardando || estado === incidente.status}>
        {guardando ? "Guardando…" : "Guardar revisión"}
      </button>
    </form>
  );
}
