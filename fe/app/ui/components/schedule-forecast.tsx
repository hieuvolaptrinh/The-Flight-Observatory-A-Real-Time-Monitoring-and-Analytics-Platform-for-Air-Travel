"use client";

import { useEffect, useState } from "react";
import { number } from "../flight-types";
import { apiRequest } from "../api-client";

type Forecast =
  | { ready: false; forecast_date?: string }
  | {
    ready: true;
    forecast_date: string;
    payload: {
      predicted_flight_count: number;
      classification: "high" | "low";
      classification_threshold: number;
      explanation: string;
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

  useEffect(() => {
    const controller = new AbortController();
    requestForecast(request.method, controller.signal)
      .then(next => {
        if (!controller.signal.aborted) setResult({ request, forecast: next });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setResult({ request, error: error instanceof Error ? error.message : "Lỗi khi gọi Analytics API." });
        }
      });
    return () => controller.abort();
  }, [request]);

  return (
    <section className="analytics-panel schedule-forecast" aria-label="Dự báo lưu lượng ngày kế tiếp">
      <h2>Dự báo lưu lượng ngày kế tiếp</h2>
      <p>Ngày kế tiếp tính theo mốc cuối của dữ liệu chuyến bay đã lưu trong hệ thống.</p>
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
          {forecast.forecast_date ? "Chưa có dự báo cho ngày " + forecast.forecast_date + "." : "Chưa có dữ liệu chuyến bay để dự báo."}
        </p>
      )}
      <div className="analytics-controls">
        <button type="button" disabled={pending} onClick={() => setRequest({ method: "GET" })}>Tải lại</button>
        <button type="button" disabled={pending || forecast?.ready === true || (forecast?.ready === false && !forecast.forecast_date)}
          onClick={() => setRequest({ method: "POST" })}>
          Tạo dự báo
        </button>
      </div>
    </section>
  );
}
