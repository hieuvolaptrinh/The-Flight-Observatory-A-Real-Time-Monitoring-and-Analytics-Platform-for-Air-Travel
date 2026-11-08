import { ClusterCentroid } from "../flight-types";
import { US_AIRPORT_COORDS } from "../us-airports";
import { Icon } from "./icons";

interface FilterBarProps {
  airport: string;
  setAirport: (val: string) => void;
  destAirport: string;
  setDestAirport: (val: string) => void;
  carrier: string;
  setCarrier: (val: string) => void;
  flightStatus: string;
  setFlightStatus: (val: string) => void;
  selectedClusterId: number | null;
  setSelectedClusterId: (val: number | null) => void;
  search: string;
  setSearch: (val: string) => void;
  uniqueOrigins: string[];
  uniqueDests: string[];
  uniqueCarriers: string[];
  centroids: ClusterCentroid[];
  busy: boolean;
  onRefresh: () => void;
  onResetFilters: () => void;
}

export function FilterBar({
  airport,
  setAirport,
  destAirport,
  setDestAirport,
  carrier,
  setCarrier,
  flightStatus,
  setFlightStatus,
  selectedClusterId,
  setSelectedClusterId,
  search,
  setSearch,
  uniqueOrigins,
  uniqueDests,
  uniqueCarriers,
  centroids,
  busy,
  onRefresh,
  onResetFilters,
}: FilterBarProps) {
  const hasActiveFilter =
    airport !== "all" ||
    destAirport !== "all" ||
    carrier !== "all" ||
    flightStatus !== "all" ||
    selectedClusterId !== null ||
    search.trim() !== "";

  return (
    <div className="filter-bar">
      <div className="filters">
        <div className="filter-control">
          <Icon name="plane" size={15} />
          <select
            aria-label="Sân bay đi"
            value={airport}
            onChange={e => setAirport(e.target.value)}
          >
            <option value="all">Tất cả sân bay đi ({uniqueOrigins.length})</option>
            {uniqueOrigins.map(code => (
              <option key={code} value={code}>
                Đi từ: {code} ({US_AIRPORT_COORDS[code]?.city || code})
              </option>
            ))}
          </select>
        </div>

        <div className="filter-control">
          <select
            aria-label="Sân bay đến"
            value={destAirport}
            onChange={e => setDestAirport(e.target.value)}
          >
            <option value="all">Tất cả sân bay đến ({uniqueDests.length})</option>
            {uniqueDests.map(code => (
              <option key={code} value={code}>
                Đến: {code} ({US_AIRPORT_COORDS[code]?.city || code})
              </option>
            ))}
          </select>
        </div>

        <div className="filter-control">
          <select
            aria-label="Hãng bay"
            value={carrier}
            onChange={e => setCarrier(e.target.value)}
          >
            <option value="all">Tất cả hãng bay ({uniqueCarriers.length})</option>
            {uniqueCarriers.map(code => (
              <option key={code} value={code}>
                Hãng: {code}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-control">
          <select
            aria-label="Lọc trạng thái trễ"
            value={flightStatus}
            onChange={e => setFlightStatus(e.target.value)}
          >
            <option value="all">Mọi trạng thái Delay</option>
            <option value="on_time">Đúng giờ (&lt; 15p)</option>
            <option value="moderate_delay">Trễ nhẹ (15–44p)</option>
            <option value="severe_delay">Trễ nặng (≥ 45p)</option>
          </select>
        </div>

        {centroids.length > 0 && (
          <div className="filter-control">
            <Icon name="cluster" size={15} />
            <select
              aria-label="Lọc theo cụm K-Means"
              value={selectedClusterId === null ? "all" : String(selectedClusterId)}
              onChange={e =>
                setSelectedClusterId(e.target.value === "all" ? null : Number(e.target.value))
              }
            >
              <option value="all">Tất cả cụm K-Means (4 cụm)</option>
              {centroids.map(c => (
                <option key={c.cluster_id} value={c.cluster_id}>
                  Cụm {c.cluster_id}: {c.short_label} ({c.entity_count})
                </option>
              ))}
            </select>
          </div>
        )}

        <label className="filter-search">
          <Icon name="search" size={15} />
          <input
            placeholder="Tìm chuyến bay, tàu bay (Tail), mã sân bay…"
            aria-label="Tìm kiếm chuyến bay"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </label>
      </div>

      <div className="filter-bar-right">
        {hasActiveFilter && (
          <button type="button" className="reset-filter-btn" onClick={onResetFilters}>
            Xóa lọc
          </button>
        )}
        <button
          type="button"
          className="refresh-button"
          onClick={onRefresh}
          disabled={busy}
          aria-label="Làm mới dữ liệu"
        >
          <span className={busy ? "spinning" : ""}>
            <Icon name="refresh" size={15} />
          </span>
          {busy ? "Đang tải…" : "Đồng bộ"}
        </button>
      </div>
    </div>
  );
}
