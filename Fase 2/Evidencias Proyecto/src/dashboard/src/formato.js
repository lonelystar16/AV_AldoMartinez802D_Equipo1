export const INFRACCION = {
  missing_helmet: "Sin casco",
  missing_reflective_vest: "Sin chaleco",
};

export const ESTADO = {
  open: "Abierto",
  reviewed: "Revisado",
  closed: "Cerrado",
  false_positive: "Falso positivo",
};

export const BALIZA = {
  alerted: "Alertada",
  failed: "Falló",
  skipped_offline: "Fuera de línea",
};

export const ROL = {
  admin: "Administrador",
  prevencionista: "Prevencionista",
  supervisor: "Supervisor",
};

export function fecha(valor) {
  if (!valor) return "—";
  return new Date(valor).toLocaleString("es-CL", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function duracion(segundos) {
  if (segundos === null || segundos === undefined) return "—";
  const s = Math.round(segundos);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export const infracciones = (inc) =>
  (inc.violation_types?.length ? inc.violation_types : [inc.violation_type])
    .map((t) => INFRACCION[t] ?? t)
    .join(" + ");

export const puedeRevisar = (usuario) =>
  usuario?.role === "admin" || usuario?.role === "prevencionista";
