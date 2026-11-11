"use client";

import FlightRadarMap from "../flight-radar-map";
import {
  CLUSTER_COLORS,
  ClusterAssignment,
  ClusterCentroid,
  ClusteringMeta,
  FlightItem,
  RawFlightItem,
  number,
  statusBadgeClass,
  statusLabels,
} from "../flight-types";
import { CustomSelect } from "../components/custom-select";
import { Icon } from "../components/icons";
import { Metric } from "../components/metric-card";
import { PcaScatterChart } from "../components/pca-scatter-chart";

interface FlightsViewProps {
  apiMode: "gateway" | "ingestion" | "demo";
  apiReady: boolean | null;
  totalFilteredCount: number;
  batchMeta: {
    total_stored?: number;
    window_start?: number;
    window_end?: number;
    inserted_count?: number;
    duplicate_count?: number;
  } | null;
  flightsOnTimeCount: number;
  flightsDelayedCount: number;
  flightsDelayRate: number;
  flightsAvgDelay: number;
  flightsAvgDistance: number;
  statusCounts: Record<FlightItem["delay_status"], number>;
  clusteringMeta: ClusteringMeta | null;
  mapFlights: FlightItem[];
  selectedFlightKey: string | null;
  setSelectedFlightKey: (updater: string | null | ((prev: string | null) => string | null)) => void;
  airport: string;
  setAirport: (updater: string | ((prev: string) => string)) => void;
  autoPollEnabled: boolean;
  setAutoPollEnabled: (updater: boolean | ((prev: boolean) => boolean)) => void;
  airportClusterMap: Record<string, ClusterAssignment>;
  selectedClusterId: number | null;
  setSelectedClusterId: (id: number | null) => void;
  centroids: ClusterCentroid[];
  clusterAssignments: ClusterAssignment[];
  flightStatus: string;
  setFlightStatus: (val: string) => void;
  carrier: string;
  setCarrier: (val: string) => void;
  carrierDelayBars: { code: string; avg_delay: number; flight_count: number }[];
  sort: string;
  setSort: (val: string) => void;
  pageSize: number;
  setPageSize: (val: number) => void;
  paginatedFlights: FlightItem[];
  startIndex: number;
  safePage: number;
  totalPages: number;
  pageNumbers: (number | "...")[];
  setCurrentPage: (updater: number | ((prev: number) => number)) => void;
  dataLayer: "cleaned" | "raw";
  setDataLayer: (layer: "cleaned" | "raw") => void;
  rawFlights: RawFlightItem[];
  rawLoading: boolean;
  rawCursor: number;
  setRawCursor: (updater: number | ((prev: number) => number)) => void;
  rawTotal: number;
  rawPageSize: number;
  notify: (msg: string) => void;
}

const SORT_OPTIONS = [
  { value: "time", label: "Sắp xếp: Giờ khởi hành" },
  { value: "delay", label: "Sắp xếp: Độ trễ giảm dần" },
  { value: "distance", label: "Sắp xếp: Cự ly giảm dần" },
];

const PAGE_SIZE_OPTIONS = [
  { value: "10", label: "10 dòng / trang" },
  { value: "12", label: "12 dòng / trang" },
  { value: "25", label: "25 dòng / trang" },
  { value: "50", label: "50 dòng / trang" },
];

export function FlightsView({
  apiMode,
  apiReady,
  totalFilteredCount,
  batchMeta,
  flightsOnTimeCount,
  flightsDelayedCount,
  flightsDelayRate,
  flightsAvgDelay,
  flightsAvgDistance,
  statusCounts,
  clusteringMeta,
  mapFlights,
  selectedFlightKey,
  setSelectedFlightKey,
  airport,
  setAirport,
  autoPollEnabled,
  setAutoPollEnabled,
  airportClusterMap,
  selectedClusterId,
  setSelectedClusterId,
  centroids,
  clusterAssignments,
  flightStatus,
  setFlightStatus,
  carrier,
  setCarrier,
  carrierDelayBars,
  sort,
  setSort,
  pageSize,
  setPageSize,
  paginatedFlights,
  startIndex,
  safePage,
  totalPages,
  pageNumbers,
  setCurrentPage,
  dataLayer,
  setDataLayer,
  rawFlights,
  rawLoading,
  rawCursor,
  setRawCursor,
  rawTotal,
  rawPageSize,
  notify,
}: FlightsViewProps) {
  return (
    <>
      {apiMode !== "demo" && apiReady === false && (
        <section className="forecast-banner">
          <span className="banner-icon">
            <Icon name="alert" size={24} />
          </span>
          <div>
            <h2>Database hiện đang trống (chưa có dữ liệu chuyến bay).</h2>
            <p>
              Nhấn nút &ldquo;Nạp batch mới (POST /run)&rdquo; trên thanh Header để Ingestion
              gọi Simulator và lưu dữ liệu vào PostgreSQL.
            </p>
          </div>
        </section>
      )}

      {/* 4 COMPACT KPI METRICS */}
      <section className="metrics" aria-label="Chỉ số chuyến bay">
        <Metric
          title="Tổng chuyến bay khớp lọc"
          value={number(totalFilteredCount)}
          unit="chuyến"
          icon="plane"
          note={
            batchMeta?.window_start !== undefined
              ? `Đang theo dõi ${number(batchMeta.total_stored ?? 0)} chuyến bay`
              : "Dữ liệu vận hành cập nhật thời gian thực"
          }
        />
        <Metric
          title="Đúng giờ (< 15 phút)"
          value={number(flightsOnTimeCount)}
          unit={`(${(totalFilteredCount ? 100 - flightsDelayRate : 0).toFixed(1)}%)`}
          icon="check"
          note="Khởi hành đúng giờ hoặc trễ dưới 15 phút"
          color="teal"
        />
        <Metric
          title="Chuyến bay trễ (≥ 15 phút)"
          value={number(flightsDelayedCount)}
          unit={`(${flightsDelayRate.toFixed(1)}%)`}
          icon="alert"
          note={`Trễ nhẹ: ${statusCounts.moderate_delay} · Trễ nặng: ${statusCounts.severe_delay}`}
          color="coral"
        />
        <Metric
          title="Độ trễ TB & Phân cụm K-Means"
          value={flightsAvgDelay.toFixed(1)}
          unit="phút"
          icon="cluster"
          note={`Cự ly TB: ${number(Math.round(flightsAvgDistance))} dặm · ${clusteringMeta?.total_airports ?? 0} sân bay đã phân cụm`}
          color="purple"
        />
      </section>

      {/* MAIN WORKBENCH LAYOUT: RADAR MAP (65%) + SIDEBAR (35%) */}
      <div className="flights-workbench-grid">
        <div className="workbench-map-col">
          <FlightRadarMap
            flights={mapFlights}
            selectedFlightKey={selectedFlightKey}
            onSelectFlight={f => setSelectedFlightKey(f ? f.flight_key : null)}
            onQuickFilterAirport={code => {
              setAirport(prev => (prev === code ? "all" : code));
              notify(`Đã lọc nhanh theo sân bay đi: ${code}`);
            }}
            autoPollEnabled={autoPollEnabled}
            onToggleAutoPoll={() => setAutoPollEnabled(v => !v)}
            apiMode={apiMode}
            totalMatchedCount={totalFilteredCount}
            totalStoredInDb={batchMeta?.total_stored}
            airportClusterMap={airportClusterMap}
            selectedClusterId={selectedClusterId}
          />
        </div>

        <aside className="workbench-side-col" aria-label="Bảng phân tích đồng bộ bên cạnh bản đồ">
          {/* SIDE PANEL 1: AIRPORT K-MEANS CLUSTERING & 2D PCA */}
          <section className="panel side-cluster-panel">
            <div className="panel-heading compact-heading">
              <div>
                <h2>Phân nhóm Đặc trưng Sân bay</h2>
                <p>
                  Chọn nhóm để lọc nhanh các sân bay và máy bay trên bản đồ radar
                </p>
              </div>
              {selectedClusterId !== null && (
                <button
                  type="button"
                  className="mini-reset-btn"
                  onClick={() => setSelectedClusterId(null)}
                >
                  Bỏ lọc cụm
                </button>
              )}
            </div>

            <div className="cluster-mini-grid">
              {centroids.map(c => {
                const active = selectedClusterId === c.cluster_id;
                const color = CLUSTER_COLORS[c.cluster_id] || c.color_code;
                return (
                  <button
                    key={c.cluster_id}
                    type="button"
                    className={`cluster-mini-card ${active ? "active" : ""}`}
                    onClick={() => setSelectedClusterId(active ? null : c.cluster_id)}
                  >
                    <div className="cluster-mini-top">
                      <span
                        className="cluster-color-dot"
                        style={{ background: color }}
                      />
                      <strong>Cụm {c.cluster_id}</strong>
                      <span className="cluster-count-badge">
                        {c.entity_count} SB ({c.share_pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="cluster-mini-label">{c.short_label}</div>
                    <div className="cluster-mini-metrics">
                      <span>Trễ TB: +{c.avg_delay_minutes.toFixed(1)}p</span>
                      <span>Tỷ lệ trễ: {c.delay_rate_pct.toFixed(1)}%</span>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="side-pca-box">
              <PcaScatterChart
                items={clusterAssignments}
                selectedClusterId={selectedClusterId}
                selectedEntityCode={airport === "all" ? null : airport}
                onSelectEntity={code => {
                  setAirport(prev => (prev === code ? "all" : code));
                  notify(`Đã chọn sân bay ${code} từ biểu đồ phân cụm PCA 2D`);
                }}
                height={162}
              />
            </div>
          </section>

          {/* SIDE PANEL 2: CARRIER DELAY CORRELATION & STATUS */}
          <section className="panel side-delay-panel">
            <div className="panel-heading compact-heading">
              <div>
                <h2>Độ trễ theo Hãng bay &amp; Trạng thái</h2>
                <p>Thống kê thời gian chậm trễ và phân bố trạng thái chuyến bay</p>
              </div>
            </div>

            <div className="side-status-pills">
              {(["on_time", "moderate_delay", "severe_delay"] as const).map(st => {
                const count = statusCounts[st] || 0;
                const pct = totalFilteredCount
                  ? ((count / totalFilteredCount) * 100).toFixed(0)
                  : "0";
                const badge = statusBadgeClass[st];
                return (
                  <button
                    key={st}
                    type="button"
                    className={`status-pill-btn ${badge} ${flightStatus === st ? "selected" : ""}`}
                    onClick={() => setFlightStatus(flightStatus === st ? "all" : st)}
                  >
                    <span>{statusLabels[st]}</span>
                    <strong>
                      {count} <small>({pct}%)</small>
                    </strong>
                  </button>
                );
              })}
            </div>

            <div className="compact-carrier-bars">
              {carrierDelayBars.slice(0, 6).map(bar => {
                const val = bar.avg_delay || 0;
                const active = carrier === bar.code;
                return (
                  <button
                    type="button"
                    key={bar.code}
                    className={`carrier-horiz-row ${active ? "active" : ""}`}
                    onClick={() => setCarrier(active ? "all" : bar.code)}
                    title={`Nhấn để lọc hãng ${bar.code}`}
                  >
                    <span className={`airline-mark airline-${bar.code}`}>{bar.code}</span>
                    <div className="carrier-horiz-track">
                      <div
                        style={{ width: `${Math.min(100, Math.max(4, (val / 45) * 100))}%` }}
                        className={val >= 20 ? "bar-coral" : "bar-teal"}
                      />
                    </div>
                    <strong className="tabular">+{val.toFixed(1)}p</strong>
                    <small className="tabular">({bar.flight_count})</small>
                  </button>
                );
              })}
            </div>
          </section>
        </aside>
      </div>

      {/* SERVER-SIDE SQL FLIGHTS TABLE WITH K-MEANS CLUSTERS & RAW DATA LAYER */}
      <section className="panel predictions-panel">
        <div className="panel-heading">
          <div>
            <h2>
              {dataLayer === "raw" ? "Dữ liệu Thô từ Database (Bronze Layer) " : "Danh sách chi tiết chuyến bay "}
              <span className="count-pill">
                {dataLayer === "raw" ? `${rawTotal.toLocaleString()} dòng` : totalFilteredCount}
              </span>
            </h2>
            <p>
              {dataLayer === "raw"
                ? "Dữ liệu chuỗi nguyên bản chưa qua làm sạch từ bảng PostgreSQL analytics.raw_flights (539.719 dòng)"
                : "Dữ liệu đã qua Ingestion Pipeline: Chuẩn hóa kiểu, khử trùng lặp và tính toán delay"}
            </p>
          </div>
          <div className="table-tools">
            <div className="data-layer-toggle" role="group" aria-label="Chọn tầng dữ liệu">
              <button
                type="button"
                className={`data-layer-btn ${dataLayer === "cleaned" ? "active" : ""}`}
                onClick={() => setDataLayer("cleaned")}
                title="Dữ liệu đã chuẩn hóa trong bảng analytics.ingested_flights"
              >
                <Icon name="check" size={13} />
                Đã chuẩn hóa (Cleaned DB)
              </button>
              <button
                type="button"
                className={`data-layer-btn ${dataLayer === "raw" ? "raw-active" : ""}`}
                onClick={() => setDataLayer("raw")}
                title="Dữ liệu thô nguyên bản trong bảng analytics.raw_flights (539.719 dòng)"
              >
                <Icon name="cluster" size={13} />
                Dữ liệu thô (Raw DB · 540k)
              </button>
            </div>

            {dataLayer === "cleaned" && (
              <>
                <CustomSelect
                  ariaLabel="Sắp xếp"
                  size="compact"
                  value={sort}
                  onChange={setSort}
                  options={SORT_OPTIONS}
                />
                <CustomSelect
                  ariaLabel="Số dòng mỗi trang"
                  size="compact"
                  value={String(pageSize)}
                  onChange={val => setPageSize(Number(val))}
                  options={PAGE_SIZE_OPTIONS}
                />
              </>
            )}
          </div>
        </div>

        {dataLayer === "raw" && (
          <div className="raw-db-banner">
            <span className="raw-db-badge">BRONZE LAYER · RAW DB</span>
            <div>
              <strong>Bảng dữ liệu thô nguyên bản: <code>analytics.raw_flights</code></strong>
              <span>
                {" "}— Truy vấn trực tiếp từ <strong>539.719 dòng</strong> lưu trữ định dạng TEXT nguyên gốc trước khi qua Ingestion Pipeline để làm sạch, khử trùng lặp và gán nhãn delay.
              </span>
            </div>
          </div>
        )}

        <div className="table-scroll">
          {dataLayer === "raw" ? (
            <table>
              <thead>
                <tr>
                  <th>MÃ THÔ (RAW ID)</th>
                  <th>NGÀY BAY</th>
                  <th>HÃNG BAY & SỐ HIỆU</th>
                  <th>TÀU BAY (TAIL)</th>
                  <th>HÀNH TRÌNH THÔ (ORIGIN → DEST)</th>
                  <th>GIỜ ĐI (CRS)</th>
                  <th>GIỜ ĐẾN (CRS)</th>
                  <th>CỰ LY / THỜI LƯỢNG</th>
                  <th>TRẠNG THÁI</th>
                </tr>
              </thead>
              <tbody>
                {rawLoading ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: "center", padding: "40px", color: "var(--muted)" }}>
                      Đang truy vấn dữ liệu thô từ bảng <code>analytics.raw_flights</code>...
                    </td>
                  </tr>
                ) : (
                  rawFlights.map((r, i) => (
                    <tr key={r.RAW_ID || `raw-${i}`}>
                      <td>
                        <strong>#{r.RAW_ID}</strong> <small className="muted">(Dòng {r.ROW_NUMBER})</small>
                      </td>
                      <td className="tabular">{r.FL_DATE}</td>
                      <td>
                        <span className={`airline-mark airline-${r.OP_UNIQUE_CARRIER || "AA"}`}>{r.OP_UNIQUE_CARRIER}</span>
                        <strong>{r.OP_CARRIER_FL_NUM}</strong>
                      </td>
                      <td><code>{r.TAIL_NUM || "—"}</code></td>
                      <td>
                        <span className="route">
                          <strong>{r.ORIGIN}</strong> <small className="muted">({r.ORIGIN_AIRPORT_ID})</small>
                          <Icon name="arrow" size={14} />
                          <strong>{r.DEST}</strong> <small className="muted">({r.DEST_AIRPORT_ID})</small>
                        </span>
                      </td>
                      <td className="tabular">
                        <code>{r.CRS_DEP_TIME}</code> <small className="muted">(text thô)</small>
                      </td>
                      <td className="tabular">
                        <code>{r.CRS_ARR_TIME}</code>
                      </td>
                      <td className="tabular">
                        {r.DISTANCE ? `${r.DISTANCE} dặm` : "—"} / {r.CRS_ELAPSED_TIME ? `${r.CRS_ELAPSED_TIME}p` : "—"}
                      </td>
                      <td>
                        <span className="raw-tag">RAW · Chưa xử lý</span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>CHUYẾN BAY</th>
                  <th>TÀU BAY (TAIL)</th>
                  <th>NGÀY BAY</th>
                  <th>HÀNH TRÌNH</th>
                  <th>CỤM K-MEANS (SÂN BAY ĐI)</th>
                  <th>GIỜ ĐI / ĐẾN (CRS)</th>
                  <th>CỰ LY / THỜI GIAN</th>
                  <th>MỨC ĐỘ DELAY</th>
                  <th>TRẠNG THÁI</th>
                </tr>
              </thead>
              <tbody>
                {paginatedFlights.map(f => {
                  const badge = statusBadgeClass[f.delay_status];
                  const isRowSelected = selectedFlightKey === f.flight_key;
                  const oCluster = airportClusterMap[f.origin];
                  return (
                    <tr
                      key={f.flight_key}
                      onClick={() =>
                        setSelectedFlightKey(prev =>
                          prev === f.flight_key ? null : f.flight_key
                        )
                      }
                      className={isRowSelected ? "selected-row" : ""}
                      style={{ cursor: "pointer" }}
                      title="Nhấn để định vị máy bay này trên Bản đồ Radar"
                    >
                      <td>
                        <span className={`airline-mark airline-${f.op_unique_carrier}`}>
                          {f.op_unique_carrier}
                        </span>
                        <strong>{f.flight_code}</strong>
                      </td>
                      <td className="tabular">{f.tail_num || "—"}</td>
                      <td className="tabular">{f.fl_date}</td>
                      <td>
                        <span className="route">
                          <strong>{f.origin}</strong>
                          <Icon name="arrow" size={14} />
                          <strong>{f.dest}</strong>
                        </span>
                      </td>
                      <td>
                        {oCluster ? (
                          <span
                            className="cluster-pill-tag"
                            style={{
                              borderColor: CLUSTER_COLORS[oCluster.cluster_id] || "#38bdf8",
                              color: CLUSTER_COLORS[oCluster.cluster_id] || "#38bdf8",
                            }}
                          >
                            <i
                              style={{
                                background: CLUSTER_COLORS[oCluster.cluster_id] || "#38bdf8",
                              }}
                            />
                            Cụm {oCluster.cluster_id} · {oCluster.short_label}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="tabular">
                        {f.crs_dep_time} <span className="muted">→</span> {f.crs_arr_time}
                      </td>
                      <td className="tabular">
                        {number(Math.round(f.distance))}{" "}
                        <span className="muted">dặm ({Math.round(f.crs_elapsed_time)}p)</span>
                      </td>
                      <td className="tabular">
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
          )}

          {dataLayer === "cleaned" && !paginatedFlights.length && (
            <div className="empty-state">
              <Icon name="search" size={28} />
              <h3>Không có chuyến bay phù hợp</h3>
              <p>
                {apiMode !== "demo" && apiReady === false
                  ? "Database hiện đang trống. Nhấn nút 'Nạp batch mới (POST /run)' để nạp dữ liệu từ Simulator."
                  : "Thử từ khóa tìm kiếm khác hoặc đặt lại bộ lọc."}
              </p>
            </div>
          )}
        </div>

        {dataLayer === "raw" ? (
          <div className="table-footer">
            <div>
              Hiển thị dòng thô{" "}
              <strong>
                {rawCursor + 1}–{Math.min(rawCursor + rawFlights.length, rawTotal)}
              </strong>{" "}
              trên tổng số <strong>{rawTotal.toLocaleString()}</strong> dòng thô trong database (<code>analytics.raw_flights</code> · Keyset Seek)
            </div>

            <div className="pagination-controls">
              <button
                type="button"
                className="button secondary page-btn"
                disabled={rawCursor <= 0 || rawLoading}
                onClick={() => setRawCursor(0)}
              >
                « Về đầu (Dòng 1)
              </button>
              <button
                type="button"
                className="button secondary page-btn"
                disabled={rawCursor <= 0 || rawLoading}
                onClick={() => setRawCursor(Math.max(0, rawCursor - rawPageSize))}
              >
                ‹ Trước {rawPageSize} dòng
              </button>
              <button
                type="button"
                className="button secondary page-btn"
                disabled={rawCursor + rawPageSize >= rawTotal || rawLoading}
                onClick={() => setRawCursor(rawCursor + rawPageSize)}
              >
                Kế tiếp {rawPageSize} dòng ›
              </button>
            </div>
          </div>
        ) : (
          <div className="table-footer">
            <div>
              Hiển thị{" "}
              <strong>
                {totalFilteredCount ? startIndex + 1 : 0}–
                {Math.min(startIndex + paginatedFlights.length, totalFilteredCount)}
              </strong>{" "}
              trên tổng số <strong>{totalFilteredCount}</strong> chuyến bay (Trang {safePage}/
              {totalPages} · PostgreSQL Server-side Query)
            </div>

            <div className="pagination-controls">
              <button
                type="button"
                className="button secondary page-btn"
                disabled={safePage <= 1}
                onClick={() => setCurrentPage(1)}
              >
                « Đầu
              </button>
              <button
                type="button"
                className="button secondary page-btn"
                disabled={safePage <= 1}
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              >
                ‹ Trước
              </button>

              {pageNumbers.map((p, idx) =>
                p === "..." ? (
                  <span key={`ellipsis-${idx}`} className="page-ellipsis">
                    …
                  </span>
                ) : (
                  <button
                    type="button"
                    key={p}
                    onClick={() => setCurrentPage(p)}
                    aria-current={safePage === p ? "page" : undefined}
                    className={`page-num-btn ${safePage === p ? "active" : ""}`}
                  >
                    {p}
                  </button>
                )
              )}

              <button
                type="button"
                className="button secondary page-btn"
                disabled={safePage >= totalPages}
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              >
                Sau ›
              </button>
              <button
                type="button"
                className="button secondary page-btn"
                disabled={safePage >= totalPages}
                onClick={() => setCurrentPage(totalPages)}
              >
                Cuối »
              </button>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
