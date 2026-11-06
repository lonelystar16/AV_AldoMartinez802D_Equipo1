import { useEffect, useState } from "react";
import { alExpirar, api, guardarToken, hayToken } from "./api.js";
import { ROL } from "./formato.js";
import Login from "./Login.jsx";
import Monitoreo from "./Monitoreo.jsx";
import Historial from "./Historial.jsx";
import Usuarios from "./Usuarios.jsx";
import Detalle from "./Detalle.jsx";

const VISTAS = [
  { id: "monitoreo", nombre: "Monitoreo" },
  { id: "historial", nombre: "Historial" },
  { id: "usuarios", nombre: "Usuarios", rol: "admin" },
];

export default function App() {
  const [usuario, setUsuario] = useState(null);
  const [cargando, setCargando] = useState(hayToken());
  const [vista, setVista] = useState("monitoreo");
  const [abierto, setAbierto] = useState(null); // incidente del panel de detalle
  const [version, setVersion] = useState(0); // fuerza recargar tras una revisión

  useEffect(() => {
    alExpirar(() => setUsuario(null));
    if (!hayToken()) return;
    // Un 401 ya borra el token en api.js; otro error (API reiniciando) no cierra la sesión.
    api("/auth/me")
      .then(setUsuario)
      .catch(() => {})
      .finally(() => setCargando(false));
  }, []);

  if (cargando) return <p className="centro">Cargando…</p>;
  if (!usuario) return <Login alEntrar={setUsuario} />;

  const salir = () => {
    guardarToken(null);
    setUsuario(null);
  };
  const visibles = VISTAS.filter((v) => !v.rol || v.rol === usuario.role);

  return (
    <>
      <header className="barra">
        <h1>
          Casco<span>Vision</span>
        </h1>
        <nav aria-label="Secciones">
          {visibles.map((v) => (
            <button
              key={v.id}
              className={vista === v.id ? "pestana activa" : "pestana"}
              aria-current={vista === v.id ? "page" : undefined}
              onClick={() => setVista(v.id)}
            >
              {v.nombre}
            </button>
          ))}
        </nav>
        <div className="sesion">
          <span>
            {usuario.full_name || usuario.email} · {ROL[usuario.role]}
          </span>
          <button className="secundario" onClick={salir}>
            Salir
          </button>
        </div>
      </header>
      <main>
        {vista === "monitoreo" && <Monitoreo abrir={setAbierto} version={version} />}
        {vista === "historial" && <Historial abrir={setAbierto} version={version} />}
        {vista === "usuarios" && <Usuarios />}
      </main>
      {abierto && (
        <Detalle
          incidente={abierto}
          usuario={usuario}
          cerrar={() => setAbierto(null)}
          alCambiar={(nuevo) => {
            setAbierto(nuevo);
            setVersion((v) => v + 1);
          }}
        />
      )}
    </>
  );
}
