// Cliente de la API REST. El token vive en sessionStorage: se borra al cerrar
// la pestaña, y un 401 cierra la sesión (token vencido o usuario desactivado).
const BASE = "/api";
const CLAVE = "cascovision_token";

let token = leer();
let alCerrarSesion = () => {};

function leer() {
  try {
    return sessionStorage.getItem(CLAVE);
  } catch {
    return null;
  }
}

export function guardarToken(valor) {
  token = valor;
  try {
    if (valor) sessionStorage.setItem(CLAVE, valor);
    else sessionStorage.removeItem(CLAVE);
  } catch {
    // sin sessionStorage la sesión dura lo que la pestaña
  }
}

export const hayToken = () => Boolean(token);
export const alExpirar = (fn) => (alCerrarSesion = fn);

export class ErrorApi extends Error {
  constructor(status, mensaje) {
    super(mensaje);
    this.status = status;
  }
}

const TRADUCCION = {
  "Invalid email or password": "Correo o contraseña incorrectos.",
  "Insufficient role": "Tu rol no permite esta acción.",
  "Incident already has that status": "El incidente ya tiene ese estado.",
  "Already exists": "Ya existe un usuario con ese correo.",
  "JWT_SECRET is not configured": "La API no tiene configurado JWT_SECRET.",
  "User management requires PostgreSQL storage": "Gestionar usuarios requiere PostgreSQL.",
  "You cannot deactivate or demote yourself": "No puedes desactivarte ni quitarte el rol de administrador.",
  "User not found": "El usuario ya no existe.",
  "Resource management requires PostgreSQL storage": "Editar cámaras, zonas y balizas requiere PostgreSQL.",
  "Beacon IP is already in use": "Otra baliza ya usa esa IP.",
  "Zone already has a beacon": "Esa zona ya tiene una baliza.",
  "Camera or zone is not configured": "La cámara o la zona elegida no existe.",
};

async function detalle(respuesta) {
  try {
    const cuerpo = await respuesta.json();
    const d = cuerpo.detail;
    const texto = typeof d === "string" ? d : d?.[0]?.msg;
    return TRADUCCION[texto] ?? texto ?? respuesta.statusText;
  } catch {
    return respuesta.statusText || `Error ${respuesta.status}`;
  }
}

export async function api(ruta, { metodo = "GET", cuerpo, binario = false } = {}) {
  const cabeceras = {};
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";
  let respuesta;
  try {
    respuesta = await fetch(BASE + ruta, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    });
  } catch {
    throw new ErrorApi(0, "No se pudo conectar con la API.");
  }
  if (respuesta.status === 401 && token) {
    guardarToken(null);
    alCerrarSesion();
  }
  if (!respuesta.ok) throw new ErrorApi(respuesta.status, await detalle(respuesta));
  return binario ? respuesta.blob() : respuesta.json();
}

export function consulta(parametros) {
  const p = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor !== "" && valor !== null && valor !== undefined) p.set(clave, valor);
  }
  const texto = p.toString();
  return texto ? `?${texto}` : "";
}
