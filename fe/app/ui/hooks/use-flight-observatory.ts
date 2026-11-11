"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AirportStat,
  CarrierStat,
  ClusterAssignment,
  ClusterCentroid,
  ClusteringMeta,
  FlightItem,
  PredictionItem,
  RawFlightItem,
  RawFlightsResponse,
  ServerFlightMeta,
  ViewMode,
  riskOf,
  statusLabels,
} from "../flight-types";
import { US_AIRPORT_COORDS } from "../us-airports";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8080/api";
const DIRECT_INGESTION_URLS = ["http://127.0.0.1:8004", "http://localhost:8004"];
const DIRECT_CLUSTERING_URLS = ["http://127.0.0.1:8002", "http://localhost:8002"];
const DIRECT_PREDICTION_URLS = ["http://127.0.0.1:8003", "http://localhost:8003"];

export function useFlightObservatory(view: ViewMode) {
  const isOverview = view === "overview";
  const isFlights = view === "flights";
  const isClustering = view === "clustering";
  const isForecast = view === "forecast";
  const isAnalytics = view === "analytics";

  const [airport, setAirport] = useState("all");
  const [destAirport, setDestAirport] = useState("all");
  const [carrier, setCarrier] = useState("all");
  const [day] = useState("06/11/2026");
  const [rankBy, setRankBy] = useState<"airports" | "carriers">("airports");
  const [risk, setRisk] = useState("all");
  const [flightStatus, setFlightStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sort, setSort] = useState("time");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [updated, setUpdated] = useState("Đang đồng bộ...");
  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);

  // Live flight data state from PostgreSQL (Ingestion Service)
  const [liveFlights, setLiveFlights] = useState<FlightItem[] | null>(null);
  const [radarFlights, setRadarFlights] = useState<FlightItem[] | null>(null);
  const [selectedFlightKey, setSelectedFlightKey] = useState<string | null>(null);
  const [autoPollEnabled, setAutoPollEnabled] = useState<boolean>(true);
  const [serverMeta, setServerMeta] = useState<ServerFlightMeta | null>(null);
  const [apiReady, setApiReady] = useState<boolean | null>(null);
  const [apiMode, setApiMode] = useState<"gateway" | "ingestion" | "demo">("demo");
  const activeBackendRef = useRef<{ mode: "ingestion" | "gateway"; baseUrl: string } | null>(null);
  const [batchMeta, setBatchMeta] = useState<{
    total_stored?: number;
    window_start?: number;
    window_end?: number;
    inserted_count?: number;
    duplicate_count?: number;
  } | null>(null);

  // K-Means clustering state from PostgreSQL (Clustering Service)
  const [clusterEntityType, setClusterEntityType] = useState<"airport" | "route">("airport");
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null);
  const [clusteringMeta, setClusteringMeta] = useState<ClusteringMeta | null>(null);
  const [clusterAssignments, setClusterAssignments] = useState<ClusterAssignment[]>([]);
  const [clusteringReady, setClusteringReady] = useState<boolean>(false);

  // Machine Learning delay prediction state (Prediction Service - STT 12 & 13)
  const [mlPredictions, setMlPredictions] = useState<PredictionItem[] | null>(null);
  const [predictionMeta, setPredictionMeta] = useState<Record<string, any> | null>(null);

  // Raw Data Lakehouse state (Bronze Layer - analytics.raw_flights via simulator API)
  const [dataLayer, setDataLayer] = useState<"cleaned" | "raw">("cleaned");
  const [rawFlights, setRawFlights] = useState<RawFlightItem[]>([]);
  const [rawLoading, setRawLoading] = useState(false);
  const [rawCursor, setRawCursor] = useState(0);
  const [rawTotal, setRawTotal] = useState(539719);
  const rawPageSize = 12;

  const fetchRawFlights = useCallback(async (cursor: number) => {
    setRawLoading(true);
    try {
      const candidates = [
        `${API_BASE}/simulator/flights?cursor=${cursor}&window_size=${rawPageSize}`,
        `http://127.0.0.1:2003/flights?cursor=${cursor}&window_size=${rawPageSize}`,
        `http://localhost:2003/flights?cursor=${cursor}&window_size=${rawPageSize}`,
      ];
      let res: Response | null = null;
      for (const url of candidates) {
        try {
          const r = await fetch(url);
          if (r.ok) {
            res = r;
            break;
          }
        } catch {
          // Fall through to next candidate URL
        }
      }
      if (res && res.ok) {
        const payload: RawFlightsResponse = await res.json();
        setRawFlights(payload.data || []);
        if (payload.total) setRawTotal(payload.total);
      }
    } catch (err) {
      console.warn("Could not fetch raw flights:", err);
    } finally {
      setRawLoading(false);
    }
  }, [rawPageSize]);

  useEffect(() => {
    if (dataLayer === "raw") {
      fetchRawFlights(rawCursor);
    }
  }, [dataLayer, rawCursor, fetchRawFlights]);

  const notify = useCallback((message: string) => {
    setToast(message);
    setTimeout(() => setToast(""), 4000);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setCurrentPage(1);
  }, [airport, destAirport, carrier, flightStatus, debouncedSearch, sort, pageSize]);

  // Fetch K-Means clustering results from Gateway or Clustering service
  const fetchClusteringResults = useCallback(
    async (entityType: "airport" | "route" = clusterEntityType) => {
      const urls = [
        `${API_BASE}/clustering/results?entity_type=${entityType}`,
        ...DIRECT_CLUSTERING_URLS.map(u => `${u}/results?entity_type=${entityType}`),
      ];
      for (const url of urls) {
        try {
          const res = await fetch(url, { cache: "no-store" });
          if (!res.ok) continue;
          const json = await res.json();
          setClusteringReady(Boolean(json.ready));
          const items: ClusterAssignment[] = json?.output?.items || [];
          const meta: ClusteringMeta | null = json?.output?.metadata || null;
          setClusterAssignments(items);
          setClusteringMeta(meta);
          return;
        } catch {
          // try next
        }
      }
    },
    [clusterEntityType]
  );

  // Fetch ML delay predictions from Gateway (8080) or Prediction Service (8003)
  const fetchPredictions = useCallback(async () => {
    const urls = [
      `${API_BASE}/prediction/predictions`,
      `${API_BASE}/prediction/results`,
      ...DIRECT_PREDICTION_URLS.map(u => `${u}/predictions`),
    ];
    for (const url of urls) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) continue;
        const json = await res.json();
        const items: PredictionItem[] = json?.output?.items || [];
        if (items.length > 0) {
          setMlPredictions(items);
          setPredictionMeta(json?.output?.metadata || null);
          return;
        }
      } catch {
        // try next candidate
      }
    }
  }, []);

  const fetchIngestionFlights = useCallback(
    async (silent = false, forceRediscover = false) => {
      setBusy(true);

      const params = new URLSearchParams({
        limit: String(pageSize),
        offset: String((currentPage - 1) * pageSize),
        sort,
      });
      if (airport !== "all") params.set("origin", airport);
      if (destAirport !== "all") params.set("dest", destAirport);
      if (carrier !== "all") params.set("carrier", carrier);
      if (flightStatus !== "all") params.set("status", flightStatus);
      if (debouncedSearch.trim()) params.set("search", debouncedSearch.trim());

      const qs = params.toString();

      const ingestionCandidates =
        !forceRediscover &&
        activeBackendRef.current &&
        (activeBackendRef.current.mode === "ingestion" ||
          activeBackendRef.current.mode === "gateway")
          ? [
              {
                mode: activeBackendRef.current.mode,
                baseUrl: activeBackendRef.current.baseUrl,
                url: `${activeBackendRef.current.baseUrl}/flights?${qs}`,
              },
            ]
          : [
              {
                mode: "gateway" as const,
                baseUrl: `${API_BASE}/ingestion`,
                url: `${API_BASE}/ingestion/flights?${qs}`,
              },
              ...DIRECT_INGESTION_URLS.map(u => ({
                mode: "ingestion" as const,
                baseUrl: u,
                url: `${u}/flights?${qs}`,
              })),
            ];

      for (const candidate of ingestionCandidates) {
        try {
          const res = await fetch(candidate.url, { cache: "no-store" });
          if (!res.ok) continue;
          const json = await res.json();
          activeBackendRef.current = { mode: candidate.mode, baseUrl: candidate.baseUrl };
          setApiMode(candidate.mode);
          setApiReady(Boolean(json.ready));
          const items: FlightItem[] = json?.output?.items || [];
          const meta: ServerFlightMeta = json?.output?.metadata || {};
          setLiveFlights(items);
          setServerMeta(meta);

          if (pageSize >= 150 && currentPage === 1) {
            setRadarFlights(items);
          } else {
            const mapParams = new URLSearchParams(params);
            mapParams.set("limit", "300");
            mapParams.set("offset", "0");
            fetch(`${candidate.baseUrl}/flights?${mapParams.toString()}`, { cache: "no-store" })
              .then(r => (r.ok ? r.json() : null))
              .then(mapJson => {
                if (mapJson?.output?.items) {
                  setRadarFlights(mapJson.output.items);
                }
              })
              .catch(() => {});
          }
          setBatchMeta({
            total_stored: meta.total_stored ?? items.length,
            window_start: meta.last_batch?.window_start,
            window_end: meta.last_batch?.window_end,
            inserted_count: meta.last_batch?.inserted_count,
            duplicate_count: meta.last_batch?.duplicate_count,
          });
          if (json.updated_at) {
            setUpdated(
              new Date(json.updated_at).toISOString().replace("T", " ").slice(0, 19) + " UTC"
            );
          }
          setBusy(false);
          if (!silent) {
            notify(
              json.ready
                ? `Đã đồng bộ PostgreSQL: ${items.length}/${meta.filtered_count ?? items.length} chuyến bay (Trang ${currentPage}).`
                : "DB đang trống (ready: false). Hãy nhấn 'Nạp batch mới'!"
            );
          }
          return;
        } catch {
          if (activeBackendRef.current?.baseUrl === candidate.baseUrl) {
            activeBackendRef.current = null;
          }
        }
      }

      setServerMeta(null);
      setApiMode("demo");
      setApiReady(null);
      setBusy(false);
    },
    [airport, destAirport, carrier, flightStatus, debouncedSearch, sort, currentPage, pageSize, notify]
  );

  const triggerIngestionRun = useCallback(async () => {
    setBusy(true);
    const runUrls = [
      `${API_BASE}/ingestion/run`,
      ...DIRECT_INGESTION_URLS.map(u => `${u}/run`),
    ];
    for (const url of runUrls) {
      try {
        const res = await fetch(url, { method: "POST" });
        if (res.ok) {
          activeBackendRef.current = null;
          await fetchIngestionFlights(true, true);
          await fetchClusteringResults();
          notify("Đã chạy POST /run: nạp cửa sổ trượt mới vào PostgreSQL thành công!");
          return;
        }
      } catch {
        // try next
      }
    }
    await fetchIngestionFlights(false, true);
  }, [fetchClusteringResults, fetchIngestionFlights, notify]);

  const triggerClusteringRun = useCallback(async () => {
    setBusy(true);
    const runUrls = [
      `${API_BASE}/clustering/run`,
      ...DIRECT_CLUSTERING_URLS.map(u => `${u}/run`),
    ];
    for (const url of runUrls) {
      try {
        const res = await fetch(url, { method: "POST" });
        if (res.ok) {
          await fetchClusteringResults();
          setBusy(false);
          notify("Đã chạy phân cụm K-Means + PCA(2D) trên dữ liệu DB mới nhất!");
          return;
        }
      } catch {
        // try next
      }
    }
    setBusy(false);
    notify("Không thể kết nối Clustering Service (port 8002 / Gateway 8080).");
  }, [fetchClusteringResults, notify]);

  // Trigger manual ML prediction pipeline run (POST /run)
  const triggerPredictionRun = useCallback(async () => {
    setBusy(true);
    const runUrls = [
      `${API_BASE}/prediction/run`,
      ...DIRECT_PREDICTION_URLS.map(u => `${u}/run`),
    ];
    for (const url of runUrls) {
      try {
        const res = await fetch(url, { method: "POST" });
        if (res.ok) {
          await fetchPredictions();
          setBusy(false);
          notify("Đã hoàn tất tính toán dự báo delay bằng Machine Learning!");
          return;
        }
      } catch {
        // try next
      }
    }
    setBusy(false);
    notify("Không thể kết nối Prediction Service (port 8003 / Gateway 8080).");
  }, [fetchPredictions, notify]);

  useEffect(() => {
    fetchIngestionFlights(true);
    fetchClusteringResults();
    fetchPredictions();
  }, [fetchIngestionFlights, fetchClusteringResults, fetchPredictions]);

  useEffect(() => {
    if (!isFlights || !autoPollEnabled) return;
    const interval = setInterval(() => {
      fetchIngestionFlights(true);
    }, 8000);
    return () => clearInterval(interval);
  }, [isFlights, autoPollEnabled, fetchIngestionFlights]);

  // Periodic auto-polling for ML Delay Predictions (/forecast) every 15 seconds
  useEffect(() => {
    if (!isForecast || !autoPollEnabled) return;
    const interval = setInterval(() => {
      fetchPredictions();
    }, 15000);
    return () => clearInterval(interval);
  }, [isForecast, autoPollEnabled, fetchPredictions]);

  // Fast lookup map: airport code -> K-Means cluster info
  const airportClusterMap = useMemo<Record<string, ClusterAssignment>>(() => {
    const map: Record<string, ClusterAssignment> = {};
    for (const item of clusterAssignments) {
      if (item.entity_type === "airport") {
        map[item.entity_code] = item;
      }
    }
    return map;
  }, [clusterAssignments]);

  const dbSourceFlights: FlightItem[] = radarFlights?.length ? radarFlights : liveFlights || [];

  const airports = useMemo<AirportStat[]>(() => {
    const byOrigin = new Map<string, { flights: number; delayed: number; delaySum: number }>();
    for (const f of dbSourceFlights) {
      const cur = byOrigin.get(f.origin) || { flights: 0, delayed: 0, delaySum: 0 };
      cur.flights += 1;
      if (f.is_delayed === 1 || f.delay_minutes >= 15) cur.delayed += 1;
      cur.delaySum += f.delay_minutes || 0;
      byOrigin.set(f.origin, cur);
    }
    return Array.from(byOrigin.entries())
      .map(([code, st]) => ({
        code,
        name: US_AIRPORT_COORDS[code]?.name || code,
        city: US_AIRPORT_COORDS[code]?.city || code,
        flights: st.flights,
        rate: st.flights ? (st.delayed / st.flights) * 100 : 0,
        delay: st.flights ? st.delaySum / st.flights : 0,
      }))
      .sort((a, b) => b.flights - a.flights)
      .slice(0, 12);
  }, [dbSourceFlights]);

  const carriers = useMemo<CarrierStat[]>(() => {
    const byCarrier = new Map<string, { name: string; flights: number; delayed: number }>();
    for (const f of dbSourceFlights) {
      const cur = byCarrier.get(f.op_unique_carrier) || {
        name: f.carrier_name || f.op_unique_carrier,
        flights: 0,
        delayed: 0,
      };
      cur.flights += 1;
      if (f.is_delayed === 1 || f.delay_minutes >= 15) cur.delayed += 1;
      byCarrier.set(f.op_unique_carrier, cur);
    }
    return Array.from(byCarrier.entries()).map(([code, st]) => ({
      code,
      name: st.name,
      flights: st.flights,
      rate: st.flights ? (st.delayed / st.flights) * 100 : 0,
    }));
  }, [dbSourceFlights]);

  const predictions = useMemo<PredictionItem[]>(() => {
    // Prefer real ML predictions from Prediction Service (STT 12 & STT 13)
    if (mlPredictions && mlPredictions.length > 0) {
      return mlPredictions;
    }
    // Fallback: estimate from live database flights if prediction service is offline
    return dbSourceFlights.slice(0, 50).map(f => {
      const prob = Math.min(96, Math.max(8, Math.round(18 + f.delay_minutes * 1.35)));
      return {
        flight: f.flight_code,
        carrier: f.op_unique_carrier,
        origin: f.origin,
        destination: f.dest,
        time: f.crs_dep_time,
        delay: Math.round(f.delay_minutes),
        probability: prob,
      };
    });
  }, [mlPredictions, dbSourceFlights]);

  const selection = airports.filter(a => airport === "all" || a.code === airport);
  const foundCarrier = carriers.find(c => c.code === carrier);
  const carrierRate = carrier === "all" || !foundCarrier ? 1 : foundCarrier.rate / 20;
  const sumSelectionFlights = selection.reduce((s, a) => s + a.flights, 0);
  const total = serverMeta?.total_stored ?? sumSelectionFlights;
  const rate =
    serverMeta?.delay_rate_pct ??
    (sumSelectionFlights
      ? (selection.reduce((s, a) => s + a.rate * a.flights, 0) / sumSelectionFlights) * carrierRate
      : 0);
  const delayed = serverMeta?.delayed_count ?? Math.round((total * rate) / 100);
  const avg =
    serverMeta?.avg_delay_minutes ??
    (sumSelectionFlights
      ? selection.reduce((s, a) => s + a.delay * a.flights, 0) / sumSelectionFlights
      : 0);

  const scoped = predictions.filter(
    p => (airport === "all" || p.origin === airport) && (carrier === "all" || p.carrier === carrier)
  );
  const filteredPredictions = scoped
    .filter(
      p =>
        (risk === "all" || riskOf(p.probability) === risk) &&
        `${p.flight} ${p.origin} ${p.destination}`.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) =>
      sort === "risk"
        ? b.probability - a.probability
        : sort === "delay"
          ? b.delay - a.delay
          : a.time.localeCompare(b.time)
    );
  const highCount = scoped.filter(p => riskOf(p.probability) === "high").length;
  const forecastAvg = scoped.length ? scoped.reduce((s, p) => s + p.delay, 0) / scoped.length : 0;
  const meanProbability = scoped.length
    ? scoped.reduce((s, p) => s + p.probability, 0) / scoped.length
    : 0;

  const isServerSide = (apiMode === "ingestion" || apiMode === "gateway") && serverMeta !== null;
  const uniqueOrigins = isServerSide ? serverMeta.available_filters?.origins || [] : [];
  const uniqueDests = isServerSide ? serverMeta.available_filters?.destinations || [] : [];
  const uniqueCarriers = isServerSide ? serverMeta.available_filters?.carriers || [] : [];

  const totalFilteredCount = isServerSide ? serverMeta.filtered_count : 0;
  const totalPages = Math.max(1, Math.ceil(totalFilteredCount / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * pageSize;

  const rawPaginatedFlights: FlightItem[] = isServerSide ? liveFlights || [] : [];
  const paginatedFlights: FlightItem[] =
    selectedClusterId === null
      ? rawPaginatedFlights
      : rawPaginatedFlights.filter(
          f =>
            airportClusterMap[f.origin]?.cluster_id === selectedClusterId ||
            airportClusterMap[f.dest]?.cluster_id === selectedClusterId
        );

  const mapFlights: FlightItem[] = useMemo(() => {
    if (!isServerSide) return [];
    const base = radarFlights && radarFlights.length ? radarFlights : rawPaginatedFlights;
    const seen = new Set(base.map(f => f.flight_key));
    const merged = [...base];
    for (const f of rawPaginatedFlights) {
      if (!seen.has(f.flight_key)) {
        merged.unshift(f);
        seen.add(f.flight_key);
      }
    }
    return merged.slice(0, 300);
  }, [isServerSide, radarFlights, rawPaginatedFlights]);

  const pageNumbers = useMemo(() => {
    const pages: (number | "...")[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (safePage > 3) pages.push("...");
      const start = Math.max(2, safePage - 1);
      const end = Math.min(totalPages - 1, safePage + 1);
      for (let i = start; i <= end; i++) pages.push(i);
      if (safePage < totalPages - 2) pages.push("...");
      pages.push(totalPages);
    }
    return pages;
  }, [safePage, totalPages]);

  const flightsDelayedCount = isServerSide ? serverMeta.delayed_count : 0;
  const flightsOnTimeCount = isServerSide ? serverMeta.on_time_count : 0;
  const flightsDelayRate = isServerSide ? serverMeta.delay_rate_pct : 0;
  const flightsAvgDelay = isServerSide ? serverMeta.avg_delay_minutes : 0;
  const flightsAvgDistance = isServerSide ? serverMeta.avg_distance : 0;

  const statusCounts: Record<FlightItem["delay_status"], number> = {
    on_time: isServerSide ? serverMeta.on_time_count : 0,
    moderate_delay: isServerSide ? serverMeta.moderate_delay_count : 0,
    severe_delay: isServerSide ? serverMeta.severe_delay_count : 0,
  };

  const carrierDelayBars =
    isServerSide && serverMeta.carrier_delays?.length ? serverMeta.carrier_delays : [];

  const centroids: ClusterCentroid[] = clusteringMeta?.centroids || [];

  const refresh = useCallback(() => {
    fetchIngestionFlights(false, true);
    fetchClusteringResults();
  }, [fetchClusteringResults, fetchIngestionFlights]);

  const resetFilters = useCallback(() => {
    setAirport("all");
    setDestAirport("all");
    setCarrier("all");
    setFlightStatus("all");
    setSelectedClusterId(null);
    setSearch("");
  }, []);

  const exportCsv = useCallback(() => {
    const rows = isFlights
      ? [
          [
            "flight_code",
            "fl_date",
            "carrier",
            "tail_num",
            "origin",
            "dest",
            "origin_cluster",
            "crs_dep_time",
            "crs_arr_time",
            "distance_miles",
            "delay_minutes",
            "delay_status",
          ],
          ...paginatedFlights.map(f => [
            f.flight_code,
            f.fl_date,
            f.op_unique_carrier,
            f.tail_num || "",
            f.origin,
            f.dest,
            airportClusterMap[f.origin]?.short_label || "",
            f.crs_dep_time,
            f.crs_arr_time,
            f.distance,
            f.delay_minutes,
            statusLabels[f.delay_status],
          ]),
        ]
      : [
          ["airport", "flights", "delay_rate_percent", "avg_delay_minutes"],
          ...selection.map(a => [a.code, a.flights, a.rate.toFixed(1), a.delay.toFixed(1)]),
        ];
    const blob = new Blob(["\uFEFF" + rows.map(row => row.join(",")).join("\r\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `flightlens-${view}-report.csv`;
    link.click();
    URL.revokeObjectURL(url);
    notify("Đã xuất báo cáo CSV theo bộ lọc hiện tại.");
  }, [airportClusterMap, isFlights, notify, paginatedFlights, selection, view]);

  const pageTitle = isFlights
    ? "Giám sát Radar & Luồng Chuyến bay"
    : isClustering
      ? "Phân cụm K-Means & Không gian PCA 2D"
      : isForecast
        ? "Dự báo Rủi ro Trễ Chuyến bay"
        : isAnalytics
          ? "Phân tích Thống kê Chuỗi thời gian & Tương quan"
          : "Tổng quan Không lưu Hoa Kỳ";

  const pageSubtitle = isFlights
    ? "Quan sát đồng bộ Bản đồ Radar thời gian thực (65%), Phân cụm K-Means & Biểu đồ tương quan (35%) cùng truy vấn SQL Server-side."
    : isClustering
      ? "Phân tích chuyên sâu 4 cụm sân bay & tuyến bay Hoa Kỳ bằng thuật toán K-Means + StandardScaler + PCA(2D)."
      : isForecast
        ? "Nhận diện sớm các chuyến bay có xác suất trễ cao bằng Machine Learning để chủ động điều phối."
        : isAnalytics
          ? "Biểu đồ chuỗi thời gian Ngày/Tuần/Tháng, phân bố thời lượng bay, xu hướng Moving Average 7 ngày và tương quan Pearson."
          : "Tổng hợp trực tiếp lưu lượng, tỷ lệ chậm chuyến và điểm nóng sân bay từ PostgreSQL.";

  return {
    isOverview,
    isFlights,
    isClustering,
    isForecast,
    isAnalytics,
    pageTitle,
    pageSubtitle,

    // Filter state
    airport,
    setAirport,
    destAirport,
    setDestAirport,
    carrier,
    setCarrier,
    day,
    rankBy,
    setRankBy,
    risk,
    setRisk,
    flightStatus,
    setFlightStatus,
    search,
    setSearch,
    sort,
    setSort,
    currentPage,
    setCurrentPage,
    pageSize,
    setPageSize,
    updated,
    toast,
    busy,
    notify,

    // Flights & Radar state
    selectedFlightKey,
    setSelectedFlightKey,
    autoPollEnabled,
    setAutoPollEnabled,
    serverMeta,
    apiReady,
    apiMode,
    batchMeta,

    // Clustering state
    clusterEntityType,
    setClusterEntityType,
    selectedClusterId,
    setSelectedClusterId,
    clusteringMeta,
    clusterAssignments,
    clusteringReady,
    airportClusterMap,
    centroids,

    // Prediction ML state
    predictionMeta,
    mlPredictions,

    // Derived datasets
    airports,
    carriers,
    selection,
    total,
    rate,
    delayed,
    avg,
    scoped,
    filteredPredictions,
    highCount,
    forecastAvg,
    meanProbability,
    uniqueOrigins,
    uniqueDests,
    uniqueCarriers,
    totalFilteredCount,
    totalPages,
    safePage,
    startIndex,
    paginatedFlights,
    mapFlights,
    pageNumbers,
    flightsDelayedCount,
    flightsOnTimeCount,
    flightsDelayRate,
    flightsAvgDelay,
    flightsAvgDistance,
    statusCounts,
    carrierDelayBars,

    // Raw Data Lakehouse state
    dataLayer,
    setDataLayer,
    rawFlights,
    rawLoading,
    rawCursor,
    setRawCursor,
    rawTotal,
    rawPageSize,
    fetchRawFlights,

    // Actions
    fetchIngestionFlights,
    fetchClusteringResults,
    fetchPredictions,
    triggerIngestionRun,
    triggerClusteringRun,
    triggerPredictionRun,
    refresh,
    resetFilters,
    exportCsv,
  };
}
