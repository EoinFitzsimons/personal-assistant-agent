"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import ItemRow from "@/components/ItemRow";
import Nav from "@/components/Nav";
import Skeleton from "@/components/Skeleton";
import { usePlanLoader } from "@/components/usePlanLoader";
import { api, focusPlan, getToken, patchItem, Plan, PlanItem, PlanSummary } from "@/lib/api";
import { longDate, timed } from "@/lib/labels";

function ReviewBody({ planId }: { planId: string | null }) {
  const load = useCallback(() => (planId ? api<Plan>(`/plans/${planId}`) : focusPlan()), [planId]);
  const { plan, setPlan, loaded, error, setError } = usePlanLoader(load);
  const [history, setHistory] = useState<PlanSummary[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    api<PlanSummary[]>("/plans")
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [plan]);

  async function outcome(item: PlanItem, value: PlanItem["outcome"]) {
    try {
      setPlan(await patchItem(plan!.id, item.id, { outcome: value }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveNote() {
    try {
      const p = await api<Plan>(`/plans/${plan!.id}/review`, { method: "POST", body: JSON.stringify({ note: note ?? "" }) });
      setPlan(p);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const ready = plan?.status === "ready";
  const work = plan ? timed(plan.items).filter((i) => i.kind !== "meeting") : [];
  const open = work.filter((i) => !i.outcome);
  const done = work.filter((i) => i.outcome === "done");
  const skipped = work.filter((i) => i.outcome === "skipped");
  const promisesOpen = plan
    ? plan.items.filter((i) => (i.kind === "commitment" || i.kind === "follow_up") && i.status !== "removed" && i.outcome !== "done").length
    : 0;
  const past = history.filter((h) => h.id !== plan?.id && h.status === "ready");

  function section(title: string, items: PlanItem[]) {
    if (items.length === 0) return null;
    return (
      <section>
        <h3 className="list-head">{title}</h3>
        <ol className="list">
          {items.map((i) => (
            <ItemRow key={i.id} item={i} onOutcome={outcome} />
          ))}
        </ol>
      </section>
    );
  }

  return (
    <main className="page narrow">
      <h1>Review</h1>
      {plan && <p className="muted">{longDate(plan.date)}</p>}
      {error && <p className="error">{error}</p>}
      {!loaded && <Skeleton />}
      {loaded && !ready && (
        <section className="sheet empty">
          <h2>Nothing to review yet</h2>
          <p className="muted">
            Plan a day in <Link href="/plan">Week</Link>, then come back here at the end of it.
          </p>
        </section>
      )}
      {ready && (
        <>
          <dl className="tally">
            <div>
              <dt>Done</dt>
              <dd>{done.length}</dd>
            </div>
            <div>
              <dt>Skipped</dt>
              <dd>{skipped.length}</dd>
            </div>
            <div>
              <dt>Not marked</dt>
              <dd>{open.length}</dd>
            </div>
          </dl>
          {promisesOpen > 0 && (
            <p className="note">
              {promisesOpen} {promisesOpen === 1 ? "promise is" : "promises are"} still open.{" "}
              <Link href="/promises">See promises</Link>
            </p>
          )}
          {section("Not marked yet", open)}
          {section("Done", done)}
          {section("Skipped", skipped)}
          <section className="sheet review-note">
            <label>
              One line about the day
              <textarea
                rows={2}
                value={note ?? plan.review_note}
                onChange={(e) => {
                  setNote(e.target.value);
                  setSaved(false);
                }}
                placeholder="Deep work before 11 went well. Meetings ran over."
              />
            </label>
            <div className="row">
              <button className="primary" onClick={saveNote}>
                Save note
              </button>
              {saved && <span className="ok">Saved.</span>}
            </div>
          </section>
        </>
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
  );
}

function ReviewInner() {
  const planId = useSearchParams().get("plan");
  return <ReviewBody key={planId ?? "focus"} planId={planId} />;
}

export default function ReviewPage() {
  return (
    <>
      <Nav />
      <Suspense>
        <ReviewInner />
      </Suspense>
    </>
  );
}
