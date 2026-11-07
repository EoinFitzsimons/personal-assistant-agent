"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import Nav from "@/components/Nav";
import { api, Connection, Settings } from "@/lib/api";

const lines = (v: string[]) => v.join("\n");
const parseLines = (v: string) => v.split("\n").map((s) => s.trim()).filter(Boolean);
const parseCsv = (v: string) => v.split(",").map((s) => s.trim()).filter(Boolean);

function SettingsInner() {
  const params = useSearchParams();
  const [s, setS] = useState<Settings | null>(null);
  const [conns, setConns] = useState<Connection[]>([]);
  const [msg, setMsg] = useState(params.get("connected") ? `Connected ${params.get("connected")}.` : "");
  const [err, setErr] = useState(params.get("error") ? `Connection failed: ${params.get("error")}` : "");

  const load = useCallback(async () => {
    const [settings, connections] = await Promise.all([
      api<Settings>("/settings"),
      api<Connection[]>("/connections"),
    ]);
    setS(settings);
    setConns(connections);
  }, []);

  useEffect(() => {
    Promise.all([api<Settings>("/settings"), api<Connection[]>("/connections")])
      .then(([settings, connections]) => {
        setS(settings);
        setConns(connections);
      })
      .catch((e) => setErr(e.message));
  }, []);

  if (!s) return <main className="page">Loading…</main>;
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS({ ...s, [k]: v });

  async function save() {
    setErr("");
    setMsg("");
    try {
      setS(await api<Settings>("/settings", { method: "PUT", body: JSON.stringify(s) }));
      setMsg("Saved.");
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function connect(provider: string) {
    setErr("");
    try {
      const { url } = await api<{ url: string }>(`/connections/${provider}/authorize`);
      window.location.assign(url);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function disconnect(provider: string) {
    await api(`/connections/${provider}`, { method: "DELETE" });
    await load();
  }

  return (
    <main className="page settings">
      {params.get("welcome") && (
        <div className="banner">
          Welcome! Tell the assistant what matters to you, connect your apps (or keep demo data on), then go to{" "}
          <b>Plan</b>.
        </div>
      )}
      <section className="card">
        <h2>Connected apps</h2>
        <p className="muted small">Read-only access. We never post messages or change your calendar.</p>
        <ul className="conns">
          {conns.map((c) => (
            <li key={c.provider}>
              <div>
                <b>{c.name}</b> <span className="pill">{c.category}</span>
                {c.connected && <span className="muted small"> · {c.account}</span>}
                {!c.configured && <div className="muted small">Not configured on this server yet</div>}
              </div>
              {c.connected ? (
                <button onClick={() => disconnect(c.provider)}>Disconnect</button>
              ) : (
                <button
                  className="primary"
                  disabled={!c.configured || (c.category === "health" && !s.health_consent)}
                  title={c.category === "health" && !s.health_consent ? "Give health data consent below first" : ""}
                  onClick={() => connect(c.provider)}
                >
                  Connect
                </button>
              )}
            </li>
          ))}
        </ul>
        <label className="check">
          <input type="checkbox" checked={s.demo_mode} onChange={(e) => set("demo_mode", e.target.checked)} />
          Use demo data instead of my connected apps
        </label>
      </section>

      <section className="card">
        <h2>About you</h2>
        <div className="grid2">
          <label>
            Name
            <input value={s.name} onChange={(e) => set("name", e.target.value)} />
          </label>
          <label>
            Timezone
            <input value={s.timezone} onChange={(e) => set("timezone", e.target.value)} />
          </label>
          <label>
            Work starts
            <input
              type="time"
              value={s.working_hours.start}
              onChange={(e) => set("working_hours", { ...s.working_hours, start: e.target.value })}
            />
          </label>
          <label>
            Work ends
            <input
              type="time"
              value={s.working_hours.end}
              onChange={(e) => set("working_hours", { ...s.working_hours, end: e.target.value })}
            />
          </label>
        </div>
        <label>
          Weekly goals (one per line)
          <textarea
            rows={3}
            defaultValue={lines(s.weekly_goals)}
            onBlur={(e) => set("weekly_goals", parseLines(e.target.value))}
            placeholder="Ship onboarding flow"
          />
        </label>
        <div className="grid2">
          <label>
            VIP people (one per line)
            <textarea
              rows={3}
              defaultValue={lines(s.vip_people)}
              onBlur={(e) => set("vip_people", parseLines(e.target.value))}
              placeholder="Sarah Chen"
            />
          </label>
          <label>
            VIP channels / chats (one per line)
            <textarea
              rows={3}
              defaultValue={lines(s.vip_channels)}
              onBlur={(e) => set("vip_channels", parseLines(e.target.value))}
              placeholder="#leadership"
            />
          </label>
        </div>
      </section>

      <section className="card">
        <h2>Workouts & meals</h2>
        <div className="grid2">
          <label>
            Preferred workout time
            <select
              value={s.workout.preferred_time}
              onChange={(e) =>
                set("workout", { ...s.workout, preferred_time: e.target.value as Settings["workout"]["preferred_time"] })
              }
            >
              <option value="morning">Morning</option>
              <option value="midday">Midday</option>
              <option value="evening">Evening</option>
            </select>
          </label>
          <label>
            Workout length (min)
            <input
              type="number"
              min={10}
              max={180}
              value={s.workout.duration_min}
              onChange={(e) => set("workout", { ...s.workout, duration_min: Number(e.target.value) })}
            />
          </label>
          <label>
            Workout types (comma separated)
            <input
              defaultValue={s.workout.types.join(", ")}
              onBlur={(e) => set("workout", { ...s.workout, types: parseCsv(e.target.value) })}
            />
          </label>
          <label>
            Diet (e.g. vegetarian, vegan, gluten-free)
            <input
              defaultValue={s.diet.preferences.join(", ")}
              onBlur={(e) => set("diet", { ...s.diet, preferences: parseCsv(e.target.value) })}
            />
          </label>
          <label>
            Foods to avoid (comma separated)
            <input
              defaultValue={s.diet.avoid.join(", ")}
              onBlur={(e) => set("diet", { ...s.diet, avoid: parseCsv(e.target.value) })}
            />
          </label>
        </div>
        <div className="grid3">
          {(["breakfast", "lunch", "dinner"] as const).map((m) => (
            <label key={m}>
              {m[0].toUpperCase() + m.slice(1)} around
              <input type="time" value={s.meals[m]} onChange={(e) => set("meals", { ...s.meals, [m]: e.target.value })} />
            </label>
          ))}
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={s.health_consent}
            onChange={(e) => set("health_consent", e.target.checked)}
          />
          I consent to the assistant processing my health data (sleep, recovery, activity) to plan workouts. You can
          withdraw at any time.
        </label>
      </section>

      <div className="actions">
        {err && <span className="error">{err}</span>}
        {msg && <span className="ok">{msg}</span>}
        <button className="primary" onClick={save}>
          Save settings
        </button>
      </div>
    </main>
  );
}

export default function SettingsPage() {
  return (
    <>
      <Nav />
      <Suspense>
        <SettingsInner />
      </Suspense>
    </>
  );
}
