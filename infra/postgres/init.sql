CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$ BEGIN
    CREATE TYPE doc_status AS ENUM (
        'uploaded',
        'extracted',
        'classified',
        'validated',
        'validated_with_errors',
        'loaded',
        'failed'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS documents (
    doc_id              UUID PRIMARY KEY,
    filename            TEXT NOT NULL,
    mime_type           TEXT,
    size_bytes          BIGINT,
    sha256              TEXT NOT NULL,
    storage_path        TEXT NOT NULL,
    status              doc_status NOT NULL DEFAULT 'uploaded',

    doc_type            TEXT,
    number              TEXT,
    doc_date            DATE,
    counterparty_name   TEXT,
    counterparty_inn    TEXT,
    counterparty_kpp    TEXT,
    amount_total        NUMERIC(18,2),
    amount_vat          NUMERIC(18,2),
    currency            TEXT DEFAULT 'RUB',

    raw                 JSONB,
    fields              JSONB,
    summary             TEXT,
    summary_detailed    TEXT,
    vat_rate            NUMERIC(5,2),
    text_content        TEXT,
    text_search         tsvector,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary_detailed TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS vat_rate NUMERIC(5,2);

CREATE INDEX IF NOT EXISTS idx_documents_status      ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type    ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_created_at  ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_inn         ON documents(counterparty_inn);
CREATE INDEX IF NOT EXISTS idx_documents_sha256      ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_documents_text_search ON documents USING GIN(text_search);
CREATE INDEX IF NOT EXISTS idx_documents_fields_gin  ON documents USING GIN(fields);

CREATE OR REPLACE FUNCTION documents_text_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.text_search :=
        setweight(to_tsvector('russian', coalesce(NEW.counterparty_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.number, '')),            'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.text_content, '')),      'B');
    NEW.updated_at := NOW();
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_text_search ON documents;
CREATE TRIGGER trg_documents_text_search
    BEFORE INSERT OR UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_text_search_trigger();

CREATE TABLE IF NOT EXISTS processing_events (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,
    message     TEXT,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_processing_events_doc_id ON processing_events(doc_id, created_at);

CREATE TABLE IF NOT EXISTS contractors (
    inn         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kpp         TEXT,
    address     TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    username       TEXT PRIMARY KEY,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'admin',
    first_name     TEXT,
    last_name      TEXT,
    email          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email      TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
