"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ItemRow from "@/components/ItemRow";
import Nav from "@/components/Nav";
import Outcome from "@/components/Outcome";
import Skeleton from "@/components/Skeleton";
import { usePlanLoader } from "@/components/usePlanLoader";
import { api, focusPlan, patchItem, Plan, PlanItem } from "@/lib/api";
import { dayLabel, hhmm, isToday, KIND_LABEL, longDate, minutesOf, timed } from "@/lib/labels";

function nowMinutes() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

export default function TodayPage() {
  const router = useRouter();
  const { plan, setPlan, loaded, error, setError } = usePlanLoader(focusPlan);
  const [now, setNow] = useState(nowMinutes);

  useEffect(() => {
    const t = setInterval(() => setNow(nowMinutes()), 60_000);
    return () => clearInterval(t);
  }, []);

  async function outcome(item: PlanItem, value: PlanItem["outcome"]) {
    try {
      setPlan(await patchItem(plan!.id, item.id, { outcome: value }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function planTomorrow() {
    try {
      await api<Plan>("/plans", { method: "POST" });
      router.push("/plan");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const ready = plan?.status === "ready";
  const today = plan ? isToday(plan.date) : false;
  const live = today ? now : -1;
  const blocks = plan ? timed(plan.items) : [];
  const upcoming = blocks.filter((i) => minutesOf(i.end!) > live && (i.kind === "meeting" || !i.outcome));
  const earlier = blocks.filter((i) => !upcoming.includes(i));
  const focus = upcoming[0];
  const later = upcoming.slice(1);
  const work = blocks.filter((i) => i.kind !== "meeting");
  const done = work.filter((i) => i.outcome === "done").length;

  return (
    <>
      <Nav />
      <main className="page today">
        <header className="day-head">
          <h1>{plan ? dayLabel(plan.date) : "Today"}</h1>
          {plan && (
            <p className="muted">
              {longDate(plan.date)}
              {ready && work.length > 0 && `, ${done} of ${work.length} done`}
            </p>
          )}
        </header>
        {error && <p className="error">{error}</p>}
        {!loaded && <Skeleton />}

        {loaded && !plan && (
          <section className="sheet empty">
            <h2>Nothing planned yet</h2>
            <p className="muted">
              Plan tomorrow from your messages, calendar and health data. It takes about a minute.
            </p>
            <button className="primary" onClick={planTomorrow}>
              Plan tomorrow
            </button>
          </section>
        )}

        {plan && !ready && (
          <section className="sheet empty">
            <h2>{plan.status === "failed" ? "Planning failed" : "Your plan is being prepared"}</h2>
            <p className="muted">
              Follow it in <Link href="/plan">Week</Link>.
            </p>
          </section>
        )}

        {ready && (
          <>
            {!today && (
              <p className="note">
                This is tomorrow. Tick blocks off as you go, or adjust the plan in <Link href="/plan">Week</Link>.
              </p>
            )}
            {focus ? (
              <article className={`now sheet ${focus.kind}`}>
                <p className="now-when">
                  <span className="fig">{hhmm(focus.start)}</span>
                  {live >= minutesOf(focus.start!) ? "Now" : "Next"}, {focus.duration_min} min
                </p>
                <h2>{focus.title}</h2>
                <p className="muted">{focus.reason || KIND_LABEL[focus.kind]}</p>
                {focus.source_link && (
                  <a href={focus.source_link} target="_blank" rel="noreferrer">
                    Open the message
                  </a>
                )}
                {focus.kind !== "meeting" && <Outcome item={focus} onOutcome={outcome} large />}
              </article>
            ) : (
              <article className="now sheet">
                <h2>That&apos;s the day.</h2>
                <p className="muted">
                  Everything is done or past. <Link href="/review">Wrap up the day</Link>.
                </p>
              </article>
            )}

            {later.length > 0 && (
              <section>
                <h3 className="list-head">Later</h3>
                <ol className="list">
                  {later.map((i) => (
                    <ItemRow key={i.id} item={i} onOutcome={outcome} />
                  ))}
                </ol>
              </section>
            )}

            {earlier.length > 0 && (
              <details className="earlier">
                <summary>Earlier ({earlier.length})</summary>
                <ol className="list">
                  {earlier.map((i) => (
                    <ItemRow key={i.id} item={i} onOutcome={outcome} />
                  ))}
                </ol>
              </details>
            )}
          </>
        )}
      </main>
    </>
  );
}
