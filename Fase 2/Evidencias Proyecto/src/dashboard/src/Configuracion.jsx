import { useEffect, useRef, useState } from "react";
import { api, consulta } from "./api.js";
import usarDatos from "./usarDatos.js";

// Cámaras, zonas y balizas del administrador (CU-09, CU-10). PUT crea o edita;
// no se borran porque los incidentes las referencian.
const ID = "[a-z0-9][a-z0-9\\-]{0,39}";
const SONIDO = { siren: "Sirena", voice: "Voz", beep: "Pitido" };
const CAMARA = { id: "", name: "", rtsp_url: "", location: "", active: true };
const ZONA = { id: "", camera_id: "", name: "", polygon: [], suppression_s: 60, active: true };
const BALIZA = { id: "", name: "", ip: "", zone_id: "", duration_s: 10, sound: "siren", message: "" };

export default function Configuracion() {
  const [version, setVersion] = useState(0);
  const { datos, error } = usarDatos(
    () => Promise.all([api("/cameras"), api("/zones"), api("/beacons")]),
    [version],
  );
  const recargar = () => setVersion((v) => v + 1);
  if (error && !datos) return <p className="error" role="alert">{error}</p>;
  if (!datos) return <p className="suave">Cargando…</p>;
  const [camaras, zonas, balizas] = datos;

  return (
    <div className="rejilla">
      <Camaras camaras={camaras} alGuardar={recargar} />
      <Zonas zonas={zonas} camaras={camaras} alGuardar={recargar} />
      <Balizas balizas={balizas} zonas={zonas} alGuardar={recargar} />
    </div>
  );
}

// Formulario de un recurso: `vacio` es el alta; editar carga la fila elegida.
function usarFormulario(vacio, ruta, alGuardar, preparar) {
  const [form, setForm] = useState(vacio);
  const [editando, setEditando] = useState(false);
  const [mensaje, setMensaje] = useState({ tipo: "", texto: "" });

  const campo = (nombre, numero = false) => ({
    value: form[nombre] ?? "",
    onChange: (e) => setForm({ ...form, [nombre]: numero ? Number(e.target.value) : e.target.value }),
  });
  const editar = (fila) => {
    setForm({ ...vacio, ...fila });
    setEditando(true);
    setMensaje({ tipo: "", texto: "" });
  };
  const nuevo = () => {
    setForm(vacio);
    setEditando(false);
  };
  async function guardar(evento) {
    evento.preventDefault();
    setMensaje({ tipo: "", texto: "" });
    const { id, ...resto } = form;
    try {
      await api(`/${ruta}/${id}`, { metodo: "PUT", cuerpo: preparar(resto) });
      setMensaje({ tipo: "ok", texto: `Guardado: ${id}.` });
      nuevo();
      alGuardar();
    } catch (e) {
      setMensaje({ tipo: "error", texto: e.message });
    }
  }
  return { form, setForm, campo, editar, nuevo, guardar, editando, mensaje };
}

const nulo = (texto) => (texto ?? "").trim() || null;

function Pie({ f, etiqueta }) {
  return (
    <>
      <div className="acciones">
        <button type="submit">{f.editando ? "Guardar cambios" : etiqueta}</button>
        {f.editando && <button type="button" className="secundario" onClick={f.nuevo}>Cancelar</button>}
      </div>
      {f.mensaje.texto && (
        <p className={f.mensaje.tipo === "ok" ? "exito" : "error"} role="status">{f.mensaje.texto}</p>
      )}
    </>
  );
}

function Camaras({ camaras, alGuardar }) {
  const f = usarFormulario(CAMARA, "cameras", alGuardar, (c) => ({ ...c, location: nulo(c.location) }));
  return (
    <section className="panel ancho">
      <h2>Cámaras</h2>
      <Tabla
        filas={camaras}
        columnas={["ID", "Nombre", "URL RTSP", "Ubicación", "Activa"]}
        celdas={(c) => [c.id, c.name, c.rtsp_url, c.location ?? "—", c.active ? "Sí" : "No"]}
        editar={f.editar}
      />
      <form className="filtros" onSubmit={f.guardar}>
        <label>ID<input required pattern={ID} disabled={f.editando} {...f.campo("id")} /></label>
        <label>Nombre<input required maxLength={80} {...f.campo("name")} /></label>
        <label>
          URL RTSP (sin usuario ni clave)
          <input required pattern={"rtsps?://[^\\/@\\s]+(/\\S*)?"} placeholder="rtsp://192.168.1.20/stream"
                 {...f.campo("rtsp_url")} />
        </label>
        <label>Ubicación<input maxLength={120} {...f.campo("location")} /></label>
        <label className="casilla">
          <input type="checkbox" checked={f.form.active}
                 onChange={(e) => f.setForm({ ...f.form, active: e.target.checked })} />
          Activa
        </label>
        <Pie f={f} etiqueta="Registrar cámara" />
      </form>
    </section>
  );
}

function Zonas({ zonas, camaras, alGuardar }) {
  const f = usarFormulario(ZONA, "zones", alGuardar, (z) => z);
  const nombreCamara = Object.fromEntries(camaras.map((c) => [c.id, c.name]));
  const listo = f.form.polygon.length >= 3;
  return (
    <section className="panel ancho">
      <h2>Zonas de riesgo</h2>
      <Tabla
        filas={zonas}
        columnas={["ID", "Nombre", "Cámara", "Puntos", "Supresión"]}
        celdas={(z) => [z.id, z.name, nombreCamara[z.camera_id] ?? z.camera_id, z.polygon.length,
                        `${z.suppression_s} s`]}
        editar={f.editar}
      />
      <form className="filtros" onSubmit={(e) => (listo ? f.guardar(e) : e.preventDefault())}>
        <label>ID<input required pattern={ID} disabled={f.editando} {...f.campo("id")} /></label>
        <label>Nombre<input required maxLength={80} {...f.campo("name")} /></label>
        <label>
          Cámara
          <select required {...f.campo("camera_id")}>
            <option value="">Elegir…</option>
            {camaras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>
          Supresión de alertas (s)
          <input type="number" min={10} max={600} required {...f.campo("suppression_s", true)} />
        </label>
        <div className="ancho">
          <EditorZona camaraId={f.form.camera_id} puntos={f.form.polygon}
                      alCambiar={(polygon) => f.setForm({ ...f.form, polygon })} />
        </div>
        {!listo && <p className="suave ancho">Marque al menos 3 puntos para guardar la zona.</p>}
        <p className="suave ancho">
          El agente vigila una zona por cámara (la primera por ID) y aplica los cambios de esa zona en
          30 s. Una zona nueva en la misma cámara se toma al reiniciar el agente.
        </p>
        <Pie f={f} etiqueta="Registrar zona" />
      </form>
    </section>
  );
}

function Balizas({ balizas, zonas, alGuardar }) {
  const f = usarFormulario(BALIZA, "beacons", alGuardar,
                           (b) => ({ ...b, zone_id: nulo(b.zone_id), message: nulo(b.message) }));
  const nombreZona = Object.fromEntries(zonas.map((z) => [z.id, z.name]));
  return (
    <section className="panel ancho">
      <h2>Balizas</h2>
      <Tabla
        filas={balizas}
        columnas={["ID", "Nombre", "IP", "Zona", "Alerta", "Estado"]}
        celdas={(b) => [b.id, b.name, b.ip, nombreZona[b.zone_id] ?? "Sin zona",
                        `${SONIDO[b.sound] ?? b.sound} · ${b.duration_s} s`,
                        b.online ? "En línea" : "Fuera de línea"]}
        editar={f.editar}
      />
      <form className="filtros" onSubmit={f.guardar}>
        <label>ID<input required pattern={ID} disabled={f.editando} {...f.campo("id")} /></label>
        <label>Nombre<input required maxLength={80} {...f.campo("name")} /></label>
        <label>IP<input required placeholder="192.168.1.50" {...f.campo("ip")} /></label>
        <label>
          Zona
          <select {...f.campo("zone_id")}>
            <option value="">Sin zona</option>
            {zonas.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
          </select>
        </label>
        <label>
          Duración (1–30 s)
          <input type="number" min={1} max={30} required {...f.campo("duration_s", true)} />
        </label>
        <label>
          Sonido
          <select {...f.campo("sound")}>
            {Object.entries(SONIDO).map(([id, nombre]) => <option key={id} value={id}>{nombre}</option>)}
          </select>
        </label>
        <label>Mensaje en pantalla<input maxLength={40} {...f.campo("message")} /></label>
        <Pie f={f} etiqueta="Registrar baliza" />
      </form>
    </section>
  );
}

function Tabla({ filas, columnas, celdas, editar }) {
  if (!filas.length) return <p className="suave">Sin registros.</p>;
  return (
    <div className="tabla">
      <table>
        <thead>
          <tr>{columnas.map((c) => <th key={c}>{c}</th>)}<th><span className="oculto">Acciones</span></th></tr>
        </thead>
        <tbody>
          {filas.map((fila) => (
            <tr key={fila.id}>
              {celdas(fila).map((v, i) => <td key={i}>{v}</td>)}
              <td>
                <button type="button" className="secundario" onClick={() => editar(fila)}
                        aria-label={`Editar ${fila.id}`}>
                  Editar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const redondear = (v) => Math.round(Math.min(1, Math.max(0, v)) * 1000) / 1000;
const comoTexto = (puntos) => puntos.map(([x, y]) => `${x}, ${y}`).join("\n");

function leerTexto(texto) {
  const lineas = texto.split("\n").map((l) => l.trim()).filter(Boolean);
  const puntos = lineas.map((l) => l.split(",").map((v) => v.trim()));
  const validos = puntos.every((p) => p.length === 2 && p.every((v) => v !== "" && Number(v) >= 0 && Number(v) <= 1));
  return validos ? puntos.map((p) => p.map(Number)) : null;
}

// Polígono en coordenadas relativas del cuadro (0 a 1), las mismas que usa el
// agente. De fondo va la última evidencia de la cámara, ya difuminada.
function EditorZona({ camaraId, puntos, alCambiar }) {
  const [fondo, setFondo] = useState(null);
  const [texto, setTexto] = useState(comoTexto(puntos));
  const lienzo = useRef(null);

  useEffect(() => setTexto(comoTexto(puntos)), [puntos]);

  useEffect(() => {
    let vigente = true;
    let creada = null;
    setFondo(null);
    if (!camaraId) return undefined;
    api("/incidents" + consulta({ camera_id: camaraId, limit: 1 }))
      .then((lista) => (lista[0] ? api(`/incidents/${lista[0].id}/evidence`, { binario: true }) : null))
      .then((blob) => {
        if (!vigente || !blob) return;
        creada = URL.createObjectURL(blob);
        setFondo(creada);
      })
      .catch(() => {}); // sin evidencia se dibuja sobre el lienzo vacío
    return () => {
      vigente = false;
      if (creada) URL.revokeObjectURL(creada);
    };
  }, [camaraId]);

  function marcar(evento) {
    const caja = lienzo.current.getBoundingClientRect();
    alCambiar([...puntos, [redondear((evento.clientX - caja.left) / caja.width),
                           redondear((evento.clientY - caja.top) / caja.height)]]);
  }

  return (
    <div className="editor-zona">
      <div className="lienzo" ref={lienzo} onClick={marcar}>
        {fondo ? <img src={fondo} alt="Último cuadro de la cámara" /> : <div className="vacio">Sin imagen de la cámara</div>}
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
          {puntos.length > 1 && <polygon points={puntos.map((p) => p.join(",")).join(" ")} />}
          {puntos.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="0.012" />)}
        </svg>
      </div>
      <div className="acciones">
        <span className="suave">Haga clic en la imagen para marcar cada vértice ({puntos.length}).</span>
        <button type="button" className="secundario" disabled={!puntos.length}
                onClick={() => alCambiar(puntos.slice(0, -1))}>Deshacer punto</button>
        <button type="button" className="secundario" disabled={!puntos.length}
                onClick={() => alCambiar([])}>Borrar todo</button>
      </div>
      <label>
        Puntos (x, y entre 0 y 1, uno por línea)
        <textarea rows={4} value={texto} aria-invalid={!leerTexto(texto)}
                  onChange={(e) => setTexto(e.target.value)}
                  onBlur={() => {
                    const leidos = leerTexto(texto);
                    if (leidos) alCambiar(leidos);
                  }} />
      </label>
      {!leerTexto(texto) && <p className="error" role="alert">Cada línea debe ser «x, y» con valores entre 0 y 1.</p>}
    </div>
  );
}
