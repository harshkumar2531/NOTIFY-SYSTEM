# Realtime Notification System

A beginner-friendly, correctly-architected real-time notification backend built with
**FastAPI + MongoDB + Redis + PostgreSQL + VerneMQ (MQTT)**, all async.

---

## Architecture

```
   Client (web / mobile)
        ▲   │
  MQTT  │   │ REST/HTTP
 (push) │   ▼
   ┌────────────┐         ┌──────────────────────────────────┐
   │  VerneMQ   │◄────────│           FastAPI (brain)          │
   │ (delivery) │ publish  │  validate → store → decide → push │
   └────────────┘         └──┬──────────┬───────────┬─────────┘
                             │          │           │
                       PostgreSQL    MongoDB       Redis
                     (users, prefs) (notifications) (presence,
                      source of truth)  (history)    counters, cache)
```

| Tech        | Role                                                        |
|-------------|-------------------------------------------------------------|
| **FastAPI** | The brain — REST API, business logic, orchestration         |
| **PostgreSQL** | Source of truth: users, preferences (ACID, relational)   |
| **MongoDB** | Notification documents & history (flexible, high volume)    |
| **Redis**   | Speed layer: unread counters, online presence (in-memory)   |
| **VerneMQ** | MQTT broker = real-time delivery (TCP 1883, WebSocket 8080) |

**Golden rule:** always **store in the DB first, then publish to MQTT.** MQTT reaches
only *online* clients; the database guarantees durability and offline delivery.

---

## Prerequisites

- Docker Desktop (running)
- Python 3.11+
- VS Code with extensions: Python, Pylance, Docker, REST Client (or Thunder Client)

---

## Run it (Windows / PowerShell)

```powershell
# 1. Create & activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the 4 backing services (dev mode: anonymous MQTT)
docker compose up -d
docker compose ps

# 4. Run the API
uvicorn app.main:app --reload
```

Open:
- http://localhost:8000        — welcome message
- http://localhost:8000/health — all 4 services report "ok"
- http://localhost:8000/docs   — interactive API explorer
- http://localhost:8888/status — VerneMQ status page

### See a live notification

```powershell
# Terminal A: API running (above)
# Terminal B: subscribe as a user
python subscriber.py user123
```
Then POST a notification (see endpoints) for `user123` — it appears in Terminal B instantly.

---

## API endpoints

Write/admin endpoints require the header **`X-API-Key: <API_KEY from .env>`**.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET  | `/`                                    | —   | Liveness message |
| GET  | `/health`                              | —   | Status of all 4 services |
| POST | `/notifications`                       | 🔑  | Create + store + push (skips muted types) |
| GET  | `/notifications/{user_id}`             | —   | List a user's notifications (newest first) |
| GET  | `/notifications/{user_id}/unread-count`| —   | Fast unread badge value (Redis) |
| POST | `/notifications/{user_id}/mark-all-read`| 🔑 | Mark read in Mongo + reset counter |
| POST | `/presence/{user_id}/heartbeat`        | —   | Mark user online (refresh TTL) |
| GET  | `/presence/{user_id}`                  | —   | Is the user online? |
| POST | `/users`                               | 🔑  | Create/update a user |
| GET  | `/users/{user_id}`                     | —   | Fetch a user |
| PUT  | `/users/{user_id}/preferences`         | 🔑  | Enable/disable a notification type |
| GET  | `/users/{user_id}/preferences`         | —   | List a user's preferences |

### Example: create a notification (PowerShell)
```powershell
curl -X POST http://localhost:8000/notifications `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-secret-change-me" `
  -d '{\"user_id\":\"user123\",\"title\":\"Hello\",\"body\":\"Hi there\",\"type\":\"chat\"}'
```

---

## MQTT security (opt-in)

Dev mode allows anonymous MQTT so you can learn quickly. To enforce auth + ACLs:

```powershell
# Start in secure mode (both compose files)
docker compose -f docker-compose.yml -f docker-compose.secure.yml up -d

# Create MQTT accounts (passwords stored hashed)
docker exec -it notify-vernemq vmq-passwd /vernemq/etc/vmq.passwd backend
docker exec -it notify-vernemq vmq-passwd /vernemq/etc/vmq.passwd user123
docker compose restart vernemq
```

- `vernemq/vmq.acl` enforces: the **backend** may publish to `users/+/notifications`;
  each **end user** may only read their **own** `users/%u/#` topics.
- Set `MQTT_USERNAME` / `MQTT_PASSWORD` in `.env` so the backend publisher authenticates.

---

## Project layout

```
.
├── docker-compose.yml          # 4 services (dev: anonymous MQTT)
├── docker-compose.secure.yml   # opt-in MQTT auth + ACL override
├── requirements.txt
├── .env                        # secrets/config (gitignored)
├── subscriber.py               # test MQTT subscriber
├── vernemq/vmq.acl             # MQTT topic permissions
└── app/
    ├── main.py        # FastAPI app + routes + lifespan
    ├── config.py      # typed settings from .env
    ├── state.py       # shared connection clients
    ├── models.py      # Pydantic request/response models
    ├── db.py          # MongoDB helpers
    ├── crud.py        # notification create/list/mark-read (store→incr→push)
    ├── redis_ops.py   # unread counters + presence
    ├── pg_ops.py      # users + preferences (asyncpg)
    ├── schema.sql     # Postgres tables
    ├── mqtt.py        # publish to VerneMQ
    └── auth.py        # X-API-Key dependency
```

---

## Production checklist (before going live)

- [ ] **Migrations:** replace startup `CREATE IF NOT EXISTS` with **Alembic**.
- [ ] **MQTT client:** use ONE long-lived client in the lifespan (not per-publish),
      with reconnection handling.
- [ ] **TLS everywhere:** MQTTS (8883), HTTPS for the API, `wss://` for browsers.
- [ ] **Scale:** run uvicorn with multiple workers / gunicorn behind a reverse proxy.
- [ ] **Auth:** replace the shared API key with **JWT/OAuth**; issue per-user MQTT
      credentials at login.
- [ ] **Rate limiting** (e.g. Redis-based) + structured logging and metrics.
- [ ] **Mobile push to CLOSED apps** needs **APNs (iOS) / FCM (Android)** — a persistent
      MQTT connection only reaches apps that are open/connected.
- [ ] **Backups & retention** for MongoDB/Postgres; an unread-recount job from Mongo
      in case Redis is flushed.
```
