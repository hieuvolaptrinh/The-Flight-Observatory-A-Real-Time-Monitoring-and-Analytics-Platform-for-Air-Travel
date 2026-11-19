import type { HourlyFlightStat } from "../flight-types";

export function TrendChart({ hourly }: { hourly: HourlyFlightStat[] }) {
  const points = hourly.filter(row => row.known > 0).map(row => ({
    ...row,
    x: 50 + row.hour * 24,
    y: 190 - 1.6 * (row.delayed * 100 / row.known),
  }));

  if (!points.length) return <p className="analytics-empty">Chưa có chuyến biết độ trễ trong ngày này.</p>;

  return (
    <div className="trend-chart">
      <svg viewBox="0 0 640 225" role="img" aria-label="Tỷ lệ chuyến bay trễ theo giờ khởi hành">
        {[0, 25, 50, 75, 100].map(pct => (
          <g key={pct}>
            <line x1="50" x2="602" y1={190 - pct * 1.6} y2={190 - pct * 1.6}
              stroke="#e5e7eb" strokeDasharray="4 5" />
            <text x="43" y={194 - pct * 1.6} textAnchor="end">{pct}%</text>
          </g>
        ))}
        {points.map((point, index) => {
          const previous = points[index - 1];
          const hour = String(point.hour).padStart(2, "0") + ":00";
          const rate = (point.delayed * 100 / point.known).toFixed(1);
          return (
            <g key={point.hour}>
              {previous?.hour === point.hour - 1 && (
                <line x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} stroke="#05c48c" strokeWidth="2.8" />
              )}
              <circle cx={point.x} cy={point.y} r="4" fill="#05c48c">
                <title>{hour} · {rate}% ({point.delayed}/{point.known} chuyến biết độ trễ)</title>
              </circle>
            </g>
          );
        })}
        {[0, 4, 8, 12, 16, 20, 23].map(hour => (
          <text key={hour} x={50 + hour * 24} y="215" textAnchor="middle">
            {String(hour).padStart(2, "0")}:00
          </text>
        ))}
      </svg>
    </div>
  );
}
