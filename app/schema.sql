CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    email      TEXT UNIQUE,
    name       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type    TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (user_id, type)
);