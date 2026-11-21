"use client";

import { HourlyFlightStat, flightDateRange, number } from "../flight-types";
import { Icon } from "../components/icons";
import { Metric } from "../components/metric-card";
import { IngestionOverview } from "../components/ingestion-overview";
import { TrendChart } from "../components/trend-chart";

interface OverviewViewProps {
  total: number;
  rate: number;
  delayed: number;
  avg: number;
  day: string | null;
  hourlyDateFrom: string | null;
  hourly: HourlyFlightStat[];
  onTime: number;
  unknown: number;

}

export function OverviewView({
  total,
  rate,
  delayed,
  avg,
  day,
  hourlyDateFrom,
  hourly,
  onTime,
  unknown,
}: OverviewViewProps) {
  const known = total - unknown;
  const onTimePct = known > 0 ? onTime * 100 / known : 0;
  return (
    <>
      <section className="metrics" aria-label="Chỉ số tổng quan">
        <Metric
          title="Chuyến bay khớp bộ lọc"
          value={number(total)}
          unit="chuyến"
          icon="plane"
          note="Từ dữ liệu chuyến bay đã lưu"
        />
        <Metric
          title="Tỷ lệ chuyến bay trễ"
          value={known > 0 ? rate.toFixed(1) : "—"}
          unit="%"
          icon="chart"
          note="Chuyến bay trễ từ 15 phút trở lên"
          color="coral"
        />
        <Metric
          title="Số chuyến bay trễ"
          value={number(delayed)}
          unit="chuyến"
          icon="clock"
          note="Tổng hợp trực tiếp từ PostgreSQL"
          color="blue"
        />
        <Metric
          title="Độ trễ trung bình"
          value={known > 0 ? avg.toFixed(1) : "—"}
          unit="phút"
          icon="clock"
          note="Trung bình các chuyến có số liệu trễ"
          color="purple"
        />
      </section>

      <div className="overview-charts">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Lưu lượng và tỷ lệ trễ theo giờ</h2>
              <p>{day ? `Giờ khởi hành địa phương · ${flightDateRange(hourlyDateFrom ?? day, day)}` : "Chọn bộ lọc có dữ liệu chuyến bay"}</p>
            </div>
          </div>
          <TrendChart hourly={hourly} />
        </section>

        <section className="panel donut-panel">
          <div className="panel-heading">
            <div>
              <h2>Tỷ trọng Trạng thái Chuyến bay</h2>
              <p>Tỷ lệ trong các chuyến biết độ trễ</p>
            </div>
          </div>
          <div
            className="donut"
            role="img"
            aria-label={known ? `${onTimePct.toFixed(1)}% đúng giờ, ${rate.toFixed(1)}% trễ` : "Chưa biết độ trễ"}
          >
            <svg viewBox="0 0 160 160" aria-hidden="true" className="donut-ring">
              <circle cx="80" cy="80" r="72.5" className={known ? "donut-track" : "donut-track is-empty"} />
              {onTimePct > 0 && <circle cx="80" cy="80" r="72.5" pathLength="100"
                strokeDasharray={`${onTimePct} 100`} className="donut-on-time" />}
            </svg>
            <div>
              <span>Đúng giờ</span>
              <strong>
                {known ? onTimePct.toFixed(1) : "—"}
                {known > 0 && <small>%</small>}
              </strong>
              <span className="donut-check">
                <Icon name="check" size={13} />
                Trực tiếp từ DB
              </span>
            </div>
          </div>
          <div className="donut-legend">
            <div>
              <i className="teal-bg" />
              <span>Đúng giờ (&lt; 15 phút)</span>
              <strong>{number(onTime)}</strong>
            </div>
            <div>
              <i className="donut-delay-key" />
              <span>Trễ chuyến (≥ 15 phút)</span>
              <strong>{number(delayed)}</strong>
            </div>
            <div>
              <span>Chưa biết độ trễ</span>
              <strong>{number(unknown)}</strong>
            </div>
          </div>
        </section>
      </div>

      <IngestionOverview />
    </>
  );
}
