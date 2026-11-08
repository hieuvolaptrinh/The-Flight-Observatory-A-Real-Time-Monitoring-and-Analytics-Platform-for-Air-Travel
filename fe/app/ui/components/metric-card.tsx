import { IconName } from "../flight-types";
import { Icon } from "./icons";

export function Metric({
  title,
  value,
  unit,
  icon,
  note,
  color = "teal",
}: {
  title: string;
  value: string;
  unit?: string;
  icon: IconName;
  note: string;
  color?: "teal" | "coral" | "blue" | "purple";
}) {
  return (
    <article className="metric">
      <div className="metric-body">
        <span className="metric-label">{title}</span>
        <div className="metric-value">
          {value}
          {unit && <span>{unit}</span>}
        </div>
        <div className="metric-note">{note}</div>
      </div>
      <span className={`metric-icon ${color}`}>
        <Icon name={icon} size={20} />
      </span>
    </article>
  );
}
