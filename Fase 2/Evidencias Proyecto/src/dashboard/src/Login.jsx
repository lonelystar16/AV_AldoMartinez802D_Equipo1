import { useState } from "react";
import { api, guardarToken } from "./api.js";

export default function Login({ alEntrar }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function entrar(evento) {
    evento.preventDefault();
    setError("");
    setEnviando(true);
    try {
      const r = await api("/auth/login", { metodo: "POST", cuerpo: { email, password } });
      guardarToken(r.access_token);
      alEntrar(r.user);
    } catch (e) {
      setError(e.message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="login">
      <form className="panel" onSubmit={entrar}>
        <h1>
          Casco<span>Vision</span>
        </h1>
        <p className="suave">Monitoreo de EPP en la faena</p>
        <label>
          Correo
          <input type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Contraseña
          <input type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
