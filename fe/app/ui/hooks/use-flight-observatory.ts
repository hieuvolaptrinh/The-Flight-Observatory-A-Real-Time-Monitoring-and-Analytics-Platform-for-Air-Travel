"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
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
  flightRouteKey,
  riskOf,
  statusLabels,
} from "../flight-types";
import { US_AIRPORT_COORDS } from "../us-airports";

const DIRECT_INGESTION_URLS = ["http://127.0.0.1:2004", "http://localhost:2004"];
const DIRECT_CLUSTERING_URLS = ["http://127.0.0.1:2006", "http://localhost:2006"];
const DIRECT_PREDICTION_URLS = ["http://127.0.0.1:2007", "http://localhost:2007"];

export function useFlightObservatory(view: ViewMode) {
  const isOverview = view === "overview";
  const isFlights = view === "flights";
  const isClustering = view === "clustering";
  const isForecast = view === "forecast";
  const isAnalytics = view === "analytics";

  const [airport, setAirport] = useState("all");
  const [destAirport, setDestAirport] = useState("all");
  const [carrier, setCarrier] = useState("all");
  const [flightSource, setFlightSource] = useState<"airlabs" | "legacy" | "all">("airlabs");
  const [rankBy, setRankBy] = useState<"airports" | "carriers">("airports");
  const [risk, setRisk] = useState("all");
  const [flightStatus, setFlightStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sort, setSort] = useState("time");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [updated, setUpdated] = useState<string | null>(null);
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
  const flightRequest = useRef(0);
  const activeBackendRef = useRef<{ mode: "ingestion" | "gateway"; baseUrl: string } | null>(null);
  const [batchMeta, setBatchMeta] = useState<{
    total_stored?: number;
    window_start?: number;
    window_end?: number;
    inserted_count?: number;
    duplicate_count?: number;
  } | null>(null);

  // K-Means clustering state from PostgreSQL (Clustering Service)
  const [clusterEntityType, setClusterEntityType] = useState<"airport" | "route">(isClustering ? "route" : "airport");
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null);
  const [clusteringMeta, setClusteringMeta] = useState<ClusteringMeta | null>(null);
  const [clusterAssignments, setClusterAssignments] = useState<ClusterAssignment[]>([]);
  const [radarRoutes, setRadarRoutes] = useState<ClusterAssignment[]>([]);
  const [clusteringReady, setClusteringReady] = useState<boolean>(false);

  // Machine Learning delay prediction state (Prediction Service - STT 12 & 13)
  const [mlPredictions, setMlPredictions] = useState<PredictionItem[] | null>(null);
  const [predictionMeta, setPredictionMeta] = useState<Record<string, any> | null>(null);

  // Raw Data Lakehouse state (Bronze Layer - saved AirLabs responses via Ingestion API)
  const [dataLayer, setDataLayer] = useState<"cleaned" | "raw">("cleaned");
  const [rawFlights, setRawFlights] = useState<RawFlightItem[]>([]);
  const [rawLoading, setRawLoading] = useState(false);
  const [rawCursor, setRawCursor] = useState(0);
  const [rawTotal, setRawTotal] = useState(0);
  const rawPageSize = 12;

  const fetchRawFlights = useCallback(async (cursor: number) => {
    setRawLoading(true);
    try {
      const candidates = [
        `${API_BASE}/ingestion/raw?cursor=${cursor}&window_size=${rawPageSize}`,
        `http://127.0.0.1:2004/raw?cursor=${cursor}&window_size=${rawPageSize}`,
        `http://localhost:2004/raw?cursor=${cursor}&window_size=${rawPageSize}`,
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
        setRawTotal(payload.total ?? 0);
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
  }, [airport, destAirport, carrier, flightStatus, debouncedSearch, sort, pageSize, flightSource, selectedClusterId]);

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

  const clusterRun = clusteringMeta?.run?.run_id;
  useEffect(() => {
    if (!isFlights || !clusterRun) return;
    const controller = new AbortController();
    const urls = [`${API_BASE}/clustering/results`, ...DIRECT_CLUSTERING_URLS.map(url => `${url}/results`)];
    async function loadRoutes() {
      for (const url of urls) {
        try {
          const response = await fetch(`${url}?entity_type=route`, { cache: "no-store", signal: controller.signal });
          if (!response.ok) continue;
          const result = await response.json();
          if (!controller.signal.aborted) setRadarRoutes(result.output?.items ?? []);
          return;
        } catch {
          if (controller.signal.aborted) return;
        }
      }
      if (!controller.signal.aborted) setRadarRoutes([]);
    }
    void loadRoutes();
    return () => controller.abort();
  }, [isFlights, clusterRun]);

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
      const requestId = ++flightRequest.current;
      setBusy(true);

      const params = new URLSearchParams({
        limit: String(pageSize),
        offset: String((currentPage - 1) * pageSize),
        sort,
      });
      if (isOverview || isFlights) params.set("source", flightSource);
      if (isOverview) params.set("overview", "true");
      if (isFlights && selectedClusterId !== null) params.set("cluster_id", String(selectedClusterId));
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
          if (requestId !== flightRequest.current) return;
          activeBackendRef.current = { mode: candidate.mode, baseUrl: candidate.baseUrl };
          setApiMode(candidate.mode);
          setApiReady(Boolean(json.ready));
          const items: FlightItem[] = json?.output?.items || [];
          const meta: ServerFlightMeta = json?.output?.metadata || {};
          setLiveFlights(items);
          setServerMeta(meta);

          if (isFlights && pageSize >= 300 && currentPage === 1) {
            setRadarFlights(items);
          } else if (isFlights) {
            setRadarFlights(null);
            const mapParams = new URLSearchParams(params);
            mapParams.set("limit", "300");
            mapParams.set("offset", "0");
            fetch(`${candidate.baseUrl}/flights?${mapParams.toString()}`, { cache: "no-store" })
              .then(r => (r.ok ? r.json() : null))
              .then(mapJson => {
                if (requestId === flightRequest.current && mapJson?.output?.items) {
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
          setUpdated(json.updated_at ?? null);
          setBusy(false);
          if (!silent) {
            notify(
              json.ready
                ? `Đã đồng bộ PostgreSQL: ${items.length}/${meta.filtered_count ?? items.length} chuyến bay (Trang ${currentPage}).`
                : "Chưa có dữ liệu chuyến bay. Hãy đợi lượt nạp tự động."
            );
          }
          return;
        } catch {
          if (activeBackendRef.current?.baseUrl === candidate.baseUrl) {
            activeBackendRef.current = null;
          }
        }
      }

      if (requestId !== flightRequest.current) return;
      setServerMeta(null);
      setApiMode("demo");
      setApiReady(null);
      setBusy(false);
    },
    [airport, destAirport, carrier, flightStatus, debouncedSearch, sort, currentPage, pageSize, notify, isOverview, isFlights, flightSource, selectedClusterId]
  );

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
    notify("Không thể kết nối Clustering Service (port 2006 / Gateway 2002).");
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

  const routeClusterMap = useMemo<Record<string, ClusterAssignment>>(
    () => Object.fromEntries((clusterRun ? radarRoutes : []).map(route => [route.entity_code, route])),
    [clusterRun, radarRoutes]
  );

  const selection: AirportStat[] = (serverMeta?.airport_stats ?? []).map(row => ({
    code: row.code,
    name: US_AIRPORT_COORDS[row.code]?.name ?? row.code,
    city: US_AIRPORT_COORDS[row.code]?.city ?? row.code,
    flights: row.flight_count,
    delay: row.avg_delay ?? 0,
    rate: row.known_count ? row.delayed_count * 100 / row.known_count : null,
  }));
  const carriers: CarrierStat[] = (serverMeta?.carrier_stats ?? []).map(row => ({
    code: row.code,
    name: row.name || row.code,
    flights: row.flight_count,
    rate: row.known_count ? row.delayed_count * 100 / row.known_count : null,
  }));

  const predictions = useMemo<PredictionItem[]>(() => {
    // Prefer real ML predictions from Prediction Service (STT 12 & STT 13)
    if (mlPredictions && mlPredictions.length > 0) {
      return mlPredictions;
    }
    return [];
  }, [mlPredictions]);

  const total = serverMeta?.filtered_count ?? 0;
  const rate = serverMeta?.delay_rate_pct ?? 0;
  const delayed = serverMeta?.delayed_count ?? 0;
  const avg = serverMeta?.avg_delay_minutes ?? 0;

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

  const paginatedFlights = isServerSide ? liveFlights ?? [] : [];
  const mapFlights = isServerSide ? radarFlights ?? paginatedFlights : [];

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
    unknown: serverMeta?.unknown_delay_count ?? 0,
    on_time: isServerSide ? serverMeta.on_time_count : 0,
    moderate_delay: isServerSide ? serverMeta.moderate_delay_count : 0,
    severe_delay: isServerSide ? serverMeta.severe_delay_count : 0,
  };

  const carrierDelayBars =
    isServerSide && serverMeta.carrier_delays?.length ? serverMeta.carrier_delays : [];

  const centroids: ClusterCentroid[] = clusteringMeta?.centroids || [];
  const radarCentroids = centroids.flatMap(centroid => {
    const count = clusteringMeta?.route_cluster_counts?.[centroid.cluster_id] ?? 0;
    const totalRoutes = clusteringMeta?.total_routes ?? 0;
    return count && totalRoutes ? [{ ...centroid, entity_count: count, share_pct: count * 100 / totalRoutes }] : [];
  });

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
            "route_cluster",
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
            routeClusterMap[flightRouteKey(f)]?.short_label || "",
            f.crs_dep_time,
            f.crs_arr_time,
            f.distance,
            f.delay_minutes,
            statusLabels[f.delay_status],
          ]),
        ]
      : [
          ["airport", "flights", "delay_rate_percent", "avg_delay_minutes"],
          ...selection.map(a => [a.code, a.flights, a.rate?.toFixed(1) ?? "", a.delay.toFixed(1)]),
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
  }, [routeClusterMap, isFlights, notify, paginatedFlights, selection, view]);

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
    ? "Theo dõi vị trí trực quan trên bản đồ radar và thông tin chi tiết từng hành trình bay."
    : isClustering
      ? "Phân nhóm và đánh giá đặc trưng vận hành của các sân bay và đường bay trọng điểm."
      : isForecast
        ? "Nhận diện sớm các chuyến bay có xác suất trễ cao bằng Machine Learning để chủ động điều phối."
        : isAnalytics
          ? "Biểu đồ chuỗi thời gian Ngày/Tuần/Tháng, phân bố thời lượng bay, xu hướng, mùa vụ và tương quan Pearson."
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
    flightSource,
    setFlightSource,
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
    routeClusterMap,
    centroids,
    radarCentroids,
    radarRoutes: clusterRun ? radarRoutes : [],

    // Prediction ML state
    predictionMeta,
    mlPredictions,

    // Derived datasets
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
    triggerClusteringRun,
    triggerPredictionRun,
    refresh,
    resetFilters,
    exportCsv,
  };
}
