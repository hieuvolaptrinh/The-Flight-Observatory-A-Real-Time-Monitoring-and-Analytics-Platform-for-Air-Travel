import { type HourlyFlightStat, number } from "../flight-types";

export function TrendChart({ hourly }: { hourly: HourlyFlightStat[] }) {
  if (!hourly.length) return <p className="analytics-empty">Chưa có chuyến bay trong khoảng ngày này.</p>;

  const x = (hour: number) => 60 + (520 * hour) / 23;
  const y = (fraction: number) => 190 - 160 * fraction;
  const countStep = Math.max(1, Math.ceil(Math.max(...hourly.map(row => row.flights)) / 4));
  const countMax = countStep * 4;
  const points = hourly.filter(row => row.known > 0).map(row => ({
    ...row,
    rate: row.delayed / row.known,
  }));
  const hourLabel = (hour: number) => String(hour).padStart(2, "0") + ":00";

  return (
    <div className="trend-chart">
      <div className="hourly-chart-legend" aria-hidden="true">
        <span><i className="hourly-volume-key" /> Số chuyến</span>
        <span><i className="hourly-delay-key" /> Tỷ lệ trễ</span>
      </div>
      <svg viewBox="0 0 640 225" role="img" aria-label="Số chuyến và tỷ lệ trễ theo giờ khởi hành">
        <text x="5" y="14">Chuyến</text>
        <text x="635" y="14" textAnchor="end">Tỷ lệ trễ</text>
        {[0, 1, 2, 3, 4].map(tick => {
          const tickY = y(tick / 4);
          return (
            <g key={tick}>
              <line x1="48" x2="592" y1={tickY} y2={tickY} stroke="#e5e7eb" strokeDasharray="4 5" />
              <text x="43" y={tickY + 4} textAnchor="end">{number(tick * countStep)}</text>
              <text x="598" y={tickY + 4}>{tick * 25}%</text>
            </g>
          );
        })}
        {hourly.map(row => {
          const barY = y(row.flights / countMax);
          return (
            <rect key={row.hour} x={x(row.hour) - 7} y={barY} width="14" height={y(0) - barY}
              rx="2" className="hourly-volume-bar">
              <title>{`${hourLabel(row.hour)} · ${number(row.flights)} chuyến · ${number(row.known)} chuyến biết độ trễ`}</title>
            </rect>
          );
        })}
        {points.map((point, index) => {
          const previous = points[index - 1];
          return (
            <g key={point.hour}>
              {previous?.hour === point.hour - 1 && (
                <line x1={x(previous.hour)} y1={y(previous.rate)} x2={x(point.hour)} y2={y(point.rate)}
                  className="hourly-delay-line" strokeWidth="2.8" />
              )}
              <circle cx={x(point.hour)} cy={y(point.rate)} r="4" className="hourly-delay-point">
                <title>{`${hourLabel(point.hour)} · ${(point.rate * 100).toFixed(1)}% (${point.delayed}/${point.known} chuyến biết độ trễ)`}</title>
              </circle>
            </g>
          );
        })}
        {[0, 4, 8, 12, 16, 20, 23].map(hour => (
          <text key={hour} x={x(hour)} y="215" textAnchor="middle">
            {hourLabel(hour)}
          </text>
        ))}
      </svg>
      <p className="analytics-status">Tỷ lệ trễ tính trên các chuyến đã biết độ trễ.</p>
    </div>
  );
}
