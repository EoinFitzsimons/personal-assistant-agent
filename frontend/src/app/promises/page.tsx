"use client";

import Link from "next/link";
import ItemRow from "@/components/ItemRow";
import Nav from "@/components/Nav";
import Skeleton from "@/components/Skeleton";
import { usePlanLoader } from "@/components/usePlanLoader";
import { latestPlan, patchItem, PlanItem } from "@/lib/api";
import { dayLabel, hhmm, STATUS_LABEL } from "@/lib/labels";

export default function PromisesPage() {
  const { plan, setPlan, loaded, error, setError } = usePlanLoader(latestPlan);

  async function update(item: PlanItem, body: object) {
    try {
      setPlan(await patchItem(plan!.id, item.id, body));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const ready = plan?.status === "ready";
  const items = ready
    ? plan.items.filter((i) => (i.kind === "commitment" || i.kind === "follow_up") && i.status !== "removed")
    : [];
  const mine = items.filter((i) => i.kind === "commitment");
  const owed = items.filter((i) => i.kind === "follow_up");

  function when(i: PlanItem) {
    if (i.start && i.status !== "inbox" && i.status !== "unscheduled") {
      return (
        <>
          {dayLabel(plan!.date)} <span className="fig">{hhmm(i.start)}</span>
        </>
      );
    }
    return STATUS_LABEL[i.status];
  }

  function rows(list: PlanItem[], empty: string) {
    if (list.length === 0) return <p className="muted">{empty}</p>;
    return (
      <ol className="list">
        {list.map((i) => (
          <ItemRow key={i.id} item={i} when={when(i)} onOutcome={(item, outcome) => update(item, { outcome })}>
            {i.status === "inbox" ? (
              <>
                <button className="primary" onClick={() => update(i, { status: "proposed" })}>
                  Schedule
                </button>
                <button onClick={() => update(i, { status: "removed" })}>Dismiss</button>
              </>
            ) : undefined}
          </ItemRow>
        ))}
      </ol>
    );
  }

  return (
    <>
      <Nav />
      <main className="page narrow">
        <h1>Promises</h1>
        {ready && (
          <p className="muted">
            You said you&apos;d do {mine.length} {mine.length === 1 ? "thing" : "things"}. {owed.length}{" "}
            {owed.length === 1 ? "person is" : "people are"} waiting on your reply. Taken from the last 48 hours of
            messages and email.
          </p>
        )}
        {error && <p className="error">{error}</p>}
        {!loaded && <Skeleton />}
        {loaded && !ready && (
          <section className="sheet empty">
            <h2>No scan yet</h2>
            <p className="muted">
              Promises appear after you plan a day. Start one in <Link href="/plan">Week</Link>.
            </p>
          </section>
        )}
        {ready && (
          <>
            <h2 className="section-head">You said you&apos;d do these</h2>
            {rows(mine, "Nothing here. Promises show up when you write things like \u201cI\u2019ll send it\u201d or \u201cwill do\u201d.")}
            <h2 className="section-head">Waiting on your reply</h2>
            {rows(owed, "Nobody is waiting on you.")}
          </>
        )}
      </main>
    </>
  );
}
