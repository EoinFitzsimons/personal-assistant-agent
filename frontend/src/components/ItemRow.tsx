import { ReactNode } from "react";
import Outcome from "@/components/Outcome";
import { PlanItem } from "@/lib/api";
import { hhmm, KIND_LABEL } from "@/lib/labels";

type Props = {
  item: PlanItem;
  when?: ReactNode;
  onOutcome?: (item: PlanItem, outcome: PlanItem["outcome"]) => void;
  children?: ReactNode;
};

export default function ItemRow({ item, when, onOutcome, children }: Props) {
  const who = item.owed_to ? (item.kind === "follow_up" ? `, from ${item.owed_to}` : `, for ${item.owed_to}`) : "";
  return (
    <li className={`row-item ${item.kind} ${item.outcome}`}>
      <span className="when">{when ?? <span className="fig">{hhmm(item.start)}</span>}</span>
      <div className="what">
        <span className="title">{item.title}</span>
        <span className="muted small">
          {KIND_LABEL[item.kind]}
          {who}
          {item.source_link && (
            <>
              {" "}
              <a href={item.source_link} target="_blank" rel="noreferrer">
                source
              </a>
            </>
          )}
        </span>
      </div>
      <div className="acts">
        {children ?? (onOutcome && item.kind !== "meeting" && <Outcome item={item} onOutcome={onOutcome} />)}
      </div>
    </li>
  );
}
