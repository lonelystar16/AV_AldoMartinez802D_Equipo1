import { useEffect, useState } from "react";

// Carga `cargar()` y la repite cada `cadaMs` (0 = una vez). Así el monitoreo se
// actualiza sin recargar la página (RF-13). Si una consulta falla, se conservan
// los últimos datos y se informa el error.
export default function usarDatos(cargar, dependencias, cadaMs = 0) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [actualizado, setActualizado] = useState(null);

  useEffect(() => {
    let vigente = true;
    const traer = async () => {
      try {
        const nuevos = await cargar();
        if (!vigente) return;
        setDatos(nuevos);
        setError(null);
        setActualizado(new Date());
      } catch (e) {
        if (vigente) setError(e.message);
      }
    };
    traer();
    const id = cadaMs ? setInterval(traer, cadaMs) : null;
    return () => {
      vigente = false;
      if (id) clearInterval(id);
    };
  }, dependencias); // eslint-disable-line react-hooks/exhaustive-deps

  return { datos, error, actualizado };
}
