-- Ciclo de vida del aviso de una persona sin EPP.
--
-- El agente Edge no silencia los avisos repetidos: los mantiene vivos con un
-- ping periodico. Para que la API pueda registrar cuando empezo y cuando
-- termino el registro, cada aviso informa su momento del ciclo:
--
--   inicio : la persona aparece sin EPP. Se crea el registro.
--   ping   : sigue sin cambios. Se actualiza el mismo registro, sin duplicarlo.
--   fin    : ya no esta sin EPP. Se cierra el registro.
--
-- `episode_id` lo genera el agente en el inicio y lo reenvia en cada ping y en
-- el fin. Es lo que permite que la API encuentre el mismo registro aunque los
-- avisos viajen por separado, o incluso desde la cola local.
ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS episode_id UUID,
    ADD COLUMN IF NOT EXISTS event TEXT NOT NULL DEFAULT 'inicio' CHECK (
        event IN ('inicio', 'ping', 'fin')
    ),
    ADD COLUMN IF NOT EXISTS ping_count INTEGER NOT NULL DEFAULT 0 CHECK (ping_count >= 0),
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_ping_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ CHECK (
        ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at
    );

-- Un solo registro por episodio: los pings actualizan esa fila en vez de abrir
-- un incidente nuevo cada 60 s.
CREATE UNIQUE INDEX IF NOT EXISTS incidents_episode_id_idx
    ON incidents (episode_id)
    WHERE episode_id IS NOT NULL;
