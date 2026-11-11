import { ClusterCentroid } from "../flight-types";
import { US_AIRPORT_COORDS } from "../us-airports";
import { CustomSelect } from "./custom-select";
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

  const originOptions = [
    { value: "all", label: `Tất cả sân bay đi (${uniqueOrigins.length})` },
    ...uniqueOrigins.map(code => ({
      value: code,
      label: `Đi từ: ${code} (${US_AIRPORT_COORDS[code]?.city || code})`,
    })),
  ];

  const destOptions = [
    { value: "all", label: `Tất cả sân bay đến (${uniqueDests.length})` },
    ...uniqueDests.map(code => ({
      value: code,
      label: `Đến: ${code} (${US_AIRPORT_COORDS[code]?.city || code})`,
    })),
  ];

  const carrierOptions = [
    { value: "all", label: `Tất cả hãng bay (${uniqueCarriers.length})` },
    ...uniqueCarriers.map(code => ({
      value: code,
      label: `Hãng: ${code}`,
    })),
  ];

  const statusOptions = [
    { value: "all", label: "Mọi trạng thái Delay" },
    { value: "on_time", label: "Đúng giờ (< 15p)" },
    { value: "moderate_delay", label: "Trễ nhẹ (15–44p)" },
    { value: "severe_delay", label: "Trễ nặng (≥ 45p)" },
  ];

  const clusterOptions = [
    { value: "all", label: "Tất cả cụm K-Means (4 cụm)" },
    ...centroids.map(c => ({
      value: String(c.cluster_id),
      label: `Cụm ${c.cluster_id}: ${c.short_label} (${c.entity_count})`,
    })),
  ];

  return (
    <div className="filter-bar">
      <div className="filters">
        <CustomSelect
          ariaLabel="Sân bay đi"
          icon="plane"
          value={airport}
          onChange={setAirport}
          options={originOptions}
          highlightActive
        />

        <CustomSelect
          ariaLabel="Sân bay đến"
          value={destAirport}
          onChange={setDestAirport}
          options={destOptions}
          highlightActive
        />

        <CustomSelect
          ariaLabel="Hãng bay"
          value={carrier}
          onChange={setCarrier}
          options={carrierOptions}
          highlightActive
        />

        <CustomSelect
          ariaLabel="Lọc trạng thái trễ"
          value={flightStatus}
          onChange={setFlightStatus}
          options={statusOptions}
          highlightActive
        />

        {centroids.length > 0 && (
          <CustomSelect
            ariaLabel="Lọc theo cụm K-Means"
            icon="cluster"
            value={selectedClusterId === null ? "all" : String(selectedClusterId)}
            onChange={val => setSelectedClusterId(val === "all" ? null : Number(val))}
            options={clusterOptions}
            highlightActive
          />
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
