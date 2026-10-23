-- Campos que informa el agente Edge además del incidente base:
-- el identificador de seguimiento de la persona (ByteTrack) y la lista completa
-- de infracciones detectadas en ella dentro del mismo evento.
ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS person_track_id INTEGER CHECK (person_track_id >= 0),
    ADD COLUMN IF NOT EXISTS violation_types TEXT[] CHECK (
        violation_types <@ ARRAY['missing_helmet', 'missing_reflective_vest']::TEXT[]
    );

CREATE INDEX IF NOT EXISTS incidents_detected_at_idx ON incidents (detected_at DESC);
