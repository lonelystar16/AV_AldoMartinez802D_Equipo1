import { useState } from "react";
import { api } from "./api.js";
import { ROL, fecha } from "./formato.js";
import usarDatos from "./usarDatos.js";

const NUEVO = { email: "", full_name: "", role: "prevencionista", password: "", phone: "" };

// Alta, edición y desactivación de usuarios por el administrador (CU-11).
// El correo y la contraseña no se editan aquí.
export default function Usuarios() {
  const [version, setVersion] = useState(0);
  const [nuevo, setNuevo] = useState(NUEVO);
  const [mensaje, setMensaje] = useState({ tipo: "", texto: "" });
  const [edicion, setEdicion] = useState(null);
  const [aviso, setAviso] = useState({ tipo: "", texto: "" });
  const { datos, error } = usarDatos(() => api("/users"), [version]);

  function abrir(u) {
    setAviso({ tipo: "", texto: "" });
    setEdicion({ id: u.id, email: u.email, full_name: u.full_name ?? "", phone: u.phone ?? "",
                 role: u.role, active: u.active });
  }

  async function guardar(evento) {
    evento.preventDefault();
    try {
      const { id, email, ...resto } = edicion;
      await api(`/users/${id}`, {
        metodo: "PATCH",
        cuerpo: { ...resto, phone: resto.phone.trim() || null },
      });
      setEdicion(null);
      setAviso({ tipo: "ok", texto: `Usuario ${email} actualizado.` });
      setVersion((v) => v + 1);
    } catch (e) {
      setAviso({ tipo: "error", texto: e.message });
    }
  }

  const campoEdicion = (nombre) => ({
    value: edicion[nombre],
    onChange: (e) => setEdicion({ ...edicion, [nombre]: e.target.value }),
  });

  async function crear(evento) {
    evento.preventDefault();
    setMensaje({ tipo: "", texto: "" });
    try {
      const creado = await api("/users", {
        metodo: "POST",
        cuerpo: { ...nuevo, phone: nuevo.phone.trim() || null },
      });
      setNuevo(NUEVO);
      setMensaje({ tipo: "ok", texto: `Usuario ${creado.email} creado.` });
      setVersion((v) => v + 1);
    } catch (e) {
      setMensaje({ tipo: "error", texto: e.message });
    }
  }

  const campo = (nombre) => ({
    value: nuevo[nombre],
    onChange: (e) => setNuevo({ ...nuevo, [nombre]: e.target.value }),
  });

  return (
    <div className="rejilla">
      <section className="panel ancho">
        <h2>Usuarios</h2>
        {error && <p className="error" role="alert">{error}</p>}
        {datos && (
          <div className="tabla">
            <table>
              <thead>
                <tr><th>Correo</th><th>Nombre</th><th>Rol</th><th>Activo</th><th>Último ingreso</th><th></th></tr>
              </thead>
              <tbody>
                {datos.map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td><td>{u.full_name}</td><td>{ROL[u.role]}</td>
                    <td>{u.active ? "Sí" : "No"}</td><td>{fecha(u.last_login_at)}</td>
                    <td>
                      <button type="button" className="secundario" onClick={() => abrir(u)}
                              aria-label={`Editar ${u.email}`}>Editar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {aviso.texto && (
          <p className={aviso.tipo === "ok" ? "exito" : "error"} role="status">{aviso.texto}</p>
        )}
      </section>

      {edicion && (
        <section className="panel ancho">
          <h2>Editar {edicion.email}</h2>
          <form className="filtros" onSubmit={guardar}>
            <label>Nombre<input required maxLength={120} {...campoEdicion("full_name")} /></label>
            <label>
              Rol
              <select {...campoEdicion("role")}>
                {Object.entries(ROL).map(([id, nombre]) => <option key={id} value={id}>{nombre}</option>)}
              </select>
            </label>
            <label>
              Teléfono (+569…)
              <input type="tel" pattern="\+[1-9][0-9]{1,14}" {...campoEdicion("phone")} />
            </label>
            <label className="casilla">
              <input type="checkbox" checked={edicion.active}
                     onChange={(e) => setEdicion({ ...edicion, active: e.target.checked })} />
              Activo (puede iniciar sesión y recibe avisos)
            </label>
            <div className="acciones">
              <button type="submit">Guardar</button>
              <button type="button" className="secundario" onClick={() => setEdicion(null)}>Cancelar</button>
            </div>
          </form>
        </section>
      )}

      <section className="panel ancho">
        <h2>Nuevo usuario</h2>
        <form className="filtros" onSubmit={crear}>
          <label>Correo<input type="email" required {...campo("email")} /></label>
          <label>Nombre<input required maxLength={120} {...campo("full_name")} /></label>
          <label>
            Rol
            <select {...campo("role")}>
              {Object.entries(ROL).map(([id, nombre]) => <option key={id} value={id}>{nombre}</option>)}
            </select>
          </label>
          <label>
            Contraseña (12+)
            <input type="password" autoComplete="new-password" required minLength={12} {...campo("password")} />
          </label>
          <label>
            Teléfono (+569…)
            <input type="tel" pattern="\+[1-9][0-9]{1,14}" {...campo("phone")} />
          </label>
          <button type="submit">Crear usuario</button>
        </form>
        {mensaje.texto && (
          <p className={mensaje.tipo === "ok" ? "exito" : "error"} role="status">{mensaje.texto}</p>
        )}
      </section>
    </div>
  );
}
