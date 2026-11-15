"use client";

import { useEffect, useState, type ReactNode } from "react";
import { CustomSelect } from "../components/custom-select";
import { API_BASE, flightDateRange, number } from "../flight-types";

type Grain = "day" | "week" | "month";
type SeriesRow = { period_start: string; flight_count: number };
type LineResponse = {
  items: SeriesRow[];
  summary: { ready: boolean; flight_count: number; updated_at?: string; date_from?: string; date_to?: string };
};
type HistogramRow = { bin_start_min: number; bin_end_min: number; flight_count: number };
type ScatterRow = {
  distance_miles: number | null;
  scheduled_elapsed_min: number;
};
type ComponentResponse = {
  grain: "week" | "month";
  items: { period_start: string; trend?: number; seasonal?: number }[];
};
type Correlation = {
  variables: string[];
  matrix: (number | null)[][];
  samples: number[][];
};
type AnalyticsData = {
  line: LineResponse;
  trend: ComponentResponse;
  seasonality: ComponentResponse;
  correlation: Correlation;
  period: string | undefined;
  histogram: HistogramRow[];
  scatter: ScatterRow[];
  moreScatter: boolean;
};

const grains: Record<Grain, string> = { day: "Ngày", week: "Tuần", month: "Tháng" };
const variableLabels: Record<string, string> = {
  distance_miles: "Khoảng cách",
  scheduled_elapsed_min: "Thời lượng",
  departure_hour: "Giờ khởi hành",
};

function timePoint(date: string, value: number) {
  return { x: Date.parse(date) / 86_400_000, y: value, label: date };
}

async function read<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(API_BASE + "/analytics/" + path, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Analytics HTTP " + response.status);
  return response.json();
}

async function load(grain: Grain, selected: string, signal: AbortSignal): Promise<AnalyticsData> {
  const [line, trend, seasonality, correlation] = await Promise.all([
    read<LineResponse>("line?limit=500&grain=" + grain, signal),
    read<ComponentResponse>("trend?limit=500", signal),
    read<ComponentResponse>("seasonality?limit=500", signal),
    read<Correlation>("correlation", signal),
  ]);

  const periods = line.items.filter(row => row.flight_count > 0);
  const period = periods.find(row => row.period_start === selected)?.period_start
    ?? periods.at(-1)?.period_start;
  if (!period || !line.summary.ready) {
    return { line, trend, seasonality, correlation, period, histogram: [], scatter: [], moreScatter: false };
  }

  const query = new URLSearchParams({ grain, period_start: period });
  const [histogram, scatter] = await Promise.all([
    read<{ items: HistogramRow[] }>("histogram?limit=500&" + query, signal),
    read<{ items: ScatterRow[]; has_more: boolean }>("scatter?limit=500&" + query, signal),
  ]);
  return { line, trend, seasonality, correlation, period, histogram: histogram.items,
    scatter: scatter.items, moreScatter: scatter.has_more };
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="analytics-panel">
      <h2>{title}</h2>
      <p>{description}</p>
      {children}
    </section>
  );
}

function Plot({ points, mode = "line", label, xUnit, yUnit }: {
  points: { x: number; y: number; label: string }[];
  mode?: "line" | "bar" | "scatter";
  label: string;
  xUnit: string;
  yUnit: string;
}) {
  if (!points.length) return <p className="analytics-empty">Chưa đủ dữ liệu cho biểu đồ này.</p>;

  const xMin = Math.min(...points.map(point => point.x));
  const xRange = Math.max(1, Math.max(...points.map(point => point.x)) - xMin);
  const yMin = Math.min(0, ...points.map(point => point.y));
  const yMax = Math.max(1, ...points.map(point => point.y));
  const barWidth = Math.min(32, 380 / points.length);
  const x = (value: number) => 72 + (value - xMin) * 414 / xRange;
  const y = (value: number) => 173 - (value - yMin) * 137 / (yMax - yMin);
  const axisLabel = (point: (typeof points)[number]) => mode === "line" ? point.label : number(point.x);
  const middle = points[Math.floor(points.length / 2)];
  const ticks = mode === "scatter"
    ? [xMin, xMin + xRange / 2, xMin + xRange].map(value => ({ x: value, y: 0, label: "" }))
    : [points[0], middle, points[points.length - 1]].filter((point, index, all) => all.indexOf(point) === index);

  return (
    <svg className="analytics-plot" viewBox="0 0 530 227" role="img" aria-label={label}>
      <text x="12" y="20">{yUnit}</text>
      {[yMin, (yMin + yMax) / 2, yMax].map(value => (
        <g key={value}>
          <line className="analytics-gridline" x1="54" x2="504" y1={y(value)} y2={y(value)} />
          <text x="49" y={y(value) + 4} textAnchor="end">{number(Math.round(value * 10) / 10)}</text>
        </g>
      ))}
      {mode === "line" && (
        <polyline className="analytics-series-line" points={points.map(point => x(point.x) + "," + y(point.y)).join(" ")} />
      )}
      {points.map((point, index) => mode === "bar" ? (
        <rect key={index} className="analytics-series-mark" x={x(point.x) - barWidth / 2}
          y={y(point.y)} width={barWidth} height={y(0) - y(point.y)} rx="2">
          <title>{point.label}</title>
        </rect>
      ) : (
        <circle key={index} className="analytics-series-mark" cx={x(point.x)} cy={y(point.y)} r={mode === "scatter" ? 3 : 2.4}>
          <title>{mode === "line" ? point.label + " · " + number(point.y) : point.label}</title>
        </circle>
      ))}
      {ticks.map(point => <text key={point.x} x={x(point.x)} y="194" textAnchor="middle">{axisLabel(point)}</text>)}
      <text x="278" y="217" textAnchor="middle">{xUnit}</text>
    </svg>
  );
}

export function AnalyticsView() {
  const [grain, setGrain] = useState<Grain>("day");
  const [selected, setSelected] = useState("");
  const [zoom, setZoom] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: AnalyticsData; error?: boolean }>();
  const key = grain + "/" + selected + "/" + refresh;
  const data = result?.key === key ? result.data : undefined;
  const failed = result?.key === key && result.error;

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function update() {
      try {
        const next = await load(grain, selected, controller.signal);
        if (!controller.signal.aborted) setResult({ key, data: next });
      } catch {
        if (!controller.signal.aborted) setResult({ key, error: true });
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(update, 15000);
      }
    }
    void update();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [grain, key, selected]);

  const periods = data?.line.items.filter(row => row.flight_count > 0) ?? [];
  const line = data?.line.items.slice(zoom === 0 ? 0 : -zoom) ?? [];
  const selectedPeriod = data && selected !== data.period ? "" : selected;
  const summary = data?.line.summary;
  const dateRange = summary?.date_from && summary.date_to
    ? flightDateRange(summary.date_from, new Date(Date.parse(summary.date_to) - 86_400_000).toISOString().slice(0, 10))
    : null;

  return (
    <section className="analytics-page" aria-label="Phân tích dữ liệu chuyến bay">
      <div className="analytics-controls">
        <div className="analytics-field">
          <span>Gom theo</span>
          <CustomSelect
            ariaLabel="Gom theo"
            value={grain}
            onChange={value => {
              setGrain(value as Grain);
              setSelected("");
            }}
            options={Object.entries(grains).map(([value, label]) => ({ value, label }))}
          />
        </div>
        <div className="analytics-field">
          <span>Khoảng xem đường thời gian</span>
          <CustomSelect
            ariaLabel="Khoảng xem đường thời gian"
            value={String(zoom)}
            onChange={value => setZoom(Number(value))}
            options={[
              { value: "0", label: "Toàn bộ" },
              { value: "30", label: "30 kỳ gần nhất" },
              { value: "7", label: "7 kỳ gần nhất" },
            ]}
          />
        </div>
        <div className="analytics-field">
          <span>Kỳ của histogram và scatter</span>
          <CustomSelect
            ariaLabel="Kỳ của histogram và scatter"
            value={selectedPeriod}
            onChange={setSelected}
            options={[
              { value: "", label: "Kỳ mới nhất" },
              ...(!data && selected ? [{ value: selected, label: selected }] : []),
              ...periods.map(({ period_start }) => ({ value: period_start, label: period_start })),
            ]}
          />
        </div>
        <button type="button" onClick={() => setRefresh(value => value + 1)}>Tải lại</button>
      </div>

      {failed && <p className="analytics-empty" role="alert">Không tải được kết quả từ Analytics API.</p>}
      {!data && !failed && <p className="analytics-empty" role="status">Đang tải kết quả phân tích…</p>}
      {data && !data.line.summary.ready && (
        <p className="analytics-empty" role="status">Chưa có kết quả phân tích. Chạy Analytics POST /run để tạo kết quả.</p>
      )}

      {data?.line.summary.ready && (
        <>
          <p className="analytics-status">
            {dateRange && <><strong>Ngày chuyến bay</strong> · {dateRange} · </>}
            {number(data.line.summary.flight_count)} chuyến đã nạp
            {data.line.summary.updated_at && (
              <> · Tổng hợp lúc {new Date(data.line.summary.updated_at).toLocaleString("vi-VN")}</>
            )}
          </p>
          <div className="analytics-charts">
            <Panel title="Lưu lượng chuyến bay" description={"Số chuyến theo " + grains[grain].toLowerCase()}>
              <Plot label="Đường thời gian số chuyến bay" xUnit="Ngày bắt đầu kỳ" yUnit="Chuyến"
                points={line.map(row => timePoint(row.period_start, row.flight_count))} />
            </Panel>
            <Panel title="Xu hướng lưu lượng" description={"Xu hướng sau khi gom theo " + grains[data.trend.grain].toLowerCase()}>
              <Plot label="Đường xu hướng số chuyến bay" xUnit="Ngày bắt đầu kỳ" yUnit="Chuyến"
                points={data.trend.items.flatMap(row => row.trend == null ? [] : [timePoint(row.period_start, row.trend)])} />
            </Panel>
            <Panel title="Phân bố thời lượng bay" description={"Histogram theo khoảng 30 phút · " + data.period}>
              <Plot mode="bar" label="Histogram thời lượng bay" xUnit="Thời lượng dự kiến (phút)" yUnit="Chuyến"
                points={data.histogram.map(row => ({ x: row.bin_start_min, y: row.flight_count,
                  label: row.bin_start_min + "–" + row.bin_end_min + " phút · " + number(row.flight_count) + " chuyến" }))} />
            </Panel>
            <Panel title="Khoảng cách và thời lượng" description={"Scatter · " + data.period
              + (data.moreScatter ? " · Hiển thị 500 chuyến đầu kỳ" : "")}>
              <Plot mode="scatter" label="Điểm phân tán khoảng cách và thời lượng" xUnit="Khoảng cách (dặm)" yUnit="Phút"
                points={data.scatter.flatMap(row => row.distance_miles == null ? [] :
                  [{ x: row.distance_miles, y: row.scheduled_elapsed_min,
                    label: number(row.distance_miles) + " dặm · " + number(row.scheduled_elapsed_min) + " phút" }])} />
            </Panel>
            <Panel title="Mùa vụ lưu lượng" description={"Thành phần mùa vụ sau khi gom theo " + grains[data.seasonality.grain].toLowerCase()}>
              <Plot label="Đường mùa vụ số chuyến bay" xUnit="Ngày bắt đầu kỳ" yUnit="Chuyến"
                points={data.seasonality.items.flatMap(row =>
                  row.seasonal == null ? [] : [timePoint(row.period_start, row.seasonal)])} />
            </Panel>
            <Panel title="Ma trận tương quan Pearson" description="Hệ số tương quan giữa các biến trong khoảng dữ liệu phân tích.">
              {data.correlation.variables.length > 0 ? (
                <table className="analytics-matrix">
                  <thead><tr><th scope="col">Biến</th>{data.correlation.variables.map(variable =>
                    <th scope="col" key={variable}>{variableLabels[variable] ?? variable}</th>)}</tr></thead>
                  <tbody>{data.correlation.variables.map((variable, row) => (
                    <tr key={variable}>
                      <th scope="row">{variableLabels[variable] ?? variable}</th>
                      {data.correlation.matrix[row].map((value, col) => (
                        <td key={col} title={number(data.correlation.samples[row][col]) + " mẫu"}>
                          {value == null ? "—" : value.toFixed(2)}
                        </td>
                      ))}
                    </tr>
                  ))}</tbody>
                </table>
              ) : <p className="analytics-empty">Chưa có dữ liệu tương quan.</p>}
            </Panel>
          </div>
        </>
      )}
    </section>
  );
}
