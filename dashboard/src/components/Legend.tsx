import { colorVar, prettyLabel } from "../colors";

export default function Legend({ labels }: { labels: string[] }) {
  return (
    <div className="legend">
      {labels.map((label) => (
        <span className="item" key={label}>
          <span className="swatch" style={{ background: colorVar(label) }} aria-hidden />
          {prettyLabel(label)}
        </span>
      ))}
    </div>
  );
}
