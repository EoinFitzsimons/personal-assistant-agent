"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import Nav from "@/components/Nav";
import Timeline, { hhmm } from "@/components/Timeline";
import { api, ChatMessage, getToken, Plan, PlanItem } from "@/lib/api";

const STATUS_TEXT: Record<string, string> = {
  gathering: "Gathering messages, emails, calendar and health data…",
  planning: "Prioritising and building your plan…",
  failed: "Planning failed",
};

export default function PlanPage() {
  const router = useRouter();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

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

  const start = () => run(async () => setPlan(await api<Plan>("/plans", { method: "POST" })));
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
  const health = plan?.summary.health ?? {};
  const counts = plan?.summary.counts ?? {};

  return (
    <>
      <Nav />
      <main className="page plan">
        <div className="plan-head">
          <div>
            <h1>{plan ? `Plan for ${new Date(plan.date + "T12:00:00").toDateString()}` : "Plan tomorrow"}</h1>
            {ready && (
              <p className="muted small">
                From {(plan!.summary.sources ?? []).join(", ")}: {counts.messages ?? 0} messages, {counts.emails ?? 0}{" "}
                emails, {counts.meetings ?? 0} meetings · {counts.commitments ?? 0} commitments,{" "}
                {counts.follow_ups ?? 0} follow-ups detected
                {health.sleep_hours !== undefined && ` · sleep ${health.sleep_hours}h`}
                {health.readiness !== undefined && ` · readiness ${health.readiness}`}
              </p>
            )}
          </div>
          <div className="head-actions">
            {ready && proposed > 0 && (
              <button onClick={approveAll}>Approve all ({proposed})</button>
            )}
            <button className="primary" onClick={start} disabled={plan?.status === "gathering" || plan?.status === "planning"}>
              {plan ? "Re-plan tomorrow" : "Plan tomorrow"}
            </button>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        {plan?.summary.errors?.length ? (
          <div className="banner warn">Some sources failed: {plan.summary.errors.join("; ")}</div>
        ) : null}

        {!loaded && <p>Loading…</p>}
        {loaded && !plan && (
          <div className="card empty">
            <h2>Ready when you are</h2>
            <p className="muted">
              The assistant reads the last 48h of Slack, Teams and email, finds things you promised (&ldquo;I&apos;ll…&rdquo;,
              &ldquo;will do&rdquo;) and messages waiting for a reply, then fits them around tomorrow&apos;s meetings
              together with a workout and meals.
            </p>
            <button className="primary" onClick={start}>
              Plan tomorrow
            </button>
          </div>
        )}
        {plan && !ready && (
          <div className={`card status ${plan.status}`}>
            {plan.status !== "failed" && <span className="spinner" />}
            {STATUS_TEXT[plan.status]}
            {plan.error && <div className="error small">{plan.error}</div>}
          </div>
        )}

        {ready && (
          <div className="plan-body">
            <div className="card timeline-card">
              <p className="muted small">Drag items to reschedule. Meetings come from your calendar and stay fixed.</p>
              <Timeline
                items={items}
                onMove={(item, s) => patch(item, { start: s })}
                onStatus={(item, status) => patch(item, { status })}
              />
            </div>
            <aside>
              <div className="card">
                <h3>Detected commitments inbox ({inbox.length})</h3>
                {inbox.length === 0 && <p className="muted small">Nothing uncertain. Clear commitments are already in the plan.</p>}
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
              </div>
              {unscheduled.length > 0 && (
                <div className="card">
                  <h3>Didn&apos;t fit tomorrow ({unscheduled.length})</h3>
                  {unscheduled.map((i) => (
                    <div key={i.id} className="side-item">
                      <b>{i.title}</b>
                      <div className="muted small">{i.reason}</div>
                    </div>
                  ))}
                </div>
              )}
              <ChatPanel messages={plan!.messages} onSend={send} disabled={!ready} />
              {removed.length > 0 && (
                <div className="card">
                  <h3>Removed ({removed.length})</h3>
                  {removed.map((i) => (
                    <div key={i.id} className="side-item">
                      <span>
                        {i.title} {i.start && <span className="muted small">({hhmm(i.start)})</span>}
                      </span>
                      <button onClick={() => patch(i, { status: "proposed" })}>Restore</button>
                    </div>
                  ))}
                </div>
              )}
            </aside>
          </div>
        )}
      </main>
    </>
  );
}
