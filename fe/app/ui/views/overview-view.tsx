"use client";

import Link from "next/link";
import { AirportStat, CarrierStat, number } from "../flight-types";
import { Icon } from "../components/icons";
import { Metric } from "../components/metric-card";
import { TrendChart } from "../components/trend-chart";

interface OverviewViewProps {
  total: number;
  rate: number;
  delayed: number;
  avg: number;
  day: string;
  selection: AirportStat[];
  carriers: CarrierStat[];
  rankBy: "airports" | "carriers";
  setRankBy: (val: "airports" | "carriers") => void;
}

export function OverviewView({
  total,
  rate,
  delayed,
  avg,
  day,
  selection,
  carriers,
  rankBy,
  setRankBy,
}: OverviewViewProps) {
  return (
    <>
      <section className="metrics" aria-label="Chỉ số tổng quan">
        <Metric
          title="Tổng chuyến bay trong DB"
          value={number(total)}
          unit="chuyến"
          icon="plane"
          note={`${selection.length} sân bay nổi bật đang theo dõi`}
        />
        <Metric
          title="Tỷ lệ chuyến bay trễ"
          value={rate.toFixed(1)}
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
          value={avg.toFixed(1)}
          unit="phút"
          icon="clock"
          note="Trung bình trên toàn bộ chuyến bay"
          color="purple"
        />
      </section>

      <div className="overview-charts">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Nhịp độ khai thác &amp; Tỷ lệ trễ theo khung giờ</h2>
              <p>Biến động tỷ lệ chuyến bay trễ trong ngày theo giờ địa phương</p>
            </div>
            <span className="legend">
              <i />
              Tỷ lệ trễ (%)
            </span>
          </div>
          <TrendChart rate={rate} day={day} />
        </section>

        <section className="panel donut-panel">
          <div className="panel-heading">
            <div>
              <h2>Tỷ trọng Trạng thái Chuyến bay</h2>
              <p>Tỷ lệ chuyến bay đúng giờ và chậm chuyến hiện tại</p>
            </div>
          </div>
          <div
            className="donut"
            style={{
              background: `conic-gradient(#059669 0 ${100 - rate}%, #d97706 ${100 - rate}% 100%)`,
            }}
            role="img"
            aria-label={`${(100 - rate).toFixed(1)}% đúng giờ, ${rate.toFixed(1)}% trễ`}
          >
            <div>
              <span>Đúng giờ</span>
              <strong>
                {(100 - rate).toFixed(1)}
                <small>%</small>
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
              <strong>{number(Math.max(0, total - delayed))}</strong>
            </div>
            <div>
              <i className="orange-bg" />
              <span>Trễ chuyến (≥ 15 phút)</span>
              <strong>{number(delayed)}</strong>
            </div>
          </div>
        </section>
      </div>

      <div className="bottom-grid">
        <section className="panel ranking-panel">
          <div className="panel-heading">
            <div>
              <h2>Điểm nóng chậm chuyến</h2>
              <p>Xếp hạng theo tỷ lệ trễ từ dữ liệu thực</p>
            </div>
            <div className="segmented">
              <button
                type="button"
                className={rankBy === "airports" ? "selected" : ""}
                onClick={() => setRankBy("airports")}
              >
                Sân bay
              </button>
              <button
                type="button"
                className={rankBy === "carriers" ? "selected" : ""}
                onClick={() => setRankBy("carriers")}
              >
                Hãng bay
              </button>
            </div>
          </div>
          <div className="ranking-list">
            {(rankBy === "airports" ? selection : carriers)
              .slice(0, 6)
              .map((a, i) => (
                <div className="ranking-row" key={a.code}>
                  <span className="rank-number">{String(i + 1).padStart(2, "0")}</span>
                  <div className="airport-code">{a.code}</div>
                  <div className="ranking-name">
                    <strong>{a.name}</strong>
                    <span>{a.flights} chuyến bay</span>
                  </div>
                  <div className="ranking-track">
                    <div style={{ width: `${Math.min(100, (a.rate / 50) * 100)}%` }} />
                  </div>
                  <strong className="rank-rate">
                    {a.rate.toFixed(1)}
                    <small>%</small>
                  </strong>
                </div>
              ))}
          </div>
        </section>

        <section className="tomorrow-card">
          <h2>Khám phá Bản đồ Radar &amp; Phân tích Chuyến bay</h2>
          <p>
            Theo dõi vị trí các chuyến bay theo thời gian thực kết hợp phân tích đặc trưng vận hành sân bay.
          </p>
          <div className="flight-illustration" aria-hidden="true">
            <span className="flight-code">RADAR MAP (65%)</span>
            <span className="flight-dashes" />
            <span className="flight-plane">
              <Icon name="plane" size={26} />
            </span>
            <span className="flight-dashes" />
            <span className="flight-code">K-MEANS PCA (35%)</span>
          </div>
          <Link href="/flights" className="forecast-link">
            Mở Không gian Radar &amp; Chuyến bay
            <Icon name="arrow" size={18} />
          </Link>
        </section>
      </div>
    </>
  );
}
