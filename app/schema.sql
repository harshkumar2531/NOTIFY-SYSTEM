CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,                 -- matches our user_id (e.g. 'user123')
    email      TEXT UNIQUE,
    name       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type    TEXT    NOT NULL,                     -- e.g. 'chat', 'order', 'marketing'
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (user_id, type)
);

-- Per-channel preferences: one row per (user, type, channel).
-- channel is 'inapp' | 'email' | 'sms' | 'push' (extensible).
-- A channel is considered enabled ONLY if a row exists with enabled = TRUE.
-- (Email is opt-in: no row => not sent by email.)
CREATE TABLE IF NOT EXISTS channel_preferences (
    user_id TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type    TEXT    NOT NULL,
    channel TEXT    NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, type, channel)
);
