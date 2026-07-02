CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,                
    email      TEXT UNIQUE,
    name       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type    TEXT    NOT NULL,                     
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (user_id, type)
);

CREATE TABLE IF NOT EXISTS channel_preferences (
    user_id TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type    TEXT    NOT NULL,
    channel TEXT    NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, type, channel)
);
