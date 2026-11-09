"use client";

import { useState } from "react";
import { ClusterAssignment, CLUSTER_COLORS } from "../flight-types";

export function PcaScatterChart({
  items,
  selectedClusterId,
  selectedEntityCode,
  onSelectEntity,
  height = 175,
}: {
  items: ClusterAssignment[];
  selectedClusterId: number | null;
  selectedEntityCode: string | null;
  onSelectEntity?: (code: string) => void;
  height?: number;
}) {
  const [hovered, setHovered] = useState<ClusterAssignment | null>(null);

  if (!items.length) {
    return (
      <div className="pca-empty">
        Chưa có dữ liệu tọa độ PCA 2D. Nhấn &ldquo;Chạy K-Means&rdquo; để phân cụm.
      </div>
    );
  }

  const xs = items.map(i => i.pca_x);
  const ys = items.map(i => i.pca_y);
  const minX = Math.min(...xs, -2.5);
  const maxX = Math.max(...xs, 2.5);
  const minY = Math.min(...ys, -2.0);
  const maxY = Math.max(...ys, 2.0);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;

  const padX = 28;
  const padY = 20;
  const W = 420;
  const H = height;

  const toSvgX = (x: number) => padX + ((x - minX) / spanX) * (W - padX * 2);
  const toSvgY = (y: number) => H - padY - ((y - minY) / spanY) * (H - padY * 2);

  const zeroX = toSvgX(0);
  const zeroY = toSvgY(0);

  return (
    <div className="pca-scatter-wrap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Không gian phân cụm PCA 2 chiều (PCA X, PCA Y)"
      >
        <rect x="0" y="0" width={W} height={H} rx="8" fill="#f8fafc" />
        <line x1={padX} x2={W - padX} y1={zeroY} y2={zeroY} stroke="#cbd5e1" strokeDasharray="3 3" />
        <line x1={zeroX} x2={zeroX} y1={padY} y2={H - padY} stroke="#cbd5e1" strokeDasharray="3 3" />
        <text x={W - padX} y={zeroY - 5} textAnchor="end" fill="#64748b" fontSize="8.5">
          PCA 1 (Lưu lượng &amp; Kết nối)
        </text>
        <text x={zeroX + 6} y={padY + 8} textAnchor="start" fill="#64748b" fontSize="8.5">
          PCA 2 (Độ trễ &amp; Cự ly)
        </text>

        {items.map(item => {
          const isDimmed =
            selectedClusterId !== null && item.cluster_id !== selectedClusterId;
          const isSelected = selectedEntityCode === item.entity_code;
          const cx = toSvgX(item.pca_x);
          const cy = toSvgY(item.pca_y);
          const color = CLUSTER_COLORS[item.cluster_id] || "#38bdf8";

          return (
            <g
              key={`${item.entity_type}-${item.entity_code}`}
              style={{ cursor: "pointer", opacity: isDimmed ? 0.2 : 0.95 }}
              onMouseEnter={() => setHovered(item)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSelectEntity?.(item.entity_code)}
            >
              <circle
                cx={cx}
                cy={cy}
                r={isSelected ? 6.5 : 4.2}
                fill={color}
                stroke={isSelected ? "#111827" : "#ffffff"}
                strokeWidth={isSelected ? 2 : 1}
              />
              {(isSelected || item.flight_count >= 18) && !isDimmed && (
                <text
                  x={cx + 6}
                  y={cy + 3}
                  fill="#1e293b"
                  fontSize="8.5"
                  fontWeight="700"
                >
                  {item.entity_code}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {hovered && (
        <div className="pca-hover-pill">
          <span
            className="pca-hover-dot"
            style={{ background: CLUSTER_COLORS[hovered.cluster_id] || "#38bdf8" }}
          />
          <strong>{hovered.entity_code}</strong> ({hovered.short_label}) ·{" "}
          {hovered.flight_count} chuyến · Trễ TB: +{hovered.avg_delay_minutes.toFixed(1)}p · PCA(
          {hovered.pca_x.toFixed(2)}, {hovered.pca_y.toFixed(2)})
        </div>
      )}
    </div>
  );
}
