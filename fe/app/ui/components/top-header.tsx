import Link from "next/link";
import { Icon } from "./icons";

interface TopHeaderProps {
  pageTitle: string;
  pageSubtitle: string;
  apiMode: "gateway" | "ingestion" | "demo";
  busy: boolean;
  onTriggerIngestion: () => void;
  onTriggerClustering: () => void;
  onExportCsv: () => void;
}

export function TopHeader({
  pageTitle,
  pageSubtitle,
  apiMode,
  busy,
  onTriggerIngestion,
  onTriggerClustering,
  onExportCsv,
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
          {apiMode !== "demo" ? `Gateway · ${apiMode.toUpperCase()}` : "Đang kết nối"}
        </span>

        <div className="top-action-buttons">
          <button
            type="button"
            className="button secondary"
            onClick={onTriggerClustering}
            disabled={busy}
          >
            <Icon name="cluster" size={15} />
            Chạy K-Means
          </button>
          <button type="button" className="button secondary" onClick={onExportCsv}>
            <Icon name="download" size={15} />
            Xuất CSV
          </button>
          <button
            type="button"
            className="button primary-action"
            onClick={onTriggerIngestion}
            disabled={busy}
          >
            <Icon name="refresh" size={15} />
            Nạp batch mới (POST /run)
          </button>
        </div>
      </div>
    </header>
  );
}
