"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import {
  airports,
  carriers,
  predictions,
  demoFlights,
  FlightItem,
  statusLabels,
  statusBadgeClass,
  riskOf,
  riskLabels,
  number,
} from "./demo-data";

type IconName = "plane" | "grid" | "spark" | "chart" | "clock" | "arrow" | "download" | "refresh" | "calendar" | "search" | "chevron" | "check" | "alert" | "globe";
function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    plane: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="m22 2-11 11" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" /><path d="M21 2v4m-2-2h4" /></>,
    chart: <path d="M4 4v16h17M8 15l4-5 4 3 5-7" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    download: <path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5" />,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M7 3v4m10-4v4M3 11h18" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    chevron: <path d="m8 10 4 4 4-4" />,
    check: <path d="m5 12 4 4L19 6" />,
    alert: <><path d="m12 3 10 18H2Z" /><path d="M12 9v4m0 3v1" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Metric({ title, value, unit, icon, note, color = "teal" }: { title: string; value: string; unit?: string; icon: IconName; note: string; color?: string }) {
  return <article className="metric"><div className="metric-top"><span>{title}</span><span className={`metric-icon ${color}`}><Icon name={icon} size={19} /></span></div><div className="metric-value">{value}<span>{unit}</span></div><div className="metric-note"><span className={`tiny-dot ${color}`} />{note}</div></article>;
}

function TrendChart({ rate, day }: { rate: number; day: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const values = [12,10,13,11,15,20,17,23,18,24,29,23,26].map(v => Math.min(39, v*rate/21));
  const points = values.map((v,i) => `${48+i*46},${190-v*3.7}`).join(" ");
  return <div className="trend-chart"><svg viewBox="0 0 640 235" role="img" aria-label={`Tỷ lệ chuyến bay trễ theo giờ ngày ${day}`}>
    <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#14a58e" stopOpacity=".21" /><stop offset="100%" stopColor="#14a58e" stopOpacity="0" /></linearGradient></defs>
    {[0,10,20,30,40].map(n => <g key={n}><line x1="48" x2="610" y1={190-n*3.7} y2={190-n*3.7} stroke="#e9edf0" strokeDasharray="4 5" /><text x="32" y={194-n*3.7} textAnchor="end">{n}%</text></g>)}
    <polygon points={`48,190 ${points} 600,190`} fill="url(#area)" /><polyline points={points} fill="none" stroke="#0b9d87" strokeWidth="3" strokeLinejoin="round" />
    {values.map((v,i) => <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}><rect x={30+i*46} y="30" width="40" height="165" fill="transparent" />{hover === i && <><line x1={48+i*46} x2={48+i*46} y1="30" y2="190" stroke="#0b9d87" strokeDasharray="3 3" /><circle cx={48+i*46} cy={190-v*3.7} r="5" fill="#0b9d87" stroke="white" strokeWidth="3" /><text x={Math.min(575,Math.max(70,48+i*46))} y={175-v*3.7} textAnchor="middle" className="chart-tooltip">{v.toFixed(1)}%</text></>}</g>)}
    {[0,2,4,6,8,10,12].map(i => <text key={i} x={48+i*46} y="220" textAnchor="middle">{String(i*2).padStart(2,"0")}:00</text>)}
  </svg></div>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8080/api";
const DIRECT_INGESTION_URLS = ["http://127.0.0.1:8004", "http://localhost:8004"];
const DIRECT_SIMULATOR_URLS = ["http://127.0.0.1:8000", "http://localhost:8000"];

const CARRIER_MAP: Record<string, string> = {
  AA: "American Airlines",
  DL: "Delta Air Lines",
  UA: "United Airlines",
  WN: "Southwest Airlines",
  AS: "Alaska Airlines",
  B6: "JetBlue Airways",
  NK: "Spirit Airlines",
  F9: "Frontier Airlines",
  OO: "SkyWest Airlines",
};

function normalizeSimulatorRecord(raw: Record<string, unknown>, fetchedAt: string, idx: number): FlightItem {
  const flDate = String(raw.FL_DATE || "2025-01-06");
  const carrier = String(raw.OP_UNIQUE_CARRIER || "AA").toUpperCase();
  const flNum = String(raw.OP_CARRIER_FL_NUM || idx);
  const origin = String(raw.ORIGIN || "JFK").toUpperCase();
  const dest = String(raw.DEST || "LAX").toUpperCase();
  const depRaw = String(raw.CRS_DEP_TIME || "0800").padStart(4, "0");
  const arrRaw = String(raw.CRS_ARR_TIME || "1000").padStart(4, "0");
  const crsDep = `${depRaw.slice(0, 2)}:${depRaw.slice(2, 4)}`;
  const crsArr = `${arrRaw.slice(0, 2)}:${arrRaw.slice(2, 4)}`;
  const flightKey = `${flDate}_${carrier}_${flNum}_${origin}_${dest}_${depRaw}`;

  // Hash tất định để ước lượng delay khi đọc thẳng từ Simulator
  let hash = 0;
  for (let i = 0; i < flightKey.length; i++) {
    hash = (hash * 31 + flightKey.charCodeAt(i)) >>> 0;
  }
  const bucket = hash % 100;
  const depHour = parseInt(depRaw.slice(0, 2), 10) || 12;
  const threshold = 15 <= depHour && depHour <= 21 ? 58 : 72;
  let delayMinutes = hash % 12;
  let delayStatus: FlightItem["delay_status"] = "on_time";
  if (bucket >= threshold && bucket < threshold + 20) {
    delayMinutes = 15 + (hash % 28);
    delayStatus = "moderate_delay";
  } else if (bucket >= threshold + 20) {
    delayMinutes = 45 + (hash % 65);
    delayStatus = "severe_delay";
  }

  return {
    flight_key: flightKey,
    fl_date: flDate,
    op_unique_carrier: carrier,
    carrier_name: CARRIER_MAP[carrier] || `Carrier ${carrier}`,
    tail_num: String(raw.TAIL_NUM || "—"),
    op_carrier_fl_num: flNum,
    flight_code: `${carrier} ${flNum}`,
    origin,
    dest,
    route: `${origin} → ${dest}`,
    crs_dep_time: crsDep,
    crs_arr_time: crsArr,
    crs_elapsed_time: Number(raw.CRS_ELAPSED_TIME || 120),
    distance: Number(raw.DISTANCE || 800),
    delay_minutes: delayMinutes,
    delay_status: delayStatus,
    is_delayed: delayMinutes >= 15 ? 1 : 0,
    ingested_at: fetchedAt,
  };
}

export default function Dashboard({ view }: { view: "overview" | "flights" | "forecast" }) {
  const isOverview = view === "overview";
  const isFlights = view === "flights";
  const forecast = view === "forecast";

  const [airport,setAirport] = useState("all");
  const [destAirport,setDestAirport] = useState("all");
  const [carrier,setCarrier] = useState("all");
  const [day,setDay] = useState("06/11/2026");
  const [rankBy,setRankBy] = useState<"airports" | "carriers">("airports");
  const [risk,setRisk] = useState("all");
  const [flightStatus,setFlightStatus] = useState("all");
  const [search,setSearch] = useState("");
  const [sort,setSort] = useState("time");
  const [updated,setUpdated] = useState("14:35 · 06/11/2026 UTC");
  const [toast,setToast] = useState("");
  const [busy,setBusy] = useState(false);

  // State cho trang Danh sách chuyến bay (FE · Chuyến bay - STT 15)
  const [liveFlights, setLiveFlights] = useState<FlightItem[] | null>(null);
  const [apiReady, setApiReady] = useState<boolean | null>(null);
  const [apiMode, setApiMode] = useState<"gateway" | "ingestion" | "simulator" | "demo">("demo");
  const [batchMeta, setBatchMeta] = useState<{
    total_stored?: number;
    window_start?: number;
    window_end?: number;
    inserted_count?: number;
    duplicate_count?: number;
  } | null>(null);

  function notify(message: string) { setToast(message); setTimeout(() => setToast(""),4000); }

  const fetchIngestionFlights = useCallback(async (silent = false) => {
    setBusy(true);
    const ingestionCandidates = [
      ...DIRECT_INGESTION_URLS.map(u => ({ mode: "ingestion" as const, url: `${u}/flights?limit=500` })),
      { mode: "gateway" as const, url: `${API_BASE}/ingestion/flights?limit=500` },
    ];
    for (const candidate of ingestionCandidates) {
      try {
        const res = await fetch(candidate.url, { cache: "no-store" });
        if (!res.ok) continue;
        const json = await res.json();
        setApiMode(candidate.mode);
        setApiReady(Boolean(json.ready));
        const items: FlightItem[] = json?.output?.items || [];
        const meta = json?.output?.metadata || {};
        setLiveFlights(items);
        setBatchMeta({
          total_stored: meta.total_stored ?? items.length,
          window_start: meta.last_batch?.window_start,
          window_end: meta.last_batch?.window_end,
          inserted_count: meta.last_batch?.inserted_count,
          duplicate_count: meta.last_batch?.duplicate_count,
        });
        if (json.updated_at) {
          setUpdated(new Date(json.updated_at).toISOString().replace("T", " ").slice(0, 19) + " UTC");
        }
        setBusy(false);
        if (!silent) {
          notify(json.ready ? `Đã tải ${items.length} chuyến bay từ DB Ingestion.` : "DB đang trống (ready: false). Hãy nhấn 'Thu thập batch mới'!");
        }
        return;
      } catch {
        // try next endpoint
      }
    }

    // Nếu service Ingestion (8004) chưa bật nhưng Data Simulator (8000) đang bật, lấy trực tiếp từ Simulator!
    for (const simBase of DIRECT_SIMULATOR_URLS) {
      try {
        const res = await fetch(`${simBase}/flights`, { cache: "no-store" });
        if (!res.ok) continue;
        const simJson = await res.json();
        const rawList: Record<string, unknown>[] = simJson.data || [];
        const fetchedAt = simJson.fetched_at || new Date().toISOString();
        const incoming = rawList.map((r, i) => normalizeSimulatorRecord(r, fetchedAt, i));

        setLiveFlights(prev => {
          const existing = prev || [];
          const existingKeys = new Set(existing.map(item => item.flight_key));
          const newItems = incoming.filter(item => !existingKeys.has(item.flight_key));
          const merged = [...newItems, ...existing];
          setBatchMeta({
            total_stored: merged.length,
            window_start: simJson.window_start,
            window_end: simJson.window_end,
            inserted_count: newItems.length,
            duplicate_count: incoming.length - newItems.length,
          });
          return merged;
        });
        setApiMode("simulator");
        setApiReady(true);
        setUpdated(fetchedAt.replace("T", " ").replace("Z", " UTC"));
        setBusy(false);
        if (!silent) {
          notify(`Đã thu thập cửa sổ [${simJson.window_start}..${simJson.window_end}] từ Simulator (port 8000)!`);
        }
        return;
      } catch {
        // try next
      }
    }

    setApiMode("demo");
    setApiReady(null);
    setBusy(false);
    if (!silent) {
      notify("Đang hiển thị dữ liệu mẫu (hãy bật port 8004 hoặc 8000 để lấy API thật).");
    }
  }, []);

  async function triggerIngestionRun() {
    setBusy(true);
    const runUrls = [
      ...DIRECT_INGESTION_URLS.map(u => `${u}/run`),
      `${API_BASE}/ingestion/run`,
    ];
    for (const url of runUrls) {
      try {
        const res = await fetch(url, { method: "POST" });
        if (res.ok) {
          await fetchIngestionFlights(true);
          notify("Đã chạy POST /run (port 8004): nạp cửa sổ trượt & lưu vào DB thành công!");
          return;
        }
      } catch {
        // try next
      }
    }

    // Fallback sang Simulator (port 8000) nếu bạn chỉ mới bật port 8000 mà chưa bật port 8004
    await fetchIngestionFlights(false);
  }

  useEffect(() => {
    if (isFlights) {
      fetchIngestionFlights(true);
    }
  }, [isFlights, fetchIngestionFlights]);

  const selection = airports.filter(a => airport === "all" || a.code === airport);
  const carrierRate = carrier === "all" ? 1 : carriers.find(c => c.code === carrier)!.rate/20;
  const factor = (day === "06/11/2026" ? 1 : day === "05/11/2026" ? .91 : .86) * (carrier === "all" ? 1 : carriers.find(c => c.code === carrier)!.flights/12480);
  const total = Math.round(selection.reduce((s,a) => s+a.flights,0)*factor);
  const rate = selection.reduce((s,a) => s+a.rate*a.flights,0)/selection.reduce((s,a) => s+a.flights,0)*carrierRate;
  const delayed = Math.round(total*rate/100);
  const avg = selection.reduce((s,a) => s+a.delay*a.flights,0)/selection.reduce((s,a) => s+a.flights,0);

  // Dữ liệu cho trang Dự báo
  const scoped = predictions.filter(p => (airport === "all" || p.origin === airport) && (carrier === "all" || p.carrier === carrier));
  const filtered = scoped.filter(p => (risk === "all" || riskOf(p.probability) === risk) && `${p.flight} ${p.origin} ${p.destination}`.toLowerCase().includes(search.toLowerCase())).sort((a,b) => sort === "risk" ? b.probability-a.probability : sort === "delay" ? b.delay-a.delay : a.time.localeCompare(b.time));
  const highCount = scoped.filter(p => riskOf(p.probability) === "high").length;
  const forecastAvg = scoped.length ? scoped.reduce((s,p) => s+p.delay,0)/scoped.length : 0;
  const meanProbability = scoped.length ? scoped.reduce((s,p) => s+p.probability,0)/scoped.length : 0;

  // Dữ liệu cho trang Danh sách Chuyến bay (FE · Chuyến bay - STT 15)
  const activeFlightSource: FlightItem[] = apiMode !== "demo" && liveFlights !== null ? liveFlights : demoFlights;
  const uniqueOrigins = Array.from(new Set(activeFlightSource.map(f => f.origin))).sort();
  const uniqueDests = Array.from(new Set(activeFlightSource.map(f => f.dest))).sort();
  const uniqueCarriers = Array.from(new Set(activeFlightSource.map(f => f.op_unique_carrier))).sort();

  const scopedFlights = activeFlightSource.filter(
    f =>
      (airport === "all" || f.origin === airport) &&
      (destAirport === "all" || f.dest === destAirport) &&
      (carrier === "all" || f.op_unique_carrier === carrier)
  );
  const filteredFlights = scopedFlights
    .filter(
      f =>
        (flightStatus === "all" || f.delay_status === flightStatus) &&
        `${f.flight_code} ${f.origin} ${f.dest} ${f.tail_num || ""} ${f.carrier_name}`
          .toLowerCase()
          .includes(search.toLowerCase())
    )
    .sort((a, b) =>
      sort === "delay"
        ? b.delay_minutes - a.delay_minutes
        : sort === "distance"
          ? b.distance - a.distance
          : a.crs_dep_time.localeCompare(b.crs_dep_time)
    );

  const flightsDelayedCount = scopedFlights.filter(f => f.is_delayed === 1 || f.delay_minutes >= 15).length;
  const flightsOnTimeCount = scopedFlights.length - flightsDelayedCount;
  const flightsDelayRate = scopedFlights.length ? (flightsDelayedCount / scopedFlights.length) * 100 : 0;
  const flightsAvgDelay = scopedFlights.length
    ? scopedFlights.reduce((s, f) => s + f.delay_minutes, 0) / scopedFlights.length
    : 0;
  const flightsAvgDistance = scopedFlights.length
    ? scopedFlights.reduce((s, f) => s + f.distance, 0) / scopedFlights.length
    : 0;

  function refresh() {
    if (isFlights) {
      fetchIngestionFlights(false);
      return;
    }
    setBusy(true);
    setTimeout(() => { setUpdated(new Intl.DateTimeFormat("vi-VN",{timeZone:"UTC",hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(new Date())+" · xem lại demo (UTC)"); setBusy(false); notify("Đã tải lại dữ liệu mẫu."); },650);
  }

  function exportCsv() {
    const rows = isFlights
      ? [
          ["flight_code", "fl_date", "carrier", "tail_num", "origin", "dest", "crs_dep_time", "crs_arr_time", "distance_miles", "delay_minutes", "delay_status"],
          ...filteredFlights.map(f => [f.flight_code, f.fl_date, f.op_unique_carrier, f.tail_num || "", f.origin, f.dest, f.crs_dep_time, f.crs_arr_time, f.distance, f.delay_minutes, statusLabels[f.delay_status]]),
        ]
      : forecast
        ? [["flight","origin","destination","departure_local","forecast_date","delay_minutes","delay_probability_percent","risk"],...filtered.map(p => [p.flight,p.origin,p.destination,p.time,"2026-11-07",p.delay,p.probability,riskLabels[riskOf(p.probability)]])]
        : [["airport","date","carrier_filter","flights","delay_rate_percent"],...selection.map(a => [a.code,day,carrier,Math.round(a.flights*factor),(a.rate*carrierRate).toFixed(1)])];
    const blob = new Blob(["\uFEFF"+rows.map(row => row.join(",")).join("\r\n")],{type:"text/csv;charset=utf-8;"});
    const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href=url; link.download=`flightlens-${view}-report.csv`; link.click(); URL.revokeObjectURL(url); notify("Đã xuất CSV theo bộ lọc hiện tại.");
  }

  const pageTitle = isFlights ? "Danh sách chuyến bay" : forecast ? "Dự báo ngày mai" : "Tổng quan chuyến bay";
  const pageEyebrow = isFlights ? "GIÁM SÁT LUỒNG CHUYẾN BAY · INGESTION" : forecast ? "NHÌN TRƯỚC MỘT BƯỚC" : "BỨC TRANH TOÀN CẢNH";
  const pageSubtitle = isFlights
    ? "Tra cứu, tìm kiếm và lọc trạng thái chuyến bay thời gian thực từ luồng Data Simulator."
    : forecast
      ? "Biến dữ liệu hôm nay thành sự chủ động cho ngày mai."
      : "Mọi chuyển động trên bầu trời, trong một góc nhìn.";

  return <div className="app-shell">
    <aside className="sidebar">
      <Link href="/" className="brand"><span className="brand-mark"><Icon name="plane" size={25} /></span><span>flightlens<span className="brand-period">.</span><small>FLIGHT INTELLIGENCE</small></span></Link>
      <div className="workspace"><span className="workspace-icon"><Icon name="globe" /></span><div>US Flight Operations<small>Không gian làm việc</small></div><span className="workspace-chevron"><Icon name="chevron" size={15} /></span></div>
      <div className="nav-label">KHÔNG GIAN PHÂN TÍCH</div>
      <nav aria-label="Điều hướng chính">
        <Link href="/" aria-label="Tổng quan" aria-current={isOverview ? "page" : undefined} className={isOverview ? "nav-item active" : "nav-item"}>
          <Icon name="grid" />Tổng quan{isOverview && <span className="active-dot" />}
        </Link>
        <Link href="/flights" aria-label="Chuyến bay" aria-current={isFlights ? "page" : undefined} className={isFlights ? "nav-item active" : "nav-item"}>
          <Icon name="plane" />Chuyến bay{isFlights ? <span className="active-dot" /> : <span className="nav-new">LIVE</span>}
        </Link>
        <Link href="/forecast" aria-label="Dự báo ngày mai" aria-current={forecast ? "page" : undefined} className={forecast ? "nav-item active" : "nav-item"}>
          <Icon name="spark" />Dự báo ngày mai<span className="nav-new">AI</span>
        </Link>
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-card"><span className="orbit-icon"><Icon name="chart" size={25} /></span><strong>Mỗi chuyến bay,<br />một góc nhìn rõ hơn.</strong><p>Theo dõi hôm nay.<br />Chủ động cho ngày mai.</p><span className="sidebar-card-line" /></div><div className="demo-status"><span className="status-dot" />{apiMode !== "demo" ? `API: ${apiMode.toUpperCase()}` : "Chế độ demo UI"}<span>v1.0</span></div><div className="profile"><span className="avatar">V</span><div>Việt · Flight Team<small>Flight Delay Project</small></div><span className="profile-badge">VN</span></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumbs">Workspace<span>/</span><strong>{pageTitle}</strong></div><div className="topbar-right"><span className="sample-pill">{isFlights && apiMode !== "demo" ? `KẾT NỐI: ${apiMode.toUpperCase()}` : "DỮ LIỆU MẪU"}</span><span className="header-divider" /><Icon name="globe" size={17} /><span>Tiếng Việt</span><span className="mini-avatar">V</span></div></header>
      <main className="main-content">
        <div className="page-heading">
          <div>
            <div className="eyebrow">{pageEyebrow}</div>
            <h1>{pageTitle}<span className="heading-dot">.</span></h1>
            <p>{pageSubtitle}</p>
          </div>
          <div style={{ display: "flex", gap: "10px" }}>
            {isFlights && (
              <button className="button secondary" onClick={triggerIngestionRun} disabled={busy} aria-label="Nạp batch mới từ Simulator">
                <Icon name="refresh" size={17} />Thu thập batch mới (POST /run)
              </button>
            )}
            <button className="button secondary" onClick={exportCsv} aria-label="Xuất báo cáo CSV">
              <Icon name="download" size={17} />Xuất báo cáo
            </button>
          </div>
        </div>

        <div className="filter-bar">
          <div className="filters">
            <div className="filter-control">
              <Icon name="calendar" size={17} />
              {forecast ? (
                <span>Ngày mai · 07/11/2026</span>
              ) : isFlights ? (
                <span>Chu kỳ nạp: 5 phút · Sliding Window</span>
              ) : (
                <select aria-label="Ngày dữ liệu" value={day} onChange={e => setDay(e.target.value)}>
                  <option>06/11/2026</option>
                  <option>05/11/2026</option>
                  <option>04/11/2026</option>
                </select>
              )}
            </div>
            <div className="filter-control">
              <Icon name="plane" size={17} />
              <select aria-label="Sân bay đi" value={airport} onChange={e => setAirport(e.target.value)}>
                <option value="all">Tất cả sân bay đi</option>
                {isFlights
                  ? uniqueOrigins.map(code => <option key={code} value={code}>Đi từ: {code}</option>)
                  : airports.map(a => <option key={a.code} value={a.code}>{a.code} · {a.city}</option>)}
              </select>
            </div>
            {isFlights && (
              <div className="filter-control">
                <select aria-label="Sân bay đến" value={destAirport} onChange={e => setDestAirport(e.target.value)}>
                  <option value="all">Tất cả sân bay đến</option>
                  {uniqueDests.map(code => <option key={code} value={code}>Đến: {code}</option>)}
                </select>
              </div>
            )}
            <div className="filter-control">
              <select aria-label="Hãng bay" value={carrier} onChange={e => setCarrier(e.target.value)}>
                <option value="all">Tất cả hãng bay</option>
                {isFlights
                  ? uniqueCarriers.map(code => <option key={code} value={code}>Hãng: {code}</option>)
                  : carriers.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <button className="refresh-button" onClick={refresh} disabled={busy} aria-label="Làm mới dữ liệu">
            <span className={busy ? "spinning" : ""}><Icon name="refresh" size={16} /></span>{busy ? "Đang tải…" : "Làm mới"}
          </button>
        </div>

        <div className="update-line">
          <span className="status-dot" />
          <span>
            {isFlights && apiMode !== "demo"
              ? <>Nguồn: <strong>API {apiMode.toUpperCase()}</strong> · Cập nhật: <strong>{updated}</strong></>
              : <>Dữ liệu mẫu · Lần cập nhật: <strong>{updated}</strong></>}
          </span>
          <span className="update-divider">|</span>
          <span>
            {isFlights
              ? batchMeta?.window_start !== undefined
                ? `Window [${batchMeta.window_start}..${batchMeta.window_end}] · Mới: +${batchMeta.inserted_count ?? 0} · Đã lọc trùng: ${batchMeta.duplicate_count ?? 0}`
                : "Chu kỳ Ingestion: 5 phút (window=100, slide=20)"
              : forecast
                ? "Phiên bản mô hình minh họa: v1.2"
                : "Chu kỳ cập nhật dự kiến: 5 phút"}
          </span>
        </div>

        {isFlights ? <>
          {apiMode !== "demo" && apiReady === false && (
            <section className="forecast-banner" style={{ background: "#fcf0eb", borderColor: "#f2d6c9" }}>
              <span className="banner-icon" style={{ background: "#f7dfd4", color: "#c96a4a" }}><Icon name="alert" size={26} /></span>
              <div>
                <span className="banner-eyebrow" style={{ color: "#b86b52" }}>TRẠNG THÁI DATABASE · READY = FALSE</span>
                <h2 style={{ color: "#7a3b26" }}>Database hiện đang trống (chưa có dữ liệu chuyến bay).</h2>
                <p style={{ color: "#9c5840" }}>Nhấn nút &ldquo;Thu thập batch mới (POST /run)&rdquo; ở góc phải phía trên để Ingestion gọi Simulator và phục hồi dữ liệu ngay lập tức.</p>
              </div>
            </section>
          )}

          <section className="metrics" aria-label="Chỉ số chuyến bay">
            <Metric
              title="Tổng chuyến bay hiển thị"
              value={number(scopedFlights.length)}
              unit="chuyến"
              icon="plane"
              note={batchMeta?.total_stored ? `Tổng lưu trong DB: ${number(batchMeta.total_stored)} chuyến` : "Theo bộ lọc sân bay & hãng hiện tại"}
            />
            <Metric
              title="Đúng giờ (< 15 phút)"
              value={number(flightsOnTimeCount)}
              unit="chuyến"
              icon="check"
              note={`Chiếm ${(100 - flightsDelayRate).toFixed(1)}% tổng số chuyến`}
              color="teal"
            />
            <Metric
              title="Chuyến bay trễ (≥ 15 phút)"
              value={number(flightsDelayedCount)}
              unit={`(${flightsDelayRate.toFixed(1)}%)`}
              icon="alert"
              note="Bao gồm trễ nhẹ và trễ nghiêm trọng"
              color="coral"
            />
            <Metric
              title="Độ trễ / Cự ly trung bình"
              value={flightsAvgDelay.toFixed(1)}
              unit="phút"
              icon="clock"
              note={`Cự ly bay TB: ${number(Math.round(flightsAvgDistance))} dặm`}
              color="purple"
            />
          </section>

          <div className="forecast-charts">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Mức độ trễ trung bình theo hãng hàng không</h2>
                  <p>Tổng hợp trực tiếp từ danh sách chuyến bay đang lọc</p>
                </div>
                <span className="chart-unit">ĐƠN VỊ: PHÚT</span>
              </div>
              <div className="airport-bars">
                {(uniqueCarriers.length ? uniqueCarriers.slice(0, 8) : ["AA", "DL", "UA", "WN"]).map(code => {
                  const rows = scopedFlights.filter(f => f.op_unique_carrier === code);
                  const val = rows.length ? rows.reduce((s, f) => s + f.delay_minutes, 0) / rows.length : 0;
                  return (
                    <div className="airport-bar" key={code}>
                      <span className="airport-bar-value">{rows.length ? val.toFixed(1) : "—"}</span>
                      <div className="airport-bar-track">
                        <div style={{ height: `${Math.min(100, (val / 45) * 100)}%` }} className={val >= 20 ? "bar-coral" : "bar-teal"} />
                      </div>
                      <strong>{code}</strong>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="panel risk-panel">
              <div className="panel-heading">
                <div>
                  <h2>Phân bố trạng thái chuyến bay</h2>
                  <p>Nhấn vào một trạng thái để lọc nhanh danh sách</p>
                </div>
                <Icon name="clock" size={19} />
              </div>
              <div className="risk-distribution">
                {(["on_time", "moderate_delay", "severe_delay"] as const).map(st => {
                  const count = scopedFlights.filter(f => f.delay_status === st).length;
                  const badge = statusBadgeClass[st];
                  return (
                    <button
                      className={`risk-row ${flightStatus === st ? "selected" : ""}`}
                      key={st}
                      onClick={() => setFlightStatus(flightStatus === st ? "all" : st)}
                      aria-pressed={flightStatus === st}
                    >
                      <span className={`risk-symbol ${badge}`}>
                        <Icon name={st === "severe_delay" ? "alert" : st === "on_time" ? "check" : "clock"} size={18} />
                      </span>
                      <span className="risk-row-text">
                        <strong>{statusLabels[st]}</strong>
                        <small>
                          {st === "on_time"
                            ? "Khởi hành đúng lịch trình hoặc trễ dưới 15 phút"
                            : st === "moderate_delay"
                              ? "Trễ từ 15 đến 44 phút"
                              : "Trễ từ 45 phút trở lên"}
                        </small>
                      </span>
                      <strong>{count}<small>chuyến</small></strong>
                      <span
                        className={`risk-mini-bar ${badge}`}
                        style={{ width: `${scopedFlights.length ? (count / scopedFlights.length) * 100 : 0}%` }}
                      />
                    </button>
                  );
                })}
              </div>
              <div className="panel-footnote">Cơ chế chống trùng lặp (Deduplication) tự động loại bỏ các chuyến bay trùng khi cửa sổ trượt.</div>
            </section>
          </div>

          <section className="panel predictions-panel">
            <div className="panel-heading">
              <div>
                <h2>Danh sách chi tiết chuyến bay <span className="count-pill">{filteredFlights.length}</span></h2>
                <p>Tìm kiếm theo mã chuyến bay, số hiệu tàu bay (Tail Num), sân bay đi/đến hoặc lọc theo trạng thái trễ</p>
              </div>
              <div className="table-tools">
                <label className="search-box">
                  <Icon name="search" size={16} />
                  <input
                    placeholder="Tìm chuyến bay, tàu bay, sân bay…"
                    aria-label="Tìm chuyến bay"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                  />
                </label>
                <select aria-label="Lọc trạng thái" value={flightStatus} onChange={e => setFlightStatus(e.target.value)}>
                  <option value="all">Tất cả trạng thái</option>
                  <option value="on_time">Đúng giờ (&lt; 15p)</option>
                  <option value="moderate_delay">Trễ nhẹ (15–44p)</option>
                  <option value="severe_delay">Trễ nặng (≥ 45p)</option>
                </select>
                <select aria-label="Sắp xếp" value={sort} onChange={e => setSort(e.target.value)}>
                  <option value="time">Giờ khởi hành</option>
                  <option value="delay">Độ trễ giảm dần</option>
                  <option value="distance">Cự ly giảm dần</option>
                </select>
              </div>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>CHUYẾN BAY</th>
                    <th>TÀU BAY (TAIL)</th>
                    <th>NGÀY BAY</th>
                    <th>HÀNH TRÌNH</th>
                    <th>GIỜ ĐI / ĐẾN (CRS)</th>
                    <th>CỰ LY / THỜI GIAN</th>
                    <th>MỨC ĐỘ DELAY</th>
                    <th>TRẠNG THÁI</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFlights.map(f => {
                    const badge = statusBadgeClass[f.delay_status];
                    return (
                      <tr key={f.flight_key}>
                        <td>
                          <span className={`airline-mark airline-${f.op_unique_carrier}`}>{f.op_unique_carrier}</span>
                          <strong>{f.flight_code}</strong>
                        </td>
                        <td className="tabular">{f.tail_num || "—"}</td>
                        <td className="tabular">{f.fl_date}</td>
                        <td>
                          <span className="route">
                            <strong>{f.origin}</strong>
                            <Icon name="arrow" size={15} />
                            <strong>{f.dest}</strong>
                          </span>
                        </td>
                        <td className="tabular">
                          {f.crs_dep_time} <span className="muted">→</span> {f.crs_arr_time}
                        </td>
                        <td className="tabular">
                          {number(Math.round(f.distance))} <span className="muted">dặm ({Math.round(f.crs_elapsed_time)}p)</span>
                        </td>
                        <td>
                          <strong className={f.delay_minutes >= 15 ? "coral-text" : ""}>
                            +{f.delay_minutes}
                          </strong>
                          <span className="muted"> phút</span>
                        </td>
                        <td>
                          <span className={`risk-badge ${badge}`}>
                            <span />
                            {statusLabels[f.delay_status]}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {!filteredFlights.length && (
                <div className="empty-state">
                  <Icon name="search" size={30} />
                  <h3>Không có chuyến bay phù hợp</h3>
                  <p>
                    {apiMode !== "demo" && apiReady === false
                      ? "Database hiện đang trống. Nhấn nút 'Thu thập batch mới (POST /run)' để nạp dữ liệu từ Simulator."
                      : "Thử từ khóa tìm kiếm khác hoặc đặt lại bộ lọc."}
                  </p>
                  <button
                    className="button secondary"
                    onClick={() => {
                      setAirport("all");
                      setDestAirport("all");
                      setCarrier("all");
                      setFlightStatus("all");
                      setSearch("");
                    }}
                  >
                    Đặt lại bộ lọc
                  </button>
                </div>
              )}
            </div>

            <div className="table-footer">
              Hiển thị {filteredFlights.length} / {scopedFlights.length} chuyến bay trong phạm vi đã chọn
              <span>
                {apiMode !== "demo"
                  ? `Kết nối trực tiếp API (${apiMode})`
                  : "Chế độ dữ liệu mẫu · Tự động chuyển sang API thật khi bật backend"}
              </span>
            </div>
          </section>
        </> : forecast ? <>
          <section className="forecast-banner"><span className="banner-icon"><Icon name="spark" size={26} /></span><div><span className="banner-eyebrow">DỰ BÁO CHO THỨ BẢY, 07 THÁNG 11</span><h2>Sẵn sàng cho hành trình ngày mai.</h2><p>Nhận diện sớm chuyến bay có nguy cơ trễ để chủ động lên kế hoạch.</p></div><div className="banner-date"><strong>07</strong><span>THÁNG 11, 2026</span></div><span className="banner-orbit" /></section>
          <section className="metrics" aria-label="Chỉ số dự báo"><Metric title="Chuyến bay được dự báo" value={number(scoped.length)} unit="chuyến" icon="plane" note="Trong phạm vi dữ liệu mẫu" /><Metric title="Delay dự kiến trung bình" value={forecastAvg.toFixed(1)} unit="phút" icon="clock" note="Trung bình các chuyến đã lọc" color="blue" /><Metric title="Chuyến bay nguy cơ cao" value={number(highCount)} unit="chuyến" icon="alert" note="Xác suất trễ từ 60%" color="coral" /><Metric title="Xác suất trễ trung bình" value={meanProbability.toFixed(1)} unit="%" icon="chart" note="Trung bình xác suất phân loại" color="purple" /></section>
          <div className="forecast-charts"><section className="panel"><div className="panel-heading"><div><h2>Delay dự kiến theo sân bay</h2><p>Số phút trễ trung bình tại sân bay khởi hành</p></div><span className="chart-unit">ĐƠN VỊ: PHÚT</span></div><div className="airport-bars">{selection.map(a => { const rows=scoped.filter(p => p.origin===a.code); const value=rows.length ? rows.reduce((s,p) => s+p.delay,0)/rows.length : 0; return <div className="airport-bar" key={a.code}><span className="airport-bar-value">{rows.length ? value.toFixed(1) : "—"}</span><div className="airport-bar-track"><div style={{height:`${value/45*100}%`}} className={value>=28 ? "bar-coral" : "bar-teal"} /></div><strong>{a.code}</strong></div>; })}</div></section><section className="panel risk-panel"><div className="panel-heading"><div><h2>Phân bố nguy cơ</h2><p>Xác suất chuyến bay trễ ≥ 15 phút</p></div><Icon name="spark" size={19} /></div><div className="risk-distribution">{(["high","medium","low"] as const).map(r => { const count=scoped.filter(p => riskOf(p.probability)===r).length; return <button className={`risk-row ${risk===r ? "selected" : ""}`} key={r} onClick={() => setRisk(risk===r ? "all" : r)} aria-pressed={risk===r}><span className={`risk-symbol ${r}`}><Icon name={r==="high" ? "alert" : r==="low" ? "check" : "clock"} size={18} /></span><span className="risk-row-text"><strong>{riskLabels[r]}</strong><small>{r==="high" ? "≥ 60%" : r==="medium" ? "30% – dưới 60%" : "Dưới 30%"}</small></span><strong>{count}<small>chuyến</small></strong><span className={`risk-mini-bar ${r}`} style={{width:`${scoped.length ? count/scoped.length*100 : 0}%`}} /></button>; })}</div><div className="panel-footnote">Chọn một nhóm để lọc danh sách bên dưới.</div></section></div>
          <section className="panel predictions-panel"><div className="panel-heading"><div><h2>Chi tiết dự báo <span className="count-pill">{filtered.length}</span></h2><p>Ngày 07/11/2026 · Giờ khởi hành theo địa phương sân bay</p></div><div className="table-tools"><label className="search-box"><Icon name="search" size={16} /><input placeholder="Tìm chuyến bay, sân bay…" aria-label="Tìm chuyến bay" value={search} onChange={e => setSearch(e.target.value)} /></label><select aria-label="Lọc nguy cơ" value={risk} onChange={e => setRisk(e.target.value)}><option value="all">Tất cả nguy cơ</option><option value="high">Nguy cơ cao</option><option value="medium">Trung bình</option><option value="low">Nguy cơ thấp</option></select><select aria-label="Sắp xếp" value={sort} onChange={e => setSort(e.target.value)}><option value="time">Giờ khởi hành</option><option value="risk">Nguy cơ giảm dần</option><option value="delay">Delay giảm dần</option></select></div></div><div className="table-scroll"><table><thead><tr><th>CHUYẾN BAY</th><th>HÀNH TRÌNH</th><th>KHỞI HÀNH</th><th>DELAY DỰ KIẾN</th><th>XÁC SUẤT TRỄ</th><th>PHÂN LOẠI NGUY CƠ</th></tr></thead><tbody>{filtered.map(p => <tr key={p.flight}><td><span className={`airline-mark airline-${p.carrier}`}>{p.carrier}</span><strong>{p.flight}</strong></td><td><span className="route">{p.origin}<Icon name="arrow" size={15} />{p.destination}</span></td><td className="tabular">{p.time}</td><td><strong className={p.delay>=30 ? "coral-text" : ""}>+{p.delay}</strong><span className="muted"> phút</span></td><td><div className="probability"><span>{p.probability}%</span><div><span className={riskOf(p.probability)} style={{width:`${p.probability}%`}} /></div></div></td><td><span className={`risk-badge ${riskOf(p.probability)}`}><span />{riskLabels[riskOf(p.probability)]}</span></td></tr>)}</tbody></table>{!filtered.length && <div className="empty-state"><Icon name="search" size={30} /><h3>Không có chuyến bay phù hợp</h3><p>Thử tìm kiếm khác hoặc đặt lại bộ lọc.</p><button className="button secondary" onClick={() => {setAirport("all");setCarrier("all");setSearch("");setRisk("all");}}>Đặt lại bộ lọc</button></div>}</div><div className="table-footer">Hiển thị {filtered.length} / {scoped.length} chuyến trong phạm vi đã chọn<span>Kết quả minh họa · Chưa chạy mô hình thực tế</span></div></section>
        </> : <>
          <section className="metrics" aria-label="Chỉ số tổng quan"><Metric title="Tổng chuyến bay" value={number(total)} icon="plane" note={`${selection.length} sân bay trong phạm vi theo dõi`} /><Metric title="Tỷ lệ chuyến bay trễ" value={rate.toFixed(1)} unit="%" icon="chart" note="Quy ước demo: trễ từ 15 phút" color="coral" /><Metric title="Số chuyến bay trễ" value={number(delayed)} unit="chuyến" icon="clock" note="Theo ngày và bộ lọc đã chọn" color="blue" /><Metric title="Delay trung bình" value={avg.toFixed(1)} unit="phút" icon="clock" note="Trung bình trên tất cả chuyến bay" color="purple" /></section>
          <div className="overview-charts"><section className="panel"><div className="panel-heading"><div><h2>Nhịp bay trong ngày</h2><p>Biến động tỷ lệ chuyến bay trễ theo giờ · UTC</p></div><span className="legend"><i />Tỷ lệ trễ</span></div><TrendChart rate={rate} day={day} /><div className="chart-caption"><Icon name="clock" size={15} /><span>Dữ liệu biểu đồ minh họa cho ngày {day}</span></div></section><section className="panel donut-panel"><div className="panel-heading"><div><h2>Trạng thái chuyến bay</h2><p>Tỷ trọng theo dữ liệu đã lọc</p></div></div><div className="donut" style={{background:`conic-gradient(#0b9d87 0 ${100-rate}%, #f3aa77 ${100-rate}% 100%)`}} role="img" aria-label={`${(100-rate).toFixed(1)}% đúng giờ, ${rate.toFixed(1)}% trễ`}><div><span>Đúng giờ</span><strong>{(100-rate).toFixed(1)}<small>%</small></strong><span className="donut-check"><Icon name="check" size={13} />Đang theo dõi</span></div></div><div className="donut-legend"><div><i className="teal-bg" /><span>Đúng giờ / sớm</span><strong>{number(total-delayed)}</strong></div><div><i className="orange-bg" /><span>Trễ ≥ 15 phút</span><strong>{number(delayed)}</strong></div></div></section></div>
          <div className="bottom-grid"><section className="panel ranking-panel"><div className="panel-heading"><div><h2>Điểm nóng chậm chuyến</h2><p>Xếp hạng theo tỷ lệ trễ giảm dần</p></div><div className="segmented"><button className={rankBy==="airports" ? "selected" : ""} onClick={() => setRankBy("airports")}>Sân bay</button><button className={rankBy==="carriers" ? "selected" : ""} onClick={() => setRankBy("carriers")}>Hãng bay</button></div></div><div className="ranking-list">{(rankBy==="airports" ? selection.map(a => ({...a,rate:a.rate*carrierRate})) : carriers.filter(c => carrier==="all" || c.code===carrier)).slice(0,5).map((a,i) => <div className="ranking-row" key={a.code}><span className="rank-number">{String(i+1).padStart(2,"0")}</span><div className="airport-code">{a.code}</div><div className="ranking-name"><strong>{a.name}</strong><span>{rankBy==="airports" ? "Sân bay quốc tế" : "Hãng hàng không"}</span></div><div className="ranking-track"><div style={{width:`${a.rate/40*100}%`}} /></div><strong className="rank-rate">{a.rate.toFixed(1)}<small>%</small></strong></div>)}</div><div className="panel-footnote">Phạm vi xếp hạng: {rankBy==="airports" ? "sân bay đã chọn" : "hãng bay đã chọn, toàn bộ sân bay"} · Dữ liệu demo</div></section><section className="tomorrow-card"><span className="tomorrow-tag"><Icon name="spark" size={15} />GÓC NHÌN NGÀY MAI</span><h2>Hành trình tốt hơn<br />bắt đầu từ dự báo.</h2><p>Khám phá mức delay dự kiến và nguy cơ chậm chuyến cho ngày 07/11/2026.</p><div className="flight-illustration" aria-hidden="true"><span className="flight-code">TODAY</span><span className="flight-dashes" /><span className="flight-plane"><Icon name="plane" size={27} /></span><span className="flight-dashes" /><span className="flight-code">TOMORROW</span></div><Link href="/forecast" className="forecast-link">Khám phá dự báo<Icon name="arrow" size={18} /></Link></section></div>
        </>}
        <footer className="page-footer"><span><strong>flightlens.</strong> Rõ dữ liệu. Chủ động hành trình.</span><span>Mẫu giao diện · US Flight Delay · 2026</span></footer>
      </main>
    </div>{toast && <div className="toast" role="status"><Icon name="check" size={18} />{toast}</div>}
  </div>;
}
