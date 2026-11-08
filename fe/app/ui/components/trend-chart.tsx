"use client";

import { useState } from "react";

export function TrendChart({ rate, day }: { rate: number; day: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const baseRate = Math.max(5, rate || 18);
  const values = [12, 10, 13, 11, 15, 20, 17, 23, 18, 24, 29, 23, 26].map(v =>
    Math.min(39, (v * baseRate) / 21)
  );
  const points = values.map((v, i) => `${48 + i * 46},${190 - v * 3.7}`).join(" ");

  return (
    <div className="trend-chart">
      <svg viewBox="0 0 640 235" role="img" aria-label={`Tỷ lệ chuyến bay trễ theo giờ ngày ${day}`}>
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#05c48c" stopOpacity=".22" />
            <stop offset="100%" stopColor="#05c48c" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 10, 20, 30, 40].map(n => (
          <g key={n}>
            <line
              x1="48"
              x2="610"
              y1={190 - n * 3.7}
              y2={190 - n * 3.7}
              stroke="#e5e7eb"
              strokeDasharray="4 5"
            />
            <text x="32" y={194 - n * 3.7} textAnchor="end">
              {n}%
            </text>
          </g>
        ))}
        <polygon points={`48,190 ${points} 600,190`} fill="url(#area)" />
        <polyline points={points} fill="none" stroke="#05c48c" strokeWidth="2.8" strokeLinejoin="round" />
        {values.map((v, i) => (
          <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={30 + i * 46} y="30" width="40" height="165" fill="transparent" />
            {hover === i && (
              <>
                <line
                  x1={48 + i * 46}
                  x2={48 + i * 46}
                  y1="30"
                  y2="190"
                  stroke="#05c48c"
                  strokeDasharray="3 3"
                />
                <circle
                  cx={48 + i * 46}
                  cy={190 - v * 3.7}
                  r="5"
                  fill="#05c48c"
                  stroke="white"
                  strokeWidth="3"
                />
                <text
                  x={Math.min(575, Math.max(70, 48 + i * 46))}
                  y={175 - v * 3.7}
                  textAnchor="middle"
                  className="chart-tooltip"
                >
                  {v.toFixed(1)}%
                </text>
              </>
            )}
          </g>
        ))}
        {[0, 2, 4, 6, 8, 10, 12].map(i => (
          <text key={i} x={48 + i * 46} y="220" textAnchor="middle">
            {String(i * 2).padStart(2, "0")}:00
          </text>
        ))}
      </svg>
    </div>
  );
}
