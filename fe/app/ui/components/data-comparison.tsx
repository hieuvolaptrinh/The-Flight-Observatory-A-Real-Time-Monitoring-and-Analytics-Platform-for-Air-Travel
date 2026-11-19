"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "../api-client";

type FlightComparison = {
  raw: { raw: unknown; processing_status: string; processing_error: string | null; fetched_at: string };
  processed: Record<string, unknown> | null;
  matches_current_source: boolean;
  fields: { label: string; raw: unknown; processed: unknown }[];
};
const display = (value: unknown) => value == null ? "—" : String(value);

export function FlightDataComparison({ rawId, onClose }: { rawId: number; onClose: () => void }) {
  const [result, setResult] = useState<{ id: number; data?: FlightComparison; error?: string }>();
  useEffect(() => {
    const controller = new AbortController();
    apiRequest<FlightComparison>(`/ingestion/raw/${rawId}/comparison`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult({ id: rawId, data }); })
      .catch(error => { if (!controller.signal.aborted) setResult({ id: rawId, error: error.message }); });
    return () => controller.abort();
  }, [rawId]);
  const current = result?.id === rawId ? result : undefined;
  const data = current?.data;
  return <section className="data-comparison panel" aria-label="So sánh dữ liệu trước và sau xử lý">
    <div className="panel-heading"><h3>Trước và sau xử lý · Dòng thô #{rawId}</h3>
      <button type="button" className="button secondary" onClick={onClose}>Đóng</button></div>
    {!current && <p role="status">Đang đọc hai nguồn dữ liệu…</p>}
    {current?.error && <p role="alert">{current.error}</p>}
    {data && <>
      <p>Lấy từ API lúc {new Date(data.raw.fetched_at).toLocaleString("vi-VN")}.</p>
      {!data.processed && <p role="status">Chưa có bản đã xử lý tương ứng. {data.raw.processing_error}</p>}
      {data.processed && !data.matches_current_source && <p className="analytics-status">
        Bên trái là lần lấy dữ liệu bạn chọn; bên phải là bản đã xử lý mới nhất của cùng chuyến bay, có thể đến từ lần cập nhật khác.
      </p>}
      <div className="table-scroll"><table><thead><tr><th>Trường</th><th>Raw từ API</th><th>Đã xử lý</th></tr></thead>
        <tbody>{data.fields.map(field => <tr key={field.label}><th>{field.label}</th>
          <td>{display(field.raw)}</td><td>{display(field.processed)}</td></tr>)}</tbody></table></div>
      <p>Khoảng cách và thời lượng có thể được tính bổ sung từ tọa độ, lịch bay và múi giờ; “—” là nguồn không cung cấp.</p>
      <div className="comparison-json">
        <details><summary>Xem JSON raw đầy đủ</summary><pre>{JSON.stringify(data.raw.raw, null, 2)}</pre></details>
        <details><summary>Xem JSON đã xử lý đầy đủ</summary><pre>{JSON.stringify(data.processed, null, 2)}</pre></details>
      </div>
    </>}
  </section>;
}

type WeatherPair = {
  raw: { wind_speed_ms: number | null; visibility_m: number | null; raw: unknown } | null;
  processed: { airport_code: string; observed_at: string; temperature_c: number | null;
    wind_speed_kmh: number | null; visibility_km: number | null };
};

export function WeatherDataComparison() {
  const [items, setItems] = useState<WeatherPair[]>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const result = await apiRequest<{ items: WeatherPair[] }>("/ingestion/weather?limit=6", { signal: controller.signal });
        if (!controller.signal.aborted) { setItems(result.items); setError(""); }
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Không đọc được thời tiết.");
      }
    }
    void load();
    const timer = setInterval(() => void load(), 15000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [retry]);
  return <section className="panel data-comparison" aria-label="Dữ liệu thời tiết trước và sau xử lý">
    <div className="panel-heading"><div><h2>Thời tiết · Raw và đã xử lý</h2>
      <p>Cùng một lần quan sát; gió đổi từ m/s sang km/h, tầm nhìn từ mét sang km.</p></div>
      <button type="button" className="button secondary" onClick={() => setRetry(value => value + 1)}>Tải lại</button></div>
    {error && <p role="alert">{error}</p>}
    {!items && !error && <p role="status">Đang tải thời tiết đã lưu…</p>}
    {items?.length === 0 && <p>Chưa có dữ liệu thời tiết đã lưu.</p>}
    {!!items?.length && <div className="table-scroll"><table><thead><tr><th>Sân bay / Quan sát</th><th>Gió raw · m/s</th>
      <th>Gió đã xử lý · km/h</th><th>Tầm nhìn raw · m</th><th>Tầm nhìn đã xử lý · km</th><th>Chi tiết</th></tr></thead>
      <tbody>{items.map(item => <tr key={item.processed.airport_code + item.processed.observed_at}>
        <td><strong>{item.processed.airport_code}</strong><br />{new Date(item.processed.observed_at).toLocaleString("vi-VN")}</td>
        <td>{display(item.raw?.wind_speed_ms)}</td><td>{display(item.processed.wind_speed_kmh)}</td>
        <td>{display(item.raw?.visibility_m)}</td><td>{display(item.processed.visibility_km)}</td>
        <td><details><summary>JSON trước / sau</summary><pre>{JSON.stringify({ raw: item.raw?.raw, processed: item.processed }, null, 2)}</pre></details></td>
      </tr>)}</tbody></table></div>}
  </section>;
}
