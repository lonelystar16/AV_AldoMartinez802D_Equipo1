import { useState } from "react";
import { api } from "./api.js";
import { ROL, fecha } from "./formato.js";
import usarDatos from "./usarDatos.js";

const NUEVO = { email: "", full_name: "", role: "prevencionista", password: "", phone: "" };

// Alta de usuarios por el administrador (CU-11). Editar o desactivar se hace en la base.
export default function Usuarios() {
  const [version, setVersion] = useState(0);
  const [nuevo, setNuevo] = useState(NUEVO);
  const [mensaje, setMensaje] = useState({ tipo: "", texto: "" });
  const { datos, error } = usarDatos(() => api("/users"), [version]);

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
                <tr><th>Correo</th><th>Nombre</th><th>Rol</th><th>Activo</th><th>Último ingreso</th></tr>
              </thead>
              <tbody>
                {datos.map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td><td>{u.full_name}</td><td>{ROL[u.role]}</td>
                    <td>{u.active ? "Sí" : "No"}</td><td>{fecha(u.last_login_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

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
