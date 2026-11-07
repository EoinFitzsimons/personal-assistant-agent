# Personal Assistant Agent

AI day planner. Click **Plan tomorrow** and the agent:

1. reads the last 48h of Slack, Teams and Outlook (read-only) plus tomorrow's calendar and your wearable data,
2. detects commitments you made ("I'll…", "will do", "let me…") and messages still waiting for your reply,
3. ranks them against your weekly goals, VIP people/channels and deadlines,
4. fits them around your meetings with a workout (lighter when recovery is low) and meal suggestions,
5. lets you review: drag to reschedule, approve/remove, or chat ("move my workout to 7am, skip lunch").

Design: [docs/design.md](docs/design.md).

## Quick start (Docker)

```bash
cp .env.example .env
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env   # required; add LLM key / OAuth apps as needed
docker compose up --build
```

Open http://localhost:3000, sign up, and click **Plan tomorrow**. New accounts start in **demo mode** with
realistic sample data, so the full flow works before any OAuth app is registered.

## Local development

```bash
# backend (SQLite by default)
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
RUN_JOBS_INLINE=true uvicorn app.main:app --reload   # or run `python -m app.worker` separately
pytest

# frontend
cd frontend && npm install && npm run dev
```

## Configuration

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `openai` or `anthropic`; empty = rule-based fallback for every AI step |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM credentials |
| `JWT_SECRET`, `TOKEN_ENCRYPTION_KEY` | Auth signing and Fernet encryption of OAuth tokens |
| `SLACK_*`, `MICROSOFT_*`, `FITBIT_*`, `OURA_*` | OAuth app credentials |

OAuth redirect URI for every provider: `$BACKEND_URL/connections/<provider>/callback`.

- **Slack**: create an app, add the *user token* scopes `channels:history groups:history im:history mpim:history
  channels:read groups:read im:read mpim:read users:read`.
- **Microsoft (Outlook + Teams)**: register a multi-tenant app in Entra ID with delegated permissions
  `offline_access User.Read Mail.Read Calendars.Read Chat.Read`. Some company tenants require IT admin consent.
- **Fitbit**: server app with scopes `sleep activity heartrate profile`.
- **Oura**: OAuth app with scopes `daily personal`.

## Project layout

```
backend/app/connectors   Slack, Microsoft Graph, Fitbit, Oura, demo data
backend/app/pipeline     commitments → rank → scheduler, chat edits, runner
backend/app/routers      auth, settings, connections (OAuth), plans
backend/app/worker.py    DB-backed job worker
frontend/src             Next.js app: settings/onboarding, timeline, chat
```
