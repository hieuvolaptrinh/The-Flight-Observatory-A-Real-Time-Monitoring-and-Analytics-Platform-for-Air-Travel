"use client";

import {
  CLUSTER_COLORS,
  ClusterAssignment,
  ClusterCentroid,
  ClusteringMeta,
  number,
} from "../flight-types";
import { Metric } from "../components/metric-card";
import { PcaScatterChart } from "../components/pca-scatter-chart";

interface ClusteringViewProps {
  clusteringMeta: ClusteringMeta | null;
  clusterEntityType: "airport" | "route";
  setClusterEntityType: (type: "airport" | "route") => void;
  fetchClusteringResults: (type: "airport" | "route") => void;
  clusterAssignments: ClusterAssignment[];
  selectedClusterId: number | null;
  setSelectedClusterId: (id: number | null) => void;
  centroids: ClusterCentroid[];
}

export function ClusteringView({
  clusteringMeta,
  clusterEntityType,
  setClusterEntityType,
  fetchClusteringResults,
  clusterAssignments,
  selectedClusterId,
  setSelectedClusterId,
  centroids,
}: ClusteringViewProps) {
  return (
    <>
      <section className="metrics" aria-label="Chỉ số phân cụm K-Means">
        <Metric
          title="Thuật toán Phân cụm"
          value={`K = ${clusteringMeta?.n_clusters ?? 4}`}
          unit="cụm"
          icon="cluster"
          note={clusteringMeta?.run?.algorithm || "KMeans + StandardScaler + PCA(2D)"}
          color="teal"
        />
        <Metric
          title="Chỉ số Silhouette Score"
          value={(clusteringMeta?.silhouette_score ?? 0).toFixed(4)}
          unit=""
          icon="spark"
          note={`Inertia: ${(clusteringMeta?.inertia ?? 0).toFixed(1)} · Model: ${clusteringMeta?.run?.model_version || "v1.0"}`}
          color="purple"
        />
        <Metric
          title="Tổng Sân bay đã phân cụm"
          value={number(clusteringMeta?.total_airports ?? 0)}
          unit="sân bay"
          icon="globe"
          note="Tổng hợp từ toàn bộ dữ liệu chuyến bay"
          color="blue"
        />
        <Metric
          title="Tổng Tuyến bay đã phân cụm"
          value={number(clusteringMeta?.total_routes ?? 0)}
          unit="tuyến"
          icon="plane"
          note={`Từ ${number(clusteringMeta?.source_flights_count ?? 0)} lượt bay đã ghi nhận`}
          color="coral"
        />
      </section>

      <div className="clustering-full-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Bản đồ Tương quan &amp; Không gian Đặc trưng</h2>
              <p>
                Trực quan hóa mức độ tương đồng và phân bố của từng {clusterEntityType === "airport" ? "sân bay" : "tuyến bay"}
              </p>
            </div>
            <div className="segmented">
              <button
                type="button"
                className={clusterEntityType === "airport" ? "selected" : ""}
                onClick={() => {
                  setClusterEntityType("airport");
                  fetchClusteringResults("airport");
                }}
              >
                Sân bay ({clusteringMeta?.total_airports ?? 0})
              </button>
              <button
                type="button"
                className={clusterEntityType === "route" ? "selected" : ""}
                onClick={() => {
                  setClusterEntityType("route");
                  fetchClusteringResults("route");
                }}
              >
                Tuyến bay ({clusteringMeta?.total_routes ?? 0})
              </button>
            </div>
          </div>
          <div style={{ padding: "0 0 16px" }}>
            <PcaScatterChart
              items={clusterAssignments}
              selectedClusterId={selectedClusterId}
              selectedEntityCode={null}
              height={310}
            />
          </div>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>4 Nhóm Đặc trưng Vận hành &amp; Ý nghĩa Nghiệp vụ</h2>
              <p>Chọn từng nhóm để xem chi tiết danh sách bên dưới</p>
            </div>
            {selectedClusterId !== null && (
              <button
                type="button"
                className="mini-reset-btn"
                onClick={() => setSelectedClusterId(null)}
              >
                Hiện tất cả cụm
              </button>
            )}
          </div>
          <div className="centroid-detail-list">
            {centroids.map(c => {
              const active = selectedClusterId === c.cluster_id;
              const color = CLUSTER_COLORS[c.cluster_id] || c.color_code;
              return (
                <article
                  key={c.cluster_id}
                  className={`centroid-detail-card ${active ? "active" : ""}`}
                  onClick={() => setSelectedClusterId(active ? null : c.cluster_id)}
                >
                  <div className="centroid-detail-header">
                    <span className="cluster-color-dot" style={{ background: color }} />
                    <strong>{c.cluster_name}</strong>
                    <span className="cluster-count-badge">
                      {c.entity_count} thực thể ({c.share_pct.toFixed(1)}%)
                    </span>
                  </div>
                  <p>{c.interpretation}</p>
                  <div className="centroid-stat-row">
                    <span>Chuyến TB: <b>{c.avg_flights.toFixed(1)}</b></span>
                    <span>Cự ly TB: <b>{Math.round(c.avg_distance)} dặm</b></span>
                    <span>Trễ TB: <b>+{c.avg_delay_minutes.toFixed(1)}p</b></span>
                    <span>Tỷ lệ trễ: <b>{c.delay_rate_pct.toFixed(1)}%</b></span>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <section className="panel predictions-panel">
        <div className="panel-heading">
          <div>
            <h2>
              Bảng Gán Cụm Chi tiết ({clusterEntityType === "airport" ? "Sân bay" : "Tuyến bay"}){" "}
              <span className="count-pill">{clusterAssignments.length}</span>
            </h2>
            <p>
              Dữ liệu truy vấn từ bảng PostgreSQL <code>cluster_assignments</code> kèm xác suất thuộc từng cụm (Soft Membership)
            </p>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>MÃ THỰC THỂ</th>
                <th>TÊN SÂN BAY / TUYẾN BAY</th>
                <th>PHÂN CỤM K-MEANS</th>
                <th>SỐ CHUYẾN</th>
                <th>SỐ TUYẾN KẾT NỐI</th>
                <th>CỰ LY TB</th>
                <th>TRỄ TB</th>
                <th>TỶ LỆ TRỄ</th>
                <th>TỌA ĐỘ PCA (X, Y)</th>
              </tr>
            </thead>
            <tbody>
              {clusterAssignments
                .filter(a => selectedClusterId === null || a.cluster_id === selectedClusterId)
                .slice(0, 60)
                .map(a => (
                  <tr key={`${a.entity_type}-${a.entity_code}`}>
                    <td>
                      <strong>{a.entity_code}</strong>
                    </td>
                    <td>{a.entity_name}</td>
                    <td>
                      <span
                        className="cluster-pill-tag"
                        style={{
                          borderColor: CLUSTER_COLORS[a.cluster_id] || "#38bdf8",
                          color: CLUSTER_COLORS[a.cluster_id] || "#38bdf8",
                        }}
                      >
                        <i
                          style={{
                            background: CLUSTER_COLORS[a.cluster_id] || "#38bdf8",
                          }}
                        />
                        Cụm {a.cluster_id} · {a.short_label}
                      </span>
                    </td>
                    <td className="tabular">{a.flight_count}</td>
                    <td className="tabular">{a.route_count}</td>
                    <td className="tabular">{Math.round(a.avg_distance)} dặm</td>
                    <td className="tabular">+{a.avg_delay_minutes.toFixed(1)}p</td>
                    <td className="tabular">{a.delay_rate_pct.toFixed(1)}%</td>
                    <td className="tabular">
                      ({a.pca_x.toFixed(2)}, {a.pca_y.toFixed(2)})
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
