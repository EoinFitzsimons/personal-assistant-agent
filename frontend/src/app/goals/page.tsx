"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import Nav from "@/components/Nav";
import Skeleton from "@/components/Skeleton";
import { usePlanLoader } from "@/components/usePlanLoader";
import { api, getToken, latestPlan, PlanItem, Settings } from "@/lib/api";
import { dayLabel, hhmm, timed } from "@/lib/labels";

const minutes = (xs: PlanItem[]) => xs.reduce((sum, i) => sum + i.duration_min, 0);

export default function GoalsPage() {
  const { plan, loaded, error, setError } = usePlanLoader(latestPlan);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (!getToken()) return;
    api<Settings>("/settings")
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, [setError]);

  async function saveGoals(goals: string[]) {
    try {
      setSettings(await api<Settings>("/settings", { method: "PUT", body: JSON.stringify({ ...settings!, weekly_goals: goals }) }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim() || !settings) return;
    await saveGoals([...settings.weekly_goals, draft.trim()]);
    setDraft("");
  }

  const goals = settings?.weekly_goals ?? [];
  const work = plan?.status === "ready" ? timed(plan.items).filter((i) => ["task", "commitment", "follow_up"].includes(i.kind)) : [];
  const linked = (g: string) => work.filter((i) => i.reason.includes(`goal "${g}"`));
  const unlinked = work.filter((i) => !goals.some((g) => i.reason.includes(`goal "${g}"`)));
  const day = plan ? dayLabel(plan.date).toLowerCase() : "tomorrow";

  function list(items: PlanItem[]) {
    return (
      <ul className="list">
        {items.map((i) => (
          <li key={i.id} className="row-item">
            <span className="when fig">{hhmm(i.start)}</span>
            <span className="what">
              <span className="title">{i.title}</span>
            </span>
            <span className="muted small">{i.duration_min} min</span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <>
      <Nav />
      <main className="page narrow">
        <h1>Goals</h1>
        <p className="muted">What you want from this week, and how much of {day} goes to it.</p>
        {error && <p className="error">{error}</p>}
        {(!loaded || !settings) && !error && <Skeleton rows={2} />}
        {settings && (
          <>
            {goals.length === 0 && (
              <section className="sheet empty">
                <h2>No goals yet</h2>
                <p className="muted">Add one below. The planner moves work that serves it up the list.</p>
              </section>
            )}
            {goals.map((g) => {
              const items = linked(g);
              return (
                <section key={g} className="sheet goal">
                  <div className="goal-meta">
                    <h2>{g}</h2>
                    <button className="quiet" onClick={() => saveGoals(goals.filter((x) => x !== g))}>
                      Remove
                    </button>
                  </div>
                  {items.length > 0 ? (
                    <>
                      <p>
                        <span className="fig">{minutes(items)} min</span> planned {day}
                      </p>
                      {list(items)}
                    </>
                  ) : (
                    <p className="muted">Nothing planned for this {day} yet.</p>
                  )}
                </section>
              );
            })}
            {unlinked.length > 0 && (
              <section className="sheet goal quiet-sheet">
                <h2>Not linked to a goal</h2>
                <p>
                  <span className="fig">{minutes(unlinked)} min</span> of work {day}
                </p>
                {list(unlinked)}
              </section>
            )}
            <form className="add-goal" onSubmit={add}>
              <label>
                Add a goal for this week
                <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ship the onboarding flow" />
              </label>
              <button className="primary">Add goal</button>
            </form>
            {!plan && loaded && (
              <p className="muted small">
                Plan a day in <Link href="/plan">Week</Link> to see time against each goal.
              </p>
            )}
          </>
        )}
      </main>
    </>
  );
}
