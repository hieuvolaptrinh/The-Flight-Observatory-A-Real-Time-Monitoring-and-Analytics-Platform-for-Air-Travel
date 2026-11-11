"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type * as LType from "leaflet";
import {
  FlightItem,
  ClusterAssignment,
  CLUSTER_COLORS,
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
  totalStoredInDb?: number;
  airportClusterMap?: Record<string, ClusterAssignment>;
  selectedClusterId?: number | null;
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
  totalStoredInDb,
  airportClusterMap = {},
  selectedClusterId = null,
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
        lastAngle: number;
      }
    >
  >(new Map());
  const airportLayerGroupRef = useRef<LType.LayerGroup | null>(null);
  const routeLayerGroupRef = useRef<LType.LayerGroup | null>(null);

  const [mapReady, setMapReady] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [speedMultiplier, setSpeedMultiplier] = useState<1 | 3 | 6>(1);
  const [colorMode, setColorMode] = useState<"status" | "cluster" | "flightaware">("status");
  const [mapStyle, setMapStyle] = useState<MapStyleMode>("satellite");
  const [showAirportLabels, setShowAirportLabels] = useState(true);
  const [liveProgress, setLiveProgress] = useState<number>(0.5);
  const [liveCoords, setLiveCoords] = useState<{ lat: number; lon: number; bearing: number }>({
    lat: 38.5,
    lon: -96.5,
    bearing: 90,
  });

  const animClockRef = useRef<number>(0);
  const lastFrameTimeRef = useRef<number | null>(null);

  const enrichedFlights = useMemo<EnrichedFlight[]>(() => {
    const list: EnrichedFlight[] = [];
    for (const f of flights) {
      const originCoord = US_AIRPORT_COORDS[f.origin];
      const destCoord = US_AIRPORT_COORDS[f.dest];
      if (!originCoord || !destCoord) continue;
      if (f.origin === f.dest) continue;

      if (selectedClusterId !== null && selectedClusterId !== undefined) {
        const oCluster = airportClusterMap[f.origin]?.cluster_id;
        const dCluster = airportClusterMap[f.dest]?.cluster_id;
        if (oCluster !== selectedClusterId && dCluster !== selectedClusterId) {
          continue;
        }
      }

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
      if (list.length >= 250) break;
    }
    return list;
  }, [flights, selectedClusterId, airportClusterMap]);

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
      const delayed = is_delayed === 1 || delay_minutes >= 15 || delay_status !== "on_time";

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
        minZoom: 3,
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
      const clusterInfo = airportClusterMap[ap.code];

      let dotColor = "#10b981";
      if (colorMode === "cluster" && clusterInfo) {
        dotColor = CLUSTER_COLORS[clusterInfo.cluster_id] || "#38bdf8";
      } else {
        if (delayRatio >= 0.5) dotColor = "#a855f7";
        else if (ap.departures === 0) dotColor = "#ffffff";
      }

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

      const clusterLine = clusterInfo
        ? `<br/><span style="color:#93c5fd;">K-Means: <b>Cụm ${clusterInfo.cluster_id} (${clusterInfo.short_label})</b></span>`
        : "";

      marker.bindTooltip(
        `<div style="font-size:11px;line-height:1.45;">
          <strong>${ap.code} · ${ap.coord.name}</strong><br/>
          <span>Thành phố: ${ap.coord.city}</span><br/>
          <span>Khởi hành: <b>${ap.departures}</b> · Hạ cánh: <b>${ap.arrivals}</b></span>${clusterLine}
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
  }, [activeAirports, showAirportLabels, onQuickFilterAirport, mapReady, colorMode, airportClusterMap]);

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
      const progress = (ef.initialProgress + nowSec / ef.durationSec) % 1;
      const pos = interpolateCurvedPosition(
        ef.originCoord.lat,
        ef.originCoord.lon,
        ef.destCoord.lat,
        ef.destCoord.lon,
        progress
      );

      let planeColor = "#f3c165";
      if (isSelected) {
        planeColor = "#38bdf8";
      } else if (colorMode === "status") {
        if (ef.item.delay_status === "severe_delay") planeColor = "#f87171";
        else if (ef.item.delay_status === "moderate_delay") planeColor = "#fbbf24";
        else planeColor = "#34d399";
      } else if (colorMode === "cluster") {
        const oCluster = airportClusterMap[ef.item.origin]?.cluster_id;
        planeColor = oCluster !== undefined ? CLUSTER_COLORS[oCluster] || "#f3c165" : "#f3c165";
      }

      const size = isSelected ? 28 : 21;
      const svgHtml = `
        <div class="fa-plane-rotator ${isSelected ? "selected" : ""}" style="transform: rotate(${pos.bearing.toFixed(1)}deg); color: ${planeColor};">
          <svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="currentColor" stroke="#08142c" stroke-width="1">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
          </svg>
        </div>
      `;

      const existing = currentMarkers.get(key);
      if (existing) {
        existing.enriched = ef;
        existing.marker.setLatLng([pos.lat, pos.lon]);
        existing.marker.setZIndexOffset(isSelected ? 2000 : 600);
        const icon = L.divIcon({
          html: svgHtml,
          className: "fa-plane-icon-wrap",
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        });
        existing.marker.setIcon(icon);
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

        const oClusterInfo = airportClusterMap[ef.item.origin];
        marker.bindTooltip(
          `<div style="font-size:11px;line-height:1.45;">
            <strong>${ef.item.flight_code}</strong> (${ef.item.carrier_name})<br/>
            <span><b>${ef.item.origin}</b> → <b>${ef.item.dest}</b> · Tail: ${ef.item.tail_num || "N/A"}</span><br/>
            <span>Giờ: ${ef.item.crs_dep_time} → ${ef.item.crs_arr_time} · Delay: <b>+${ef.item.delay_minutes}p</b></span>
            ${oClusterInfo ? `<br/><span style="color:#93c5fd;">Sân bay đi thuộc: <b>Cụm ${oClusterInfo.cluster_id} (${oClusterInfo.short_label})</b></span>` : ""}
          </div>`,
          { direction: "top", offset: [0, -10], className: "fa-map-tooltip" }
        );

        marker.on("click", () => {
          onSelectFlight(ef.item);
        });

        marker.addTo(map);
        currentMarkers.set(key, {
          marker,
          enriched: ef,
          lastAngle: pos.bearing,
        });
      }
    }
  }, [enrichedFlights, selectedFlightKey, colorMode, onSelectFlight, mapReady, airportClusterMap]);

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
          const progress = (enriched.initialProgress + nowSec / enriched.durationSec) % 1;
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

    L.polyline(remainingPts, {
      color: "#f3c165",
      weight: 2,
      opacity: 0.75,
      dashArray: "6 6",
    }).addTo(routeGroup);
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
            Giám sát vị trí và hành trình của {number(totalStoredInDb ?? totalMatchedCount)} chuyến bay theo thời gian thực
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
                <span>✈ {(liveProgress * 100).toFixed(0)}%</span>
                <div className="fa-hud-progress-track">
                  <div style={{ width: `${Math.min(100, Math.max(4, liveProgress * 100))}%` }} />
                </div>
                <small>
                  {number(Math.round(selectedEnriched.item.distance))} dặm ({Math.round(selectedEnriched.item.crs_elapsed_time)}p)
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
                  {liveCoords.lat.toFixed(2)}°N, {Math.abs(liveCoords.lon).toFixed(2)}°W
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
                      selectedEnriched.item.delay_minutes >= 45
                        ? "#f87171"
                        : selectedEnriched.item.delay_minutes >= 15
                          ? "#fbbf24"
                          : "#4ade80",
                  }}
                >
                  +{selectedEnriched.item.delay_minutes}p ({statusLabels[selectedEnriched.item.delay_status]})
                </strong>
              </div>
              {airportClusterMap[selectedEnriched.item.origin] && (
                <div>
                  <span>PHÂN CỤM K-MEANS ({selectedEnriched.item.origin})</span>
                  <strong style={{ color: "#93c5fd" }}>
                    Cụm {airportClusterMap[selectedEnriched.item.origin].cluster_id} ·{" "}
                    {airportClusterMap[selectedEnriched.item.origin].short_label}
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
          <>
            <div className="fa-legend-item">
              <span className="fa-legend-dot" style={{ background: "#ef4444" }} />
              <span>Cụm 0: Mega-Hub</span>
            </div>
            <div className="fa-legend-item">
              <span className="fa-legend-dot" style={{ background: "#f59e0b" }} />
              <span>Cụm 1: Đường dài (Long-Haul)</span>
            </div>
            <div className="fa-legend-item">
              <span className="fa-legend-dot" style={{ background: "#3b82f6" }} />
              <span>Cụm 2: Khu vực tầm trung</span>
            </div>
            <div className="fa-legend-item">
              <span className="fa-legend-dot" style={{ background: "#10b981" }} />
              <span>Cụm 3: Ổn định đúng giờ</span>
            </div>
          </>
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
