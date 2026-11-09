import Link from "next/link";
import { ViewMode } from "../flight-types";
import { Icon } from "./icons";

export function BottomNavDock({ view }: { view: ViewMode }) {
  const isOverview = view === "overview";
  const isFlights = view === "flights";
  const isClustering = view === "clustering";
  const isForecast = view === "forecast";

  return (
    <nav className="bottom-nav-dock" aria-label="Điều hướng chính">
      <Link
        href="/"
        aria-current={isOverview ? "page" : undefined}
        className={`dock-item ${isOverview ? "active" : ""}`}
      >
        <Icon name="grid" size={18} />
        <span>Tổng quan</span>
      </Link>

      <Link
        href="/flights"
        aria-current={isFlights ? "page" : undefined}
        className={`dock-item ${isFlights ? "active" : ""}`}
      >
        <Icon name="plane" size={18} />
        <span>Radar &amp; Chuyến bay</span>
        <small className="dock-badge live">LIVE</small>
      </Link>

      <Link
        href="/clustering"
        aria-current={isClustering ? "page" : undefined}
        className={`dock-item ${isClustering ? "active" : ""}`}
      >
        <Icon name="cluster" size={18} />
        <span>Phân cụm K-Means</span>
        <small className="dock-badge">PCA</small>
      </Link>

      <Link
        href="/forecast"
        aria-current={isForecast ? "page" : undefined}
        className={`dock-item ${isForecast ? "active" : ""}`}
      >
        <Icon name="spark" size={18} />
        <span>Dự báo AI</span>
      </Link>
    </nav>
  );
}
