"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "../api-client";
import { number } from "../flight-types";

type Poll = {
  batch: { batch_id: string; fetched_at: string; created_at: string; inserted_count: number; updated_count: number } | null;
  raw: {
    raw_id: number;
    airline_iata: string | null;
    flight_number: string | null;
    dep_iata: string | null;
    arr_iata: string | null;
    dep_time: string | null;
    arr_time: string | null;
    processing_status: string;
  }[];
  processed: {
    flight_key: string;
    flight_code: string;
    origin: string;
    dest: string;
    fl_date: string;
    crs_dep_time: string | null;
    crs_arr_time: string | null;
    distance: number | null;
    delay_minutes: number | null;
  }[];
};

const pageSize = 5;
const route = (origin: string | null, dest: string | null) => origin && dest ? `${origin} → ${dest}` : "—";

function PollTable({ title, columns, rows }: {
  title: string;
  columns: string[];
  rows: { id: string | number; values: (string | null)[] }[];
}) {
  const [page, setPage] = useState(0);
  const start = page * pageSize;

  return (
    <section className="panel overview-poll-table" aria-label={title}>
      <div className="panel-heading"><h3>{title}</h3><span>{number(rows.length)} dòng</span></div>
      {rows.length ? <>
        <div className="table-scroll"><table>
          <thead><tr>{columns.map(column => <th key={column}>{column}</th>)}</tr></thead>
          <tbody>{rows.slice(start, start + pageSize).map(row => (
            <tr key={row.id}>{row.values.map((value, index) => <td key={columns[index]}>{value ?? "—"}</td>)}</tr>
          ))}</tbody>
        </table></div>
        <div className="table-footer">
          <span>{start + 1}–{Math.min(start + pageSize, rows.length)} / {number(rows.length)}</span>
          <div className="pagination-controls">
            <button type="button" className="button secondary" disabled={page === 0}
              onClick={() => setPage(value => value - 1)}>‹ Trước</button>
            <button type="button" className="button secondary" disabled={start + pageSize >= rows.length}
              onClick={() => setPage(value => value + 1)}>Sau ›</button>
          </div>
        </div>
      </> : <p>Chưa có bản ghi trong lượt này.</p>}
    </section>
  );
}

export function IngestionOverview() {
  const [poll, setPoll] = useState<Poll>();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const request = new AbortController();
    let loading = false;
    async function load() {
      if (loading) return;
      loading = true;
      try {
        const data = await apiRequest<Poll>("/ingestion/poll/latest", { signal: request.signal });
        if (!request.signal.aborted) { setPoll(data); setFailed(false); }
      } catch {
        if (!request.signal.aborted) setFailed(true);
      } finally {
        loading = false;
      }
    }
    void load();
    const timer = setInterval(() => void load(), 10000);
    return () => { request.abort(); clearInterval(timer); };
  }, []);

  return (
    <section className="overview-ingestion" aria-label="Lượt thu thập AirLabs">
      <div className="panel-heading">
        <div>
          <h2>Lượt thu thập AirLabs gần nhất</h2>
          {poll?.batch && <p>Ghi xong lúc <time dateTime={poll.batch.created_at}>
            {new Date(poll.batch.created_at).toLocaleString("vi-VN")}
          </time> · Hai bảng cập nhật cùng lượt thu thập</p>}
        </div>
      </div>
      {failed && <p role="alert">Chưa cập nhật được lượt thu thập.</p>}
      {!poll && !failed && <p role="status">Đang tải dữ liệu thu thập…</p>}
      {poll?.batch === null && <p role="status">Đang chờ lượt AirLabs đầu tiên ghi xong.</p>}
      {poll?.batch && <>
      <p className="analytics-status">
        {number(poll.raw.filter(row => row.processing_status === "duplicate").length)} dòng trùng ·{" "}
        {number(poll.raw.filter(row => row.processing_status === "rejected").length)} dòng không hợp lệ ·{" "}
        {number(poll.batch.inserted_count)} chuyến thêm mới · {number(poll.batch.updated_count)} chuyến cập nhật
      </p>
      <div className="overview-poll-grid" key={poll.batch.batch_id}>
        <PollTable title="Dữ liệu nhận từ AirLabs" columns={["Chuyến", "Tuyến", "Khởi hành", "Đến"]}
          rows={poll.raw.map(row => ({ id: row.raw_id, values: [
            [row.airline_iata, row.flight_number].filter(Boolean).join(" ") || null,
            route(row.dep_iata, row.arr_iata), row.dep_time, row.arr_time,
          ] }))} />
        <PollTable title="Chuyến đã xử lý và đưa vào sử dụng" columns={["Chuyến", "Tuyến", "Khởi hành", "Cự ly", "Độ trễ"]}
          rows={poll.processed.map(row => ({ id: row.flight_key, values: [
            row.flight_code, route(row.origin, row.dest),
            row.crs_dep_time ? `${row.fl_date} ${row.crs_dep_time}` : null,
            row.distance == null ? null : `${number(Math.round(row.distance))} dặm`,
            row.delay_minutes == null ? "Chưa có" : `${number(row.delay_minutes)} phút`,
          ] }))} />
      </div>
      </>}
    </section>
  );
}
