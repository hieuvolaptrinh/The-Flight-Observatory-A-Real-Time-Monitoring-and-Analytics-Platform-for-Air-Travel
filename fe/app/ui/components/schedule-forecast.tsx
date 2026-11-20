"use client";

import { useEffect, useState } from "react";
import { number } from "../flight-types";
import { apiRequest } from "../api-client";

type ForecastScope = { airports: string[]; timezone: string };

type Forecast =
  | { ready: false; forecast_date: string; scope: ForecastScope; observed_days: number; required_days: number }
  | {
    ready: true;
    forecast_date: string;
    payload: {
      predicted_flight_count: number;
      classification: "high" | "low";
      classification_threshold: number;
      explanation: string;
      scope: ForecastScope;
      observed_days: number;
      provisional: boolean;
    };
  };

async function requestForecast(method: "GET" | "POST", signal: AbortSignal): Promise<Forecast> {
  return apiRequest<Forecast>("/analytics/forecast", { method, signal });
}

export function ScheduleForecast() {
  const [request, setRequest] = useState({ method: "GET" as "GET" | "POST" });
  const [result, setResult] = useState<{ request: typeof request; forecast?: Forecast; error?: string }>();
  const forecast = result?.request === request ? result.forecast : undefined;
  const error = result?.request === request ? result.error : undefined;
  const pending = result?.request !== request;
  const scope = forecast?.ready ? forecast.payload.scope : forecast?.scope;
  const needsHistory = forecast?.ready === false && forecast.observed_days < forecast.required_days;

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function update(method: "GET" | "POST") {
      try {
        const next = await requestForecast(method, controller.signal);
        if (!controller.signal.aborted) setResult({ request, forecast: next });
      } catch (error) {
        if (!controller.signal.aborted) {
          setResult({ request, error: error instanceof Error ? error.message : "Lỗi khi gọi Analytics API." });
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => void update("GET"), 60_000);
      }
    }
    void update(request.method);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [request]);

  return (
    <section className="analytics-panel schedule-forecast" aria-label="Dự báo lưu lượng ngày kế tiếp">
      <h2>Dự báo lưu lượng ngày mai</h2>
      {scope && <p>Chuyến khởi hành từ {scope.airports.join(", ")} trong phạm vi lịch bay đã thu thập. Múi giờ {scope.timezone}.</p>}
      {forecast?.ready && forecast.payload.provisional && (
        <p><strong>Dự báo sơ bộ</strong> · Dựa trên {forecast.payload.observed_days} ngày có dữ liệu.</p>
      )}
      {forecast?.ready && (
        <dl className="schedule-forecast-summary">
          <div><dt>Ngày dự báo</dt><dd>{forecast.forecast_date}</dd></div>
          <div><dt>Số chuyến dự báo</dt><dd>{number(forecast.payload.predicted_flight_count)}</dd></div>
          <div>
            <dt>Mức lưu lượng</dt>
            <dd>{forecast.payload.classification === "high" ? "Cao" : "Thấp"}</dd>
          </div>
        </dl>
      )}
      {forecast?.ready && (
        <p>Ngưỡng mức cao từ {number(forecast.payload.classification_threshold)} chuyến. {forecast.payload.explanation}</p>
      )}
      {pending && <p role="status">{request.method === "POST" ? "Đang tạo dự báo…" : "Đang tải dự báo…"}</p>}
      {error && <p role="alert">Không lấy được dự báo. {error}</p>}
      {forecast && !forecast.ready && (
        <p role="status">
          Chưa có dự báo cho ngày {forecast.forecast_date}.
          {needsHistory && ` Đã có ${forecast.observed_days}/${forecast.required_days} ngày dữ liệu cần thiết.`}
        </p>
      )}
      <div className="analytics-controls">
        <button type="button" disabled={pending} onClick={() => setRequest({ method: "GET" })}>Tải lại</button>
        <button type="button" disabled={pending || forecast?.ready === true || needsHistory}
          onClick={() => setRequest({ method: "POST" })}>
          Tạo dự báo
        </button>
      </div>
    </section>
  );
}
