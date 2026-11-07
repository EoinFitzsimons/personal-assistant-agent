"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import ItemRow from "@/components/ItemRow";
import Nav from "@/components/Nav";
import Skeleton from "@/components/Skeleton";
import { usePlanLoader } from "@/components/usePlanLoader";
import { api, focusPlan, getToken, patchItem, Plan, PlanItem, PlanSummary } from "@/lib/api";
import { longDate, timed } from "@/lib/labels";

type Show = "done" | "skipped" | "open";
const SHOWS: Show[] = ["done", "skipped", "open"];

type BodyProps = { planId: string | null; show: Show | null; onShow: (show: Show | null) => void };

function ReviewBody({ planId, show, onShow }: BodyProps) {
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

  function section(key: Show, title: string, items: PlanItem[]) {
    if (show && show !== key) return null;
    if (items.length === 0) {
      return show ? <p className="muted section-empty">Nothing {key === "open" ? "left to mark" : key} yet.</p> : null;
    }
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
          <div className="tally" role="group" aria-label="Show blocks by outcome">
            {(
              [
                ["done", "Done", done.length],
                ["skipped", "Skipped", skipped.length],
                ["open", "Not marked", open.length],
              ] as const
            ).map(([key, label, count]) => (
              <button key={key} aria-pressed={show === key} onClick={() => onShow(show === key ? null : key)}>
                <span className="tally-label">{label}</span>
                <span className="tally-count fig">{count}</span>
              </button>
            ))}
          </div>
          {show && (
            <p className="muted small">
              Showing {show === "open" ? "not marked" : show} blocks.{" "}
              <button className="quiet" onClick={() => onShow(null)}>
                Show all
              </button>
            </p>
          )}
          {promisesOpen > 0 && (
            <p className="note">
              {promisesOpen} {promisesOpen === 1 ? "promise is" : "promises are"} still open.{" "}
              <Link href="/promises">See promises</Link>
            </p>
          )}
          {section("open", "Not marked yet", open)}
          {section("done", "Done", done)}
          {section("skipped", "Skipped", skipped)}
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
  const params = useSearchParams();
  const router = useRouter();
  const planId = params.get("plan");
  const raw = params.get("show");
  const show = SHOWS.find((s) => s === raw) ?? null;

  function onShow(next: Show | null) {
    const q = new URLSearchParams(params.toString());
    if (next) q.set("show", next);
    else q.delete("show");
    const qs = q.toString();
    router.replace(qs ? `/review?${qs}` : "/review", { scroll: false });
  }

  return <ReviewBody key={planId ?? "focus"} planId={planId} show={show} onShow={onShow} />;
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
