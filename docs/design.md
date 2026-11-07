# Personal Assistant Agent — v1 Design

## Goal

A multi-user web app. A user clicks **Plan tomorrow**; the agent gathers data from their
work apps (Slack, Outlook mail + calendar, Teams chat) and wearables, then builds a
prioritised plan for tomorrow containing work tasks, existing meetings, a workout and meal
suggestions. The user reviews and adjusts the plan in a timeline view or by chatting.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Audience | Product with sign-up (multi-tenant) |
| Platform | Web app; health data only from wearables with web APIs (Fitbit, Oura in v1) |
| Permissions | Read-only in v1; calendar write-back in v2 |
| Health depth | Light: workout type + duration in a free slot, simple meal suggestions |
| Prioritisation | AI ranking against user context (weekly goals, VIPs, VIP channels, working hours) |
| Review | Timeline (approve / delete / drag-to-reschedule) + chat box for edits |
| Architecture | Pipeline with LLM steps + deterministic scheduler |
| Commitments | High-confidence commitments auto-added; low-confidence go to an inbox |

## Architecture

```
 Next.js web app  ──HTTP──▶  FastAPI backend  ──▶  Postgres
                                   │  enqueue job
                                   ▼
                              Worker process (DB-backed job queue)
                                   │
          ┌────────────────────────┼─────────────────────────┐
     Connectors               Planning pipeline            LLM layer
  Slack / Graph / Fitbit /   detect → rank → schedule     OpenAI | Anthropic |
  Oura / Demo                → explain                    rule-based fallback
```

Components:

1. **Web app** — sign-up/login, onboarding (connect apps, goals, VIPs, working hours,
   workout + diet preferences), plan timeline, chat panel, commitments inbox.
2. **API** — auth (JWT), settings, OAuth connect/callback, plan CRUD, chat.
3. **Connectors** — one per source; each handles OAuth and maps raw data into the
   normalised types `Item` (message/email), `Event` (calendar) and `HealthMetric`.
4. **Worker** — polls a `jobs` table and runs sync + pipeline so the UI stays responsive.
5. **Pipeline** — see below.
6. **Database** — users, connections (Fernet-encrypted tokens), jobs, plans, plan items,
   chat messages.

## Planning flow

1. `POST /plans` creates a plan (`gathering`) and enqueues a job.
2. Worker syncs every connected source:
   - messages & emails from the last 48h (received **and** sent by the user),
   - tomorrow's calendar events,
   - latest sleep / readiness / activity metrics.
3. **Commitment detection (user's own messages)**
   - Keyword prefilter: `will`, `will do`, `I'll`, `I will`, `let me`, `on it`,
     `I can do that`, `by tomorrow`, `by EOD`, …
   - LLM confirmation with thread context: is this a real commitment? Extract task,
     owed-to person, deadline, confidence, source link.
   - Drop commitments already completed (later "done"/"sent" in the same thread).
4. **Follow-up expected (incoming messages)** — questions/requests addressed to the user
   with no reply from the user yet in that thread.
5. **Ranking** — LLM orders candidates against goals, VIPs, VIP channels and deadlines,
   returning a priority score, estimated duration and a one-line reason. Commitments get a
   boost (promise made), more if owed to a VIP or due by tomorrow.
6. **Scheduling (deterministic)** — inside working hours, around existing meetings:
   meals at preferred windows, workout in the preferred window (duration reduced when
   readiness/sleep is low), then tasks in priority order with 5-minute buffers. Tasks that
   don't fit are marked `unscheduled`.
7. Plan becomes `ready`; the UI polls and renders the timeline.
8. **Chat edits** — the LLM turns a request into structured edit ops
   (`move`, `remove`, `add`, `resize`); the scheduler re-validates (no overlaps with
   meetings), and the plan is updated.

When no LLM key is configured, rule-based fallbacks run for every LLM step
(keyword confidence, heuristic scoring, regex chat-command parser).

## Data model (main tables)

- `users` — email, password hash, settings JSON (timezone, working hours, weekly goals,
  VIP people, VIP channels, workout preferences, diet preferences, meal windows).
- `connections` — user, provider, encrypted access/refresh tokens, expiry, account label.
- `jobs` — type, payload, status, attempts, error.
- `plans` — user, date, status (`gathering|planning|ready|failed`), sources summary.
- `plan_items` — plan, kind (`meeting|task|commitment|follow_up|workout|meal`), title,
  start/end, priority, reason, source (provider + link), confidence, status
  (`proposed|approved|removed|inbox|unscheduled`).
- `chat_messages` — plan, role, content, applied ops.

## Integrations & security

- **Slack** — OAuth v2 with user scopes `channels:history groups:history im:history
  mpim:history users:read`.
- **Microsoft Graph** — authorization-code flow, multi-tenant app; scopes
  `offline_access User.Read Mail.Read Calendars.Read Chat.Read`. Some tenants require admin
  consent; the UI surfaces this error clearly.
- **Fitbit** (`sleep activity heartrate`) and **Oura** (`daily`) — OAuth2.
- Tokens encrypted at rest (Fernet key from env). Minimal retention: raw messages are not
  stored, only extracted plan items with a link back to the source.
- Health data is GDPR special-category data: explicit consent checkbox during
  onboarding; account deletion removes all data.

## Out of scope for v1 (data model leaves room)

Scheduled nightly runs, calendar write-back, drafting/sending replies, Garmin/Whoop
(partner programmes), learning from user edits.

## Testing

- Unit: commitment prefilter/detection, scheduler (overlaps, working hours, readiness),
  chat-command parsing.
- API: end-to-end plan creation in demo mode (demo connector with realistic sample data).
