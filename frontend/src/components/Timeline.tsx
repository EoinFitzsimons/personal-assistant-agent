"use client";

import { DragEvent, useState } from "react";
import { PlanItem } from "@/lib/api";
import { hhmm, KIND_LABEL, minutesOf } from "@/lib/labels";

const START_HOUR = 6;
const END_HOUR = 23;
const PX_PER_MIN = 1.3;
const SNAP = 15;

type Props = {
  items: PlanItem[];
  onMove: (item: PlanItem, start: string) => void;
  onStatus: (item: PlanItem, status: "approved" | "removed" | "proposed") => void;
};

export default function Timeline({ items, onMove, onStatus }: Props) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [ghost, setGhost] = useState<number | null>(null);
  const timed = items.filter((i) => i.start && i.end && !["removed", "inbox", "unscheduled"].includes(i.status));
  const height = (END_HOUR - START_HOUR) * 60 * PX_PER_MIN;

  function minuteAt(e: DragEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const raw = (e.clientY - rect.top) / PX_PER_MIN + START_HOUR * 60;
    return Math.max(START_HOUR * 60, Math.min(END_HOUR * 60 - SNAP, Math.round(raw / SNAP) * SNAP));
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const item = items.find((i) => i.id === dragId);
    setDragId(null);
    setGhost(null);
    if (!item) return;
    const m = minuteAt(e);
    onMove(item, `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
  }

  return (
    <div className="timeline" style={{ height }}>
      {Array.from({ length: END_HOUR - START_HOUR }, (_, i) => (
        <div key={i} className="hour" style={{ top: i * 60 * PX_PER_MIN }}>
          <span>{String(START_HOUR + i).padStart(2, "0")}:00</span>
        </div>
      ))}
      <div
        className="lane"
        onDragOver={(e) => {
          e.preventDefault();
          setGhost(minuteAt(e));
        }}
        onDragLeave={() => setGhost(null)}
        onDrop={onDrop}
      >
        {ghost !== null && dragId !== null && (
          <div
            className="ghost"
            style={{
              top: (ghost - START_HOUR * 60) * PX_PER_MIN,
              height: (items.find((i) => i.id === dragId)?.duration_min ?? 30) * PX_PER_MIN,
            }}
          >
            {String(Math.floor(ghost / 60)).padStart(2, "0")}:{String(ghost % 60).padStart(2, "0")}
          </div>
        )}
        {timed.map((item) => {
          const top = (minutesOf(item.start!) - START_HOUR * 60) * PX_PER_MIN;
          const h = Math.max(22, (minutesOf(item.end!) - minutesOf(item.start!)) * PX_PER_MIN);
          const movable = item.kind !== "meeting";
          return (
            <div
              key={item.id}
              data-testid={`item-${item.id}`}
              className={`block ${item.kind} ${item.status} ${h < 45 ? "compact" : ""}`}
              style={{ top, height: h }}
              draggable={movable}
              onDragStart={(e) => {
                setDragId(item.id);
                e.dataTransfer.effectAllowed = "move";
              }}
              onDragEnd={() => {
                setDragId(null);
                setGhost(null);
              }}
              title={item.reason}
            >
              <div className="block-head">
                <span className="time">
                  {hhmm(item.start)} <span className="dur">{item.duration_min} min</span>
                </span>
                <span className="kind">{KIND_LABEL[item.kind]}</span>
                {h < 45 && item.source_link && (
                  <a href={item.source_link} target="_blank" rel="noreferrer" title={item.reason}>
                    source
                  </a>
                )}
                {item.fixed && item.kind !== "meeting" && <span className="pin">Pinned</span>}
                {item.status === "approved" && item.kind !== "meeting" && <span className="tick">Kept</span>}
                {item.outcome === "done" && <span className="stamp">Done</span>}
                {movable && (
                  <span className="btns">
                    {item.status !== "approved" && (
                      <button title="Keep this in the plan" onClick={() => onStatus(item, "approved")}>
                        Keep
                      </button>
                    )}
                    <button title="Remove" onClick={() => onStatus(item, "removed")}>
                      Remove
                    </button>
                  </span>
                )}
              </div>
              <div className="block-title">{item.title}</div>
              {h >= 72 && (
                <div className="block-reason">
                  {item.reason}
                  {item.source_link && (
                    <>
                      {" "}
                      <a href={item.source_link} target="_blank" rel="noreferrer">
                        source
                      </a>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
