"use client";

import { useState } from "react";
import { type HourlyFlightStat, number } from "../flight-types";

const hours = Array.from({ length: 24 }, (_, hour) => hour);
const hourLabel = (hour: number) => String(hour).padStart(2, "0") + ":00";
const rateLabel = (row?: HourlyFlightStat) =>
  row?.known ? `${(100 * row.delayed / row.known).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%` : "Chưa có số liệu";

function delayLevel(row?: HourlyFlightStat) {
  if (!row?.known) return "unknown";
  const rate = row.delayed / row.known;
  return rate < 0.25 ? "low" : rate < 0.5 ? "mid" : "high";
}

export function TrendChart({ hourly }: { hourly: HourlyFlightStat[] }) {
  const [selectedHour, setSelectedHour] = useState<number>();
  const [hoveredHour, setHoveredHour] = useState<number>();
  if (!hourly.length) return <p className="analytics-empty">Chưa có chuyến bay trong khoảng ngày này.</p>;

  const rows = new Map(hourly.map(row => [row.hour, row]));
  const peak = hourly.reduce((busiest, row) => row.flights > busiest.flights ? row : busiest);
  const step = Math.max(1, Math.ceil(peak.flights / 4));
  const max = step * 4;
  const active = hoveredHour ?? selectedHour ?? peak.hour;
  const detail = rows.get(active);

  return (
    <div className="hourly-profile">
      <div className="hourly-profile-detail">
        <div><span>Giờ khởi hành</span><strong>{hourLabel(active)}</strong></div>
        <div><span>Số chuyến</span><strong>{number(detail?.flights ?? 0)}</strong></div>
        <div><span>Tỷ lệ trễ</span><strong>{rateLabel(detail)}</strong></div>
        <div><span>Số chuyến biết độ trễ</span><strong>{number(detail?.known ?? 0)}</strong></div>
      </div>
      <div className="hourly-profile-scroll">
        <div className="hourly-profile-plot">
          <div className="hourly-profile-axis" aria-hidden="true">
            <strong>Chuyến</strong>
            <div className="hourly-profile-ticks">
              {[4, 3, 2, 1, 0].map(tick => <span key={tick}>{number(tick * step)}</span>)}
            </div>
            <strong>Tỷ lệ trễ</strong>
          </div>
          <div className="hourly-profile-hours" role="group" aria-label="Chọn giờ khởi hành">
            {hours.map(hour => {
              const row = rows.get(hour);
              return (
                <button key={hour} type="button" className={hour === active ? "hourly-slot is-active" : "hourly-slot"}
                  aria-label={`${hourLabel(hour)} · ${number(row?.flights ?? 0)} chuyến · ${rateLabel(row)}`}
                  aria-pressed={hour === (selectedHour ?? peak.hour)}
                  onMouseEnter={() => setHoveredHour(hour)}
                  onMouseLeave={() => setHoveredHour(undefined)}
                  onFocus={() => setHoveredHour(hour)}
                  onBlur={() => setHoveredHour(undefined)}
                  onClick={() => setSelectedHour(hour)}>
                  <span className="hourly-slot-volume" aria-hidden="true">
                    <span style={{ height: `${100 * (row?.flights ?? 0) / max}%` }} />
                  </span>
                  <span className={`hourly-delay-cell hourly-delay-${delayLevel(row)}`} aria-hidden="true" />
                  <span className="hourly-slot-time" aria-hidden="true">{hour % 4 === 0 || hour === 23 ? hourLabel(hour) : ""}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <ul className="hourly-profile-legend" aria-label="Màu theo tỷ lệ chuyến trễ">
        <li><i className="hourly-delay-low" /> Dưới 25%</li>
        <li><i className="hourly-delay-mid" /> 25–dưới 50%</li>
        <li><i className="hourly-delay-high" /> Từ 50%</li>
        <li><i className="hourly-delay-unknown" /> Chưa có số liệu</li>
      </ul>
    </div>
  );
}
