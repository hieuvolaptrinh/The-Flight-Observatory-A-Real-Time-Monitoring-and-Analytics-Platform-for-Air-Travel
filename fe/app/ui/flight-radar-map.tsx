"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type * as LType from "leaflet";
import {
  FlightItem,
  ClusterAssignment,
  CLUSTER_COLORS,
  flightRouteKey,
  statusLabels,
  number,
} from "./flight-types";
import { US_AIRPORT_COORDS, AirportCoord } from "./us-airports";
import { CustomSelect } from "./components/custom-select";

interface FlightRadarMapProps {
  flights: FlightItem[];
  selectedFlightKey: string | null;
  onSelectFlight: (flight: FlightItem | null) => void;
  onQuickFilterAirport?: (iata: string) => void;
  autoPollEnabled: boolean;
  onToggleAutoPoll: () => void;
  apiMode: "gateway" | "ingestion" | "demo";
  totalMatchedCount: number;
  routeClusterMap: Record<string, ClusterAssignment>;
  selectedClusterId: number | null;
}

interface EnrichedFlight {
  item: FlightItem;
  originCoord: AirportCoord;
  destCoord: AirportCoord;
  initialProgress: number;
  durationSec: number;
  depMinutes: number;
  arrMinutes: number;
}

type FlightTimeline = Pick<EnrichedFlight, "initialProgress" | "durationSec"> & { startedAt: number };

function simulatedProgress(timeline: FlightTimeline, nowSec: number) {
  return Math.min(1, timeline.initialProgress + (nowSec - timeline.startedAt) / timeline.durationSec);
}

type MapStyleMode = "navy" | "osm-dark" | "satellite" | "osm";

const FREE_TILE_SOURCES: Record<
  MapStyleMode,
  { baseUrl: string; labelUrl?: string; attribution: string }
> = {
  navy: {
    baseUrl:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    labelUrl:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri, HERE, Garmin, OpenStreetMap",
  },
  "osm-dark": {
    baseUrl: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  },
  satellite: {
    baseUrl:
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    labelUrl:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri, Maxar",
  },
  osm: {
    baseUrl: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  },
};

function parseTimeToMinutes(hhmm: string | null | undefined): number {
  if (!hhmm) return 480;
  const clean = hhmm.trim();
  const parts = clean.split(":");
  if (parts.length === 2) {
    const h = parseInt(parts[0], 10) || 0;
    const m = parseInt(parts[1], 10) || 0;
    return h * 60 + m;
  }
  if (clean.length === 4) {
    const h = parseInt(clean.slice(0, 2), 10) || 0;
    const m = parseInt(clean.slice(2, 4), 10) || 0;
    return h * 60 + m;
  }
  return 480;
}

function escapeTooltipText(value: string | null | undefined) {
  return (value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function formatLongitude(value: number) {
  const normalized = ((value + 540) % 360) - 180;
  return Math.abs(normalized).toFixed(2) + "°" + (normalized < 0 ? "W" : "E");
}

function interpolateCurvedPosition(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
  t: number
): { lat: number; lon: number; bearing: number } {
  const dx = lon2 - lon1;
  const dy = lat2 - lat1;
  const dist = Math.hypot(dx, dy) || 0.001;

  const archFactor = Math.min(0.18, dist * 0.004);
  const midLat = (lat1 + lat2) / 2 + Math.abs(dx) * archFactor;
  const midLon = (lon1 + lon2) / 2;

  const u = 1 - t;
  const lat = u * u * lat1 + 2 * u * t * midLat + t * t * lat2;
  const lon = u * u * lon1 + 2 * u * t * midLon + t * t * lon2;

  const dLat = 2 * (1 - t) * (midLat - lat1) + 2 * t * (lat2 - midLat);
  const dLon = 2 * (1 - t) * (midLon - lon1) + 2 * t * (lon2 - midLon);

  const meanLatRad = ((lat1 + lat2) * 0.5 * Math.PI) / 180;
  const scaledDLon = dLon * Math.cos(meanLatRad);

  const angleRad = Math.atan2(scaledDLon, dLat);
  const bearing = ((angleRad * 180) / Math.PI + 360) % 360;

  return { lat, lon, bearing };
}

function buildCurvePoints(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
  upToT = 1,
  fromT = 0,
  steps = 28
): [number, number][] {
  const pts: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const t = fromT + ((upToT - fromT) * i) / steps;
    const pos = interpolateCurvedPosition(lat1, lon1, lat2, lon2, t);
    pts.push([pos.lat, pos.lon]);
  }
  return pts;
}

export default function FlightRadarMap({
  flights,
  selectedFlightKey,
  onSelectFlight,
  onQuickFilterAirport,
  autoPollEnabled,
  onToggleAutoPoll,
  apiMode,
  totalMatchedCount,
  routeClusterMap,
  selectedClusterId,
}: FlightRadarMapProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<LType.Map | null>(null);
  const leafletRef = useRef<typeof LType | null>(null);
  const baseTileLayerRef = useRef<LType.TileLayer | null>(null);
  const labelTileLayerRef = useRef<LType.TileLayer | null>(null);

  const planeMarkersRef = useRef<
    Map<
      string,
      {
        marker: LType.Marker;
        enriched: EnrichedFlight;
        timeline: FlightTimeline;
        progress: number;
      }
    >
  >(new Map());
  const airportLayerGroupRef = useRef<LType.LayerGroup | null>(null);
  const routeLayerGroupRef = useRef<LType.LayerGroup | null>(null);

  const [mapReady, setMapReady] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [speedMultiplier, setSpeedMultiplier] = useState<1 | 3 | 6>(1);
  const [preferredColorMode, setColorMode] = useState<"status" | "cluster" | "flightaware">("status");
  const colorMode = selectedClusterId === null ? preferredColorMode : "cluster";
  const fittedCluster = useRef<number | null>(null);
  const [mapStyle, setMapStyle] = useState<MapStyleMode>("satellite");
  const [showAirportLabels, setShowAirportLabels] = useState(true);
  const [liveProgress, setLiveProgress] = useState<number>(0.5);
  const [liveCoords, setLiveCoords] = useState<{ lat: number; lon: number; bearing: number }>({
    lat: 38.5,
    lon: -96.5,
    bearing: 90,
  });

  const animClockRef = useRef<number>(0);
  const flightTimelinesRef = useRef(new Map<string, FlightTimeline>());
  const lastFrameTimeRef = useRef<number | null>(null);

  const enrichedFlights = useMemo<EnrichedFlight[]>(() => {
    const list: EnrichedFlight[] = [];
    for (const f of flights) {
      if (selectedClusterId !== null && routeClusterMap[flightRouteKey(f)]?.cluster_id !== selectedClusterId) continue;
      const originCoord = f.origin_coordinate ?? US_AIRPORT_COORDS[f.origin];
      const destination = f.dest_coordinate ?? US_AIRPORT_COORDS[f.dest];
      if (!originCoord || !destination) continue;
      const longitudeDelta = ((destination.lon - originCoord.lon + 540) % 360) - 180;
      const destCoord = { ...destination, lon: originCoord.lon + longitudeDelta };
      if (f.origin === f.dest) continue;


      const depMinutes = parseTimeToMinutes(f.crs_dep_time);
      const arrMinutes = parseTimeToMinutes(f.crs_arr_time);
      const elapsedMin = Math.max(35, f.crs_elapsed_time || 120);

      const effectiveMinuteOfDay = (depMinutes + Math.max(0, f.delay_minutes || 0)) % 1440;
      const initialProgress = Math.max(0.05, Math.min(0.95, effectiveMinuteOfDay / 1440));
      const durationSec = Math.max(55, Math.min(180, elapsedMin * 0.5));

      list.push({
        item: f,
        originCoord,
        destCoord,
        initialProgress,
        durationSec,
        depMinutes,
        arrMinutes,
      });
      if (list.length >= 300) break;
    }
    return list;
  }, [flights, routeClusterMap, selectedClusterId]);

  const activeAirports = useMemo(() => {
    const map = new Map<
      string,
      {
        code: string;
        coord: AirportCoord;
        departures: number;
        arrivals: number;
        delayedCount: number;
      }
    >();

    for (const ef of enrichedFlights) {
      const { origin, dest, delay_status, is_delayed, delay_minutes } = ef.item;
      const delayed = is_delayed === 1 || (delay_minutes ?? 0) >= 15 || delay_status === "moderate_delay" || delay_status === "severe_delay";

      const oEntry = map.get(origin) || {
        code: origin,
        coord: ef.originCoord,
        departures: 0,
        arrivals: 0,
        delayedCount: 0,
      };
      oEntry.departures += 1;
      if (delayed) oEntry.delayedCount += 1;
      map.set(origin, oEntry);

      const dEntry = map.get(dest) || {
        code: dest,
        coord: ef.destCoord,
        departures: 0,
        arrivals: 0,
        delayedCount: 0,
      };
      dEntry.arrivals += 1;
      if (delayed) dEntry.delayedCount += 1;
      map.set(dest, dEntry);
    }

    return Array.from(map.values());
  }, [enrichedFlights]);

  const selectedEnriched = useMemo(
    () => enrichedFlights.find(e => e.item.flight_key === selectedFlightKey) || null,
    [enrichedFlights, selectedFlightKey]
  );

  useEffect(() => {
    if (selectedClusterId === null) {
      fittedCluster.current = null;
      return;
    }
    const map = mapInstanceRef.current;
    if (mapReady && map && enrichedFlights.length && fittedCluster.current !== selectedClusterId) {
      const points = enrichedFlights.flatMap(({ originCoord, destCoord }) =>
        buildCurvePoints(originCoord.lat, originCoord.lon, destCoord.lat, destCoord.lon, 1, 0, 8));
      map.fitBounds(points, { padding: [35, 35], maxZoom: 7, animate: false });
      fittedCluster.current = selectedClusterId;
    }
  }, [enrichedFlights, mapReady, selectedClusterId]);

  const selectedRouteCluster = selectedEnriched ? routeClusterMap[flightRouteKey(selectedEnriched.item)] : undefined;
  const visibleClusters = Array.from(new Map(enrichedFlights.flatMap(({ item }) => {
    const route = routeClusterMap[flightRouteKey(item)];
    return route ? [[route.cluster_id, route] as const] : [];
  })).values()).sort((a, b) => a.cluster_id - b.cluster_id);

  useEffect(() => {
    let mounted = true;

    async function initMap() {
      if (!mapContainerRef.current || mapInstanceRef.current) return;

      if (!document.getElementById("leaflet-css-cdn")) {
        const link = document.createElement("link");
        link.id = "leaflet-css-cdn";
        link.rel = "stylesheet";
        link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
        document.head.appendChild(link);
      }

      const L = await import("leaflet");
      if (!mounted || !mapContainerRef.current) return;
      leafletRef.current = L;

      const map = L.map(mapContainerRef.current, {
        center: [37.8, -96.0],
        zoom: 4,
        minZoom: 1,
        maxZoom: 10,
        zoomControl: false,
        attributionControl: true,
      });

      L.control.zoom({ position: "topright" }).addTo(map);
      L.control.scale({ position: "bottomleft", imperial: true, metric: true }).addTo(map);

      const cfg = FREE_TILE_SOURCES.satellite;
      baseTileLayerRef.current = L.tileLayer(cfg.baseUrl, {
        attribution: cfg.attribution,
        maxZoom: 16,
      }).addTo(map);

      if (cfg.labelUrl) {
        labelTileLayerRef.current = L.tileLayer(cfg.labelUrl, {
          maxZoom: 16,
          opacity: 0.65,
        }).addTo(map);
      }

      airportLayerGroupRef.current = L.layerGroup().addTo(map);
      routeLayerGroupRef.current = L.layerGroup().addTo(map);
      mapInstanceRef.current = map;
      setMapReady(true);

      setTimeout(() => {
        map.invalidateSize();
      }, 150);
    }

    initMap();

    return () => {
      mounted = false;
      setMapReady(false);
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
      planeMarkersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapInstanceRef.current;
    if (!L || !map || !mapReady) return;

    const cfg = FREE_TILE_SOURCES[mapStyle];
    if (baseTileLayerRef.current) {
      baseTileLayerRef.current.setUrl(cfg.baseUrl);
    }

    if (labelTileLayerRef.current) {
      map.removeLayer(labelTileLayerRef.current);
      labelTileLayerRef.current = null;
    }

    if (cfg.labelUrl) {
      labelTileLayerRef.current = L.tileLayer(cfg.labelUrl, {
        maxZoom: 16,
        opacity: 0.65,
      }).addTo(map);
    }
  }, [mapStyle, mapReady]);

  useEffect(() => {
    const L = leafletRef.current;
    const group = airportLayerGroupRef.current;
    if (!L || !group || !mapReady) return;

    group.clearLayers();

    for (const ap of activeAirports) {
      const totalOps = ap.departures + ap.arrivals;
      const delayRatio = totalOps > 0 ? ap.delayedCount / totalOps : 0;
      const dotColor = colorMode === "cluster" || ap.departures === 0
        ? "#ffffff" : delayRatio >= 0.5 ? "#a855f7" : "#10b981";

      const iconHtml = `
        <div class="fa-airport-node">
          <span class="fa-airport-dot" style="background:${dotColor};"></span>
          ${showAirportLabels ? `<span class="fa-airport-code">${ap.code}</span>` : ""}
        </div>
      `;

      const icon = L.divIcon({
        html: iconHtml,
        className: "fa-airport-marker-wrap",
        iconSize: [54, 18],
        iconAnchor: [7, 9],
      });

      const marker = L.marker([ap.coord.lat, ap.coord.lon], {
        icon,
        zIndexOffset: 100,
      });

      marker.bindTooltip(
        `<div style="font-size:11px;line-height:1.45;">
          <strong>${ap.code} · ${escapeTooltipText(ap.coord.name)}</strong><br/>
          <span>Thành phố: ${escapeTooltipText(ap.coord.city)}</span><br/>
          <span>Khởi hành: <b>${ap.departures}</b> · Hạ cánh: <b>${ap.arrivals}</b></span>
        </div>`,
        { direction: "top", offset: [0, -6], className: "fa-map-tooltip" }
      );

      if (onQuickFilterAirport) {
        marker.on("click", () => {
          onQuickFilterAirport(ap.code);
        });
      }

      marker.addTo(group);
    }
  }, [activeAirports, showAirportLabels, onQuickFilterAirport, mapReady, colorMode]);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapInstanceRef.current;
    if (!L || !map || !mapReady) return;

    const currentMarkers = planeMarkersRef.current;
    const nextKeys = new Set(enrichedFlights.map(e => e.item.flight_key));

    for (const [key, entry] of currentMarkers.entries()) {
      if (!nextKeys.has(key)) {
        entry.marker.remove();
        currentMarkers.delete(key);
      }
    }

    const nowSec = animClockRef.current;

    for (const ef of enrichedFlights) {
      const key = ef.item.flight_key;
      const isSelected = key === selectedFlightKey;
      const timeline = flightTimelinesRef.current.get(key) ?? {
        startedAt: nowSec, initialProgress: ef.initialProgress, durationSec: ef.durationSec,
      };
      flightTimelinesRef.current.set(key, timeline);
      const progress = simulatedProgress(timeline, nowSec);
      const pos = interpolateCurvedPosition(
        ef.originCoord.lat,
        ef.originCoord.lon,
        ef.destCoord.lat,
        ef.destCoord.lon,
        progress
      );
      if (isSelected) {
        setLiveProgress(progress);
        setLiveCoords(pos);
      }

      const routeCluster = routeClusterMap[flightRouteKey(ef.item)];
      let planeColor = "#f3c165";
      if (colorMode === "cluster") {
        planeColor = routeCluster ? CLUSTER_COLORS[routeCluster.cluster_id] ?? "#94a3b8" : "#94a3b8";
      } else if (isSelected) {
        planeColor = "#38bdf8";
      } else if (colorMode === "status") {
        if (ef.item.delay_status === "severe_delay") planeColor = "#f87171";
        else if (ef.item.delay_status === "moderate_delay") planeColor = "#fbbf24";
        else planeColor = "#34d399";
      }

      const size = isSelected ? 28 : 21;
      const svgHtml = `
        <div class="fa-plane-rotator ${isSelected ? "selected" : ""}" data-simulation-state="${progress >= 1 ? "arrived" : "flying"}" style="transform: rotate(${pos.bearing.toFixed(1)}deg); color: ${planeColor};">
          <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="currentColor" stroke="#08142c" stroke-width="1">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
          </svg>
        </div>
      `;

      const tooltip = `<div style="font-size:11px;line-height:1.45;">
        <strong>${escapeTooltipText(ef.item.flight_code)}</strong> (${escapeTooltipText(ef.item.carrier_name)})<br/>
        <span><b>${escapeTooltipText(ef.item.origin)}</b> → <b>${escapeTooltipText(ef.item.dest)}</b></span><br/>
        <span>Độ trễ: <b>${ef.item.delay_minutes == null ? "Chưa biết" : `${ef.item.delay_minutes}p`}</b></span>
        ${routeCluster ? `<br/>Cụm tuyến: <b>${routeCluster.cluster_id} · ${escapeTooltipText(routeCluster.short_label)}</b>` : ""}
      </div>`;

      const existing = currentMarkers.get(key);
      if (existing) {
        existing.enriched = ef;
        existing.progress = progress;
        existing.marker.setLatLng([pos.lat, pos.lon]);
        existing.marker.setZIndexOffset(isSelected ? 2000 : 600);
        const icon = L.divIcon({
          html: svgHtml,
          className: "fa-plane-icon-wrap",
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        });
        existing.marker.setIcon(icon);
        existing.marker.setTooltipContent(tooltip);
      } else {
        const icon = L.divIcon({
          html: svgHtml,
          className: "fa-plane-icon-wrap",
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        });

        const marker = L.marker([pos.lat, pos.lon], {
          icon,
          zIndexOffset: isSelected ? 2000 : 600,
        });

        marker.bindTooltip(tooltip, { direction: "top", offset: [0, -10], className: "fa-map-tooltip" });

        marker.on("click", () => {
          onSelectFlight(ef.item);
        });

        marker.addTo(map);
        currentMarkers.set(key, {
          marker,
          enriched: ef,
          timeline,
          progress,
        });
      }
    }
  }, [enrichedFlights, selectedFlightKey, colorMode, onSelectFlight, mapReady, routeClusterMap]);

  useEffect(() => {
    let rafId: number;
    let lastUpdateMs = 0;

    const animate = (timestamp: number) => {
      if (lastFrameTimeRef.current === null) {
        lastFrameTimeRef.current = timestamp;
      }
      const dtSec = (timestamp - lastFrameTimeRef.current) / 1000;
      lastFrameTimeRef.current = timestamp;

      if (!isPaused) {
        animClockRef.current += dtSec * speedMultiplier;
      }

      if (timestamp - lastUpdateMs >= 50) {
        lastUpdateMs = timestamp;
        const nowSec = animClockRef.current;

        for (const [key, entry] of planeMarkersRef.current.entries()) {
          const { marker, enriched } = entry;
          const progress = simulatedProgress(entry.timeline, nowSec);
          if (progress === entry.progress) continue;
          entry.progress = progress;
          const pos = interpolateCurvedPosition(
            enriched.originCoord.lat,
            enriched.originCoord.lon,
            enriched.destCoord.lat,
            enriched.destCoord.lon,
            progress
          );

          marker.setLatLng([pos.lat, pos.lon]);

          const el = marker.getElement();
          if (el) {
            const rotator = el.querySelector(".fa-plane-rotator") as HTMLElement | null;
            if (rotator) {
              rotator.style.transform = `rotate(${pos.bearing.toFixed(1)}deg)`;
              if (progress === 1) rotator.dataset.simulationState = "arrived";
            }
          }

          if (key === selectedFlightKey) {
            setLiveProgress(progress);
            setLiveCoords(pos);
          }
        }
      }

      rafId = requestAnimationFrame(animate);
    };

    rafId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafId);
  }, [isPaused, speedMultiplier, selectedFlightKey]);

  useEffect(() => {
    const L = leafletRef.current;
    const routeGroup = routeLayerGroupRef.current;
    if (!L || !routeGroup || !mapReady) return;

    routeGroup.clearLayers();
    if (!selectedEnriched) return;

    const { originCoord, destCoord } = selectedEnriched;
    const traveledPts = buildCurvePoints(
      originCoord.lat,
      originCoord.lon,
      destCoord.lat,
      destCoord.lon,
      liveProgress,
      0,
      20
    );
    const remainingPts = buildCurvePoints(
      originCoord.lat,
      originCoord.lon,
      destCoord.lat,
      destCoord.lon,
      1,
      liveProgress,
      20
    );

    L.polyline(traveledPts, {
      color: "#38bdf8",
      weight: 3,
      opacity: 0.95,
    }).addTo(routeGroup);

    if (liveProgress < 1) {
      L.polyline(remainingPts, {
        color: "#f3c165",
        weight: 2,
        opacity: 0.75,
        dashArray: "6 6",
      }).addTo(routeGroup);
    }
  }, [selectedEnriched, liveProgress, mapReady]);

  function resetUSBounds() {
    if (!mapInstanceRef.current) return;
    mapInstanceRef.current.flyTo([37.8, -96.0], 4, { duration: 0.8 });
  }

  return (
    <section className="panel fa-radar-panel" aria-label="Bản đồ radar chuyến bay thời gian thực">
      <div className="panel-heading fa-radar-header">
        <div>
          <div className="fa-title-row">
            <h2>Bản đồ Radar Không lưu Hoa Kỳ</h2>
            <span className="status-badge-pill mint">
              <span className="fa-pulse-dot" />
              {enrichedFlights.length} máy bay · {activeAirports.length} sân bay
            </span>
          </div>
          <p>
            Vẽ {number(enrichedFlights.length)} / {number(totalMatchedCount)} chuyến khớp bộ lọc (tối đa 300).
            Vị trí mô phỏng theo lịch bay.
            {flights.length > enrichedFlights.length && " Một số chuyến chưa đủ tọa độ để vẽ."}
          </p>
        </div>

        <div className="fa-radar-controls">
          <button
            type="button"
            className={`fa-ctrl-btn ${autoPollEnabled ? "active" : ""}`}
            onClick={onToggleAutoPoll}
            title="Tự động đồng bộ dữ liệu chuyến bay mới từ PostgreSQL mỗi 8 giây"
          >
            <span className="fa-dot-indicator" />
            {autoPollEnabled ? "Auto-Sync (8s)" : "Auto-Sync: Tắt"}
          </button>

          <button
            type="button"
            className="fa-ctrl-btn"
            onClick={() => setIsPaused(p => !p)}
            title="Tạm dừng hoặc tiếp tục chuyển động máy bay"
          >
            {isPaused ? "▶ Tiếp tục" : "⏸ Tạm dừng"}
          </button>

          <div className="fa-speed-group" role="group" aria-label="Tốc độ mô phỏng">
            {([1, 3, 6] as const).map(spd => (
              <button
                key={spd}
                type="button"
                className={speedMultiplier === spd ? "active" : ""}
                onClick={() => setSpeedMultiplier(spd)}
              >
                {spd}x
              </button>
            ))}
          </div>

          {selectedClusterId === null ? (
            <CustomSelect
              ariaLabel="Chế độ màu máy bay"
              size="compact"
              value={colorMode}
              onChange={val => setColorMode(val as "status" | "cluster" | "flightaware")}
              options={[
                { value: "status", label: "Màu: Trạng thái Delay" },
                { value: "cluster", label: "Màu: Cụm K-Means" },
                { value: "flightaware", label: "Màu: Vàng FlightAware" },
              ]}
            />
          ) : (
            <span className="fa-ctrl-btn" style={{ color: CLUSTER_COLORS[selectedClusterId] }}>
              Màu: Cụm {selectedClusterId}
            </span>
          )}

          <CustomSelect
            ariaLabel="Nền bản đồ"
            size="compact"
            value={mapStyle}
            onChange={val => setMapStyle(val as MapStyleMode)}
            options={[
              { value: "satellite", label: "Nền: Vệ tinh Esri" },
              { value: "navy", label: "Nền: FlightAware Navy" },
              { value: "osm-dark", label: "Nền: OSM Dark Radar" },
              { value: "osm", label: "Nền: Bản đồ Sáng" },
            ]}
          />

          <button
            type="button"
            className={`fa-ctrl-btn ${showAirportLabels ? "active" : ""}`}
            onClick={() => setShowAirportLabels(v => !v)}
          >
            Mã IATA
          </button>

          <button type="button" className="fa-ctrl-btn" onClick={resetUSBounds}>
            Reset
          </button>
        </div>
      </div>

      {/* Khung chứa bản đồ có isolation: isolate để mọi layer con không bao giờ tràn lên Header */}
      <div className={`fa-map-wrapper style-${mapStyle}`}>
        <div ref={mapContainerRef} className="fa-leaflet-container" />

        {selectedEnriched && (
          <aside className="fa-flight-hud" aria-label="Chi tiết chuyến bay đang chọn">
            <div className="fa-hud-top">
              <div>
                <span className="fa-hud-carrier">
                  {selectedEnriched.item.carrier_name} · {selectedEnriched.item.fl_date}
                </span>
                <h3>
                  {selectedEnriched.item.flight_code}
                  <small>Tail: {selectedEnriched.item.tail_num || "N/A"}</small>
                </h3>
              </div>
              <button
                type="button"
                className="fa-hud-close"
                onClick={() => onSelectFlight(null)}
                aria-label="Đóng chi tiết chuyến bay"
              >
                ✕
              </button>
            </div>

            <div className="fa-hud-route">
              <div className="fa-hud-airport">
                <strong>{selectedEnriched.item.origin}</strong>
                <span>{selectedEnriched.originCoord.city}</span>
                <small>CRS Đi: {selectedEnriched.item.crs_dep_time}</small>
              </div>
              <div className="fa-hud-plane-divider">
                <span>{liveProgress >= 1 ? "Đã đến · mô phỏng" : `✈ ${Math.floor(liveProgress * 100)}%`}</span>
                <div className="fa-hud-progress-track">
                  <div style={{ width: `${Math.min(100, Math.max(4, liveProgress * 100))}%` }} />
                </div>
                <small>
                  {number(Math.round(selectedEnriched.item.distance ?? 0))} dặm ({Math.round(selectedEnriched.item.crs_elapsed_time ?? 0)}p)
                </small>
              </div>
              <div className="fa-hud-airport" style={{ textAlign: "right" }}>
                <strong>{selectedEnriched.item.dest}</strong>
                <span>{selectedEnriched.destCoord.city}</span>
                <small>CRS Đến: {selectedEnriched.item.crs_arr_time}</small>
              </div>
            </div>

            <div className="fa-hud-telemetry">
              <div>
                <span>VĨ ĐỘ / KINH ĐỘ</span>
                <strong>
                  {Math.abs(liveCoords.lat).toFixed(2)}°{liveCoords.lat < 0 ? "S" : "N"}, {formatLongitude(liveCoords.lon)}
                </strong>
              </div>
              <div>
                <span>HƯỚNG BAY (HDG)</span>
                <strong>{Math.round(liveCoords.bearing)}°</strong>
              </div>
              <div>
                <span>TRẠNG THÁI DELAY</span>
                <strong
                  style={{
                    color:
                      (selectedEnriched.item.delay_minutes ?? 0) >= 45
                        ? "#f87171"
                        : (selectedEnriched.item.delay_minutes ?? 0) >= 15
                          ? "#fbbf24"
                          : "#4ade80",
                  }}
                >
                  {selectedEnriched.item.delay_minutes == null ? "Chưa biết" : `${selectedEnriched.item.delay_minutes}p`} ({statusLabels[selectedEnriched.item.delay_status]})
                </strong>
              </div>
              {selectedRouteCluster && (
                <div>
                  <span>CỤM K-MEANS (TUYẾN BAY)</span>
                  <strong style={{ color: CLUSTER_COLORS[selectedRouteCluster.cluster_id] }}>
                    Cụm {selectedRouteCluster.cluster_id} · {selectedRouteCluster.short_label}
                  </strong>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>

      {/* Thanh chú thích đặt gọn gàng ở chân Card Bản đồ (không bao giờ đè lên bản đồ hay nổi lên trên Header) */}
      <div className="fa-map-footer-bar">
        {colorMode === "cluster" ? (
          visibleClusters.map(cluster => (
            <div className="fa-legend-item" key={cluster.cluster_id}>
              <span className="fa-legend-dot" style={{ background: CLUSTER_COLORS[cluster.cluster_id] }} />
              <span>Cụm {cluster.cluster_id}: {cluster.short_label}</span>
            </div>
          ))
        ) : (
          <>
            <div className="fa-legend-item">
              <span className="fa-legend-dot" style={{ background: "#10b981" }} />
              <span>Sân bay lưu thông tốt</span>
            </div>
            <div className="fa-legend-item">
              <span className="fa-legend-dot" style={{ background: "#a855f7" }} />
              <span>Sân bay tỷ lệ trễ cao</span>
            </div>
            <span className="fa-footer-sep">|</span>
            <div className="fa-legend-item">
              <span style={{ color: "#10b981", fontWeight: 700 }}>✈</span>
              <span>Đúng giờ (&lt; 15p)</span>
            </div>
            <div className="fa-legend-item">
              <span style={{ color: "#f59e0b", fontWeight: 700 }}>✈</span>
              <span>Trễ nhẹ (15–44p)</span>
            </div>
            <div className="fa-legend-item">
              <span style={{ color: "#ef4444", fontWeight: 700 }}>✈</span>
              <span>Trễ nặng (≥ 45p)</span>
            </div>
          </>
        )}
        <span className="fa-footer-source">
          Trạng thái dữ liệu: Trực tiếp ({apiMode.toUpperCase()})
        </span>
      </div>
    </section>
  );
}
