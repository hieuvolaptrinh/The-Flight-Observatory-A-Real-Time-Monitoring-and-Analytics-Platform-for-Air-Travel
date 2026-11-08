"use client";

import {
  AirportStat,
  PredictionItem,
  number,
  riskLabels,
  riskOf,
} from "../flight-types";
import { Icon } from "../components/icons";
import { Metric } from "../components/metric-card";

interface ForecastViewProps {
  scoped: PredictionItem[];
  filteredPredictions: PredictionItem[];
  forecastAvg: number;
  highCount: number;
  meanProbability: number;
  selection: AirportStat[];
  risk: string;
  setRisk: (val: string) => void;
}

export function ForecastView({
  scoped,
  filteredPredictions,
  forecastAvg,
  highCount,
  meanProbability,
  selection,
  risk,
  setRisk,
}: ForecastViewProps) {
  return (
    <>
      <section className="metrics" aria-label="Chỉ số dự báo">
        <Metric
          title="Chuyến bay được đánh giá"
          value={number(scoped.length)}
          unit="chuyến"
          icon="plane"
          note="Dựa trên tập chuyến bay thực tế trong PostgreSQL"
        />
        <Metric
          title="Delay dự kiến trung bình"
          value={forecastAvg.toFixed(1)}
          unit="phút"
          icon="clock"
          note="Trung bình các chuyến theo bộ lọc"
          color="blue"
        />
        <Metric
          title="Chuyến bay nguy cơ cao"
          value={number(highCount)}
          unit="chuyến"
          icon="alert"
          note="Xác suất trễ từ 60% trở lên"
          color="coral"
        />
        <Metric
          title="Xác suất trễ trung bình"
          value={meanProbability.toFixed(1)}
          unit="%"
          icon="chart"
          note="Trung bình xác suất phân loại"
          color="purple"
        />
      </section>

      <div className="forecast-charts">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Delay dự kiến theo sân bay khởi hành</h2>
              <p>Số phút trễ trung bình tại các sân bay lớn trong DB</p>
            </div>
            <span className="chart-unit">ĐƠN VỊ: PHÚT</span>
          </div>
          <div className="airport-bars">
            {selection.slice(0, 8).map(a => {
              const rows = scoped.filter(p => p.origin === a.code);
              const value = rows.length
                ? rows.reduce((s, p) => s + p.delay, 0) / rows.length
                : a.delay;
              return (
                <div className="airport-bar" key={a.code}>
                  <span className="airport-bar-value">{value.toFixed(1)}</span>
                  <div className="airport-bar-track">
                    <div
                      style={{ height: `${Math.min(100, (value / 45) * 100)}%` }}
                      className={value >= 25 ? "bar-coral" : "bar-teal"}
                    />
                  </div>
                  <strong>{a.code}</strong>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel risk-panel">
          <div className="panel-heading">
            <div>
              <h2>Phân bố mức độ nguy cơ</h2>
              <p>Xác suất chuyến bay trễ ≥ 15 phút</p>
            </div>
            <Icon name="spark" size={18} />
          </div>
          <div className="risk-distribution">
            {(["high", "medium", "low"] as const).map(r => {
              const count = scoped.filter(p => riskOf(p.probability) === r).length;
              return (
                <button
                  type="button"
                  className={`risk-row ${risk === r ? "selected" : ""}`}
                  key={r}
                  onClick={() => setRisk(risk === r ? "all" : r)}
                  aria-pressed={risk === r}
                >
                  <span className={`risk-symbol ${r}`}>
                    <Icon
                      name={r === "high" ? "alert" : r === "low" ? "check" : "clock"}
                      size={18}
                    />
                  </span>
                  <span className="risk-row-text">
                    <strong>{riskLabels[r]}</strong>
                    <small>
                      {r === "high"
                        ? "Xác suất ≥ 60%"
                        : r === "medium"
                          ? "Xác suất 30% – 59%"
                          : "Xác suất dưới 30%"}
                    </small>
                  </span>
                  <strong>
                    {count}
                    <small>chuyến</small>
                  </strong>
                  <span
                    className={`risk-mini-bar ${r}`}
                    style={{
                      width: `${scoped.length ? (count / scoped.length) * 100 : 0}%`,
                    }}
                  />
                </button>
              );
            })}
          </div>
        </section>
      </div>

      <section className="panel predictions-panel">
        <div className="panel-heading">
          <div>
            <h2>
              Danh sách dự báo chi tiết <span className="count-pill">{filteredPredictions.length}</span>
            </h2>
            <p>Sắp xếp theo mức độ rủi ro và độ trễ dự kiến</p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>CHUYẾN BAY</th>
                <th>HÀNH TRÌNH</th>
                <th>KHỞI HÀNH</th>
                <th>DELAY DỰ KIẾN</th>
                <th>XÁC SUẤT TRỄ</th>
                <th>PHÂN LOẠI NGUY CƠ</th>
              </tr>
            </thead>
            <tbody>
              {filteredPredictions.map((p, idx) => (
                <tr key={`${p.flight}-${idx}`}>
                  <td>
                    <span className={`airline-mark airline-${p.carrier}`}>{p.carrier}</span>
                    <strong>{p.flight}</strong>
                  </td>
                  <td>
                    <span className="route">
                      <strong>{p.origin}</strong>
                      <Icon name="arrow" size={14} />
                      <strong>{p.destination}</strong>
                    </span>
                  </td>
                  <td className="tabular">{p.time}</td>
                  <td className="tabular">
                    <strong className={p.delay >= 30 ? "coral-text" : ""}>+{p.delay}</strong>
                    <span className="muted"> phút</span>
                  </td>
                  <td>
                    <div className="probability">
                      <span className="tabular">{p.probability}%</span>
                      <div>
                        <span
                          className={riskOf(p.probability)}
                          style={{ width: `${p.probability}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className={`risk-badge ${riskOf(p.probability)}`}>
                      <span />
                      {riskLabels[riskOf(p.probability)]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
