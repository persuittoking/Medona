import { Line, LineChart, Tooltip, YAxis } from "recharts";
import type { Hit } from "../api/types";

const COLOR: Record<string, string> = { red: "#DC2626", yellow: "#D97706" };

/** Tiny line of the values a trend rule used (e.g. 3 checkups), with ↗ / ↘. Renders nothing without a series. */
export function TrendSpark({ hit }: { hit: Hit }) {
  const values = hit.values ?? [];
  if (values.length < 2) return null;
  const data = values.map((v, i) => ({ i, v, w: hit.weeks?.[i] }));
  const color = COLOR[hit.zone] ?? "#475569";
  const arrow = hit.direction === "down" ? "↘" : "↗";
  return (
    <span className="inline-flex shrink-0 items-center gap-1" title={`${values.join(" → ")} ${hit.unit ?? ""}`}>
      <LineChart width={72} height={24} data={data} margin={{ top: 3, bottom: 3, left: 2, right: 2 }}>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Tooltip
          cursor={false}
          wrapperStyle={{ fontSize: 11 }}
          formatter={(v: number) => [`${v} ${hit.unit ?? ""}`, ""]}
          labelFormatter={(_, p) => (p?.[0]?.payload?.w != null ? `${p[0].payload.w} hafta` : "")}
        />
        <Line dataKey="v" stroke={color} strokeWidth={2} dot={{ r: 2, fill: color }} isAnimationActive={false} />
      </LineChart>
      <span aria-label={hit.direction === "down" ? "pasaymoqda" : "oshmoqda"} className="text-base font-bold leading-none" style={{ color }}>
        {arrow}
      </span>
    </span>
  );
}
