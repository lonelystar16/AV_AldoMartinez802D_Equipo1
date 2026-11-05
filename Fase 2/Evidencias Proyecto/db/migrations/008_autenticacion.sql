-- Inicio de sesion del dashboard (RF-17, tarea 4.16).
--
-- La API compara la contrasena con crypt() contra el hash bcrypt de users, asi
-- que el hash nunca sale de la base. Se instala en public y la API la llama
-- como public.crypt(), para que funcione con cualquier search_path.
-- Repetible: no hace nada si la extension ya existe.
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
