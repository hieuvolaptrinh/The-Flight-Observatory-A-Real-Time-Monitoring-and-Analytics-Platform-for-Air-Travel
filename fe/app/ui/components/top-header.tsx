import Link from "next/link";
import { Icon } from "./icons";
import { IngestionCountdown } from "./ingestion-countdown";

interface TopHeaderProps {
  pageTitle: string;
  pageSubtitle: string;
  apiMode: "gateway" | "ingestion" | "demo";
  busy: boolean;
  onTriggerClustering: () => void;
  onExportCsv: () => void;
  runLabel?: string;
  showRun?: boolean;
}

export function TopHeader({
  pageTitle,
  pageSubtitle,
  apiMode,
  busy,
  onTriggerClustering,
  onExportCsv,
  runLabel = "Chạy K-Means",
  showRun = true,
}: TopHeaderProps) {
  return (
    <header className="top-command-bar">
      <div className="top-brand-group">
        <Link href="/flights" className="brand-logo">
          <span className="brand-mark">
            <img src="/logo.png" alt="FlightLens Logo" className="brand-logo-img" />
          </span>
          <strong>
            flightlens<span className="brand-period">+</span>
          </strong>
        </Link>

        <span className="top-divider" />

        <div className="top-heading-info">
          <h1>{pageTitle}</h1>
          <p>{pageSubtitle}</p>
        </div>
      </div>

      <div className="top-telemetry-actions">
        <span className={`status-badge-pill ${apiMode !== "demo" ? "lavender" : "peach"}`}>
          <span className="badge-dot" />
          {apiMode !== "demo" ? "API qua gateway" : "Đang kết nối"}
        </span>

        <div className="top-action-buttons">
          {showRun && <button
            type="button"
            className="button secondary"
            onClick={onTriggerClustering}
            disabled={busy}
          >
            <Icon name="cluster" size={15} />
            {runLabel}
          </button>}
          <button type="button" className="button secondary" onClick={onExportCsv}>
            <Icon name="download" size={15} />
            Xuất CSV
          </button>
          <IngestionCountdown direct={apiMode === "ingestion"} />
        </div>
      </div>
    </header>
  );
}
