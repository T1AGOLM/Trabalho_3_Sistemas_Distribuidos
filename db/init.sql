-- ============================================================
-- Sistema Cliente/Servidor em Camadas - Processamento de Audio
-- Esquema do banco de dados (executado automaticamente pelo
-- docker-compose; para uso manual: psql -d audio_db -f db/init.sql)
-- ============================================================

CREATE TABLE IF NOT EXISTS audios (
    id              UUID PRIMARY KEY,
    original_name   VARCHAR(255) NOT NULL,
    original_ext    VARCHAR(16)  NOT NULL,
    mime_type       VARCHAR(100) NOT NULL,
    size_bytes      BIGINT       NOT NULL DEFAULT 0,
    duration_sec    DOUBLE PRECISION,
    sample_rate     INTEGER,
    channels        INTEGER,
    bitrate         INTEGER,
    processing_type VARCHAR(50)  NOT NULL DEFAULT 'none',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    path_original   VARCHAR(500),
    path_processed  VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS idx_audios_created_at     ON audios (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audios_processing     ON audios (processing_type);
