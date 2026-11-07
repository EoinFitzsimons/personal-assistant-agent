import { PlanItem } from "@/lib/api";

export const KIND_LABEL: Record<PlanItem["kind"], string> = {
  meeting: "Meeting",
  task: "Task",
  commitment: "Your promise",
  follow_up: "Reply owed",
  workout: "Workout",
  meal: "Meal",
};

export const STATUS_LABEL: Record<PlanItem["status"], string> = {
  proposed: "Suggested",
  approved: "Kept",
  removed: "Removed",
  inbox: "Needs a decision",
  unscheduled: "No room",
};

export function hhmm(iso: string | null) {
  return iso ? iso.slice(11, 16) : "";
}

export function minutesOf(iso: string) {
  const [h, m] = iso.slice(11, 16).split(":").map(Number);
  return h * 60 + m;
}

function isoDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function offsetMinutes(iso: string) {
  const m = iso.match(/([+-])(\d{2}):(\d{2})$/);
  return m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0;
}

export function clockAt(offsetMin: number, timestamp: number) {
  const d = new Date(timestamp + offsetMin * 60_000);
  return { date: d.toISOString().slice(0, 10), minutes: d.getUTCHours() * 60 + d.getUTCMinutes() };
}

export function isToday(date: string) {
  return date === isoDate(new Date());
}

export function dayLabel(date: string) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (isToday(date)) return "Today";
  if (date === isoDate(tomorrow)) return "Tomorrow";
  return new Date(date + "T12:00:00").toLocaleDateString(undefined, { weekday: "long" });
}

export function longDate(date: string) {
  return new Date(date + "T12:00:00").toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

export function timed(items: PlanItem[]) {
  return items
    .filter((i) => i.start && i.end && !["removed", "inbox", "unscheduled"].includes(i.status))
    .sort((a, b) => a.start!.localeCompare(b.start!));
}
