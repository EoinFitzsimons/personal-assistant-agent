import { PlanItem } from "@/lib/api";

type Props = {
  item: PlanItem;
  onOutcome: (item: PlanItem, outcome: PlanItem["outcome"]) => void;
  large?: boolean;
};

export default function Outcome({ item, onOutcome, large }: Props) {
  if (item.outcome) {
    return (
      <span className="outcome">
        {item.outcome === "done" ? <span className="stamp">Done</span> : <span className="skipped-label">Skipped</span>}
        <button className="quiet" onClick={() => onOutcome(item, "")}>
          Undo
        </button>
      </span>
    );
  }
  return (
    <span className={large ? "outcome large" : "outcome"}>
      <button className="primary" onClick={() => onOutcome(item, "done")}>
        Done
      </button>
      <button onClick={() => onOutcome(item, "skipped")}>Skip</button>
    </span>
  );
}
