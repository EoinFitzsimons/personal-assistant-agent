"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import Nav from "@/components/Nav";
import Skeleton from "@/components/Skeleton";
import Timeline from "@/components/Timeline";
import { api, ChatMessage, getToken, Plan, PlanItem, PlanSummary } from "@/lib/api";
import { dayLabel, hhmm, longDate } from "@/lib/labels";

const STATUS_TEXT: Record<string, string> = {
  gathering: "Reading your messages, email, calendar and health data.",
  planning: "Putting tomorrow in order.",
  failed: "Planning failed.",
};

function progressOf(plan: Plan) {
  const marked = plan.items.filter((i) => i.outcome).length;
  const kept = plan.items.filter((i) => i.kind !== "meeting" && (i.status === "approved" || i.fixed)).length;
  const removed = plan.items.filter((i) => i.status === "removed").length;
  const parts: string[] = [];
  if (marked) parts.push(`${marked} marked done or skipped`);
  if (kept) parts.push(`${kept} kept or moved`);
  if (removed) parts.push(`${removed} removed`);
  if (plan.review_note) parts.push("your review note");
  if (plan.messages.length) parts.push("chat edits");
  return parts;
}

function sourceLine(plan: Plan) {
  const c = plan.summary.counts ?? {};
  const h = plan.summary.health ?? {};
  const from = (plan.summary.sources ?? []).join(", ") || "your apps";
  const parts = [
    `Read ${c.messages ?? 0} messages, ${c.emails ?? 0} emails and ${c.meetings ?? 0} meetings from ${from}.`,
    `Found ${c.commitments ?? 0} ${c.commitments === 1 ? "promise" : "promises"} and ${c.follow_ups ?? 0} ${c.follow_ups === 1 ? "reply" : "replies"} owed.`,
  ];
  if (h.sleep_hours !== undefined) {
    parts.push(`Slept ${h.sleep_hours} h${h.readiness !== undefined ? `, readiness ${h.readiness}` : ""}.`);
  }
  return parts.join(" ");
}

export default function WeekPage() {
  const router = useRouter();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<PlanSummary[]>([]);

  useEffect(() => {
    if (!getToken()) return;
    api<PlanSummary[]>("/plans")
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [plan?.id, plan?.status]);

  const refresh = useCallback(async (id?: number) => {
    const p = id ? await api<Plan>(`/plans/${id}`) : await api<Plan | null>("/plans/latest");
    setPlan(p);
    setLoaded(true);
    return p;
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<Plan | null>("/plans/latest")
      .then((p) => {
        setPlan(p);
        setLoaded(true);
      })
      .catch((e) => setError(e.message));
  }, [router]);

  useEffect(() => {
    if (!plan || !["gathering", "planning"].includes(plan.status)) return;
    const t = setTimeout(() => refresh(plan.id).catch((e) => setError(e.message)), 1200);
    return () => clearTimeout(t);
  }, [plan, refresh]);

  async function run<T>(fn: () => Promise<T>) {
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const [confirming, setConfirming] = useState(false);
  const start = (replace = false) =>
    run(async () => {
      setConfirming(false);
      setPlan(await api<Plan>(`/plans${replace ? "?replace=true" : ""}`, { method: "POST" }));
    });
  const patch = (item: PlanItem, body: object) =>
    run(async () =>
      setPlan(await api<Plan>(`/plans/${plan!.id}/items/${item.id}`, { method: "PATCH", body: JSON.stringify(body) })),
    );
  const approveAll = () => run(async () => setPlan(await api<Plan>(`/plans/${plan!.id}/approve`, { method: "POST" })));
  const send = async (message: string) => {
    const optimistic: ChatMessage = { id: -Date.now(), role: "user", content: message, created_at: "" };
    setPlan((p) => (p ? { ...p, messages: [...p.messages, optimistic] } : p));
    await run(async () => {
      const r = await api<{ reply: string; plan: Plan }>(`/plans/${plan!.id}/chat`, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      setPlan(r.plan);
    });
  };

  const items = plan?.items ?? [];
  const inbox = items.filter((i) => i.status === "inbox");
  const unscheduled = items.filter((i) => i.status === "unscheduled");
  const removed = items.filter((i) => i.status === "removed");
  const ready = plan?.status === "ready";
  const proposed = items.filter((i) => i.status === "proposed").length;

  const progress = plan?.status === "ready" && dayLabel(plan.date) === "Tomorrow" ? progressOf(plan) : [];
  const replan = () => (progress.length ? setConfirming(true) : start());
  const past = history.filter((h) => h.id !== plan?.id && h.status === "ready");
  const busy = plan?.status === "gathering" || plan?.status === "planning";

  return (
    <>
      <Nav />
      <main className="page plan">
        <div className="plan-head">
          <div>
            <h1>{plan ? dayLabel(plan.date) : "Plan tomorrow"}</h1>
            {plan && <p className="muted">{longDate(plan.date)}</p>}
            {ready && <p className="muted small">{sourceLine(plan!)}</p>}
          </div>
          <div className="head-actions">
            {ready && proposed > 0 && <button onClick={approveAll}>Keep all suggestions ({proposed})</button>}
            <button className="primary" onClick={replan} disabled={busy || confirming}>
              {plan ? "Re-plan tomorrow" : "Plan tomorrow"}
            </button>
          </div>
        </div>
        {confirming && (
          <section className="sheet confirm" role="alert">
            <p>
              Re-planning replaces tomorrow&apos;s plan. You&apos;ll lose {progress.join(", ")}.
            </p>
            <div className="row">
              <button className="primary" onClick={() => start(true)}>
                Replace the plan
              </button>
              <button onClick={() => setConfirming(false)}>Keep my progress</button>
            </div>
          </section>
        )}
        {error && <p className="error">{error}</p>}
        {plan?.summary.errors?.length ? (
          <div className="banner warn">Some sources failed: {plan.summary.errors.join("; ")}</div>
        ) : null}

        {!loaded && <Skeleton />}
        {loaded && !plan && (
          <section className="sheet empty">
            <h2>Ready when you are</h2>
            <p className="muted">
              The assistant reads the last 48 hours of Slack, Teams and email, finds things you promised
              (&ldquo;I&apos;ll&rdquo;, &ldquo;will do&rdquo;) and messages waiting for a reply, then fits them around
              tomorrow&apos;s meetings together with a workout and meals.
            </p>
            <button className="primary" onClick={() => start()}>
              Plan tomorrow
            </button>
          </section>
        )}
        {plan && !ready && (
          <section className={`sheet status ${plan.status}`}>
            {plan.status !== "failed" && <span className="spinner" aria-hidden="true" />}
            <span>{STATUS_TEXT[plan.status]}</span>
            {plan.error && <div className="error small">{plan.error}</div>}
          </section>
        )}

        {ready && (
          <div className="plan-body">
            <section className="sheet timeline-card">
              <p className="muted small">Drag to reschedule. Meetings come from your calendar and stay put.</p>
              <Timeline
                items={items}
                onMove={(item, s) => patch(item, { start: s })}
                onStatus={(item, status) => patch(item, { status })}
              />
            </section>
            <aside>
              <section className="sheet">
                <h3>Needs a decision ({inbox.length})</h3>
                {inbox.length === 0 && (
                  <p className="muted small">Nothing uncertain. Clear promises are already in the plan.</p>
                )}
                {inbox.map((i) => (
                  <div key={i.id} className="side-item">
                    <div>
                      <b>{i.title}</b>
                      <div className="muted small">&ldquo;{i.details}&rdquo;</div>
                    </div>
                    <div className="row">
                      <button className="primary" onClick={() => patch(i, { status: "proposed" })}>
                        Schedule
                      </button>
                      <button onClick={() => patch(i, { status: "removed" })}>Dismiss</button>
                    </div>
                  </div>
                ))}
              </section>
              {unscheduled.length > 0 && (
                <section className="sheet">
                  <h3>No room tomorrow ({unscheduled.length})</h3>
                  {unscheduled.map((i) => (
                    <div key={i.id} className="side-item">
                      <b>{i.title}</b>
                      <div className="muted small">{i.reason}</div>
                    </div>
                  ))}
                </section>
              )}
              <ChatPanel messages={plan!.messages} onSend={send} disabled={!ready} />
              {removed.length > 0 && (
                <section className="sheet">
                  <h3>Removed ({removed.length})</h3>
                  {removed.map((i) => (
                    <div key={i.id} className="side-item">
                      <span>
                        {i.title} {i.start && <span className="muted small fig">{hhmm(i.start)}</span>}
                      </span>
                      <button onClick={() => patch(i, { status: "proposed" })}>Restore</button>
                    </div>
                  ))}
                </section>
              )}
            </aside>
          </div>
        )}

        {past.length > 0 && (
          <section className="past">
            <h2>Past days</h2>
            <ol className="list">
              {past.map((h) => (
                <li key={h.id} className="row-item">
                  <span className="when fig">{h.date.slice(5)}</span>
                  <span className="what">
                    <Link href={`/review?plan=${h.id}`}>{longDate(h.date)}</Link>
                  </span>
                  <span className="muted small">
                    {h.done} of {h.planned} done
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </main>
    </>
  );
}
