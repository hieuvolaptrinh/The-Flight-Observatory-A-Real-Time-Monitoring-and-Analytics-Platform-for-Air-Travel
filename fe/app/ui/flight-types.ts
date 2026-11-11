// Type definitions for flight items (ingested_flights), server-side SQL metadata, and clustering/prediction schemas

export type ViewMode = "overview" | "flights" | "clustering" | "forecast" | "analytics";

export type IconName =
  | "plane"
  | "grid"
  | "spark"
  | "chart"
  | "clock"
  | "arrow"
  | "download"
  | "refresh"
  | "calendar"
  | "search"
  | "chevron"
  | "check"
  | "alert"
  | "globe"
  | "cluster";

export interface FlightItem {
  flight_key: string;
  fl_date: string;
  op_unique_carrier: string;
  carrier_name: string;
  tail_num: string;
  op_carrier_fl_num: string;
  flight_code: string;
  origin: string;
  dest: string;
  route: string;
  crs_dep_time: string;
  crs_arr_time: string;
  crs_elapsed_time: number;
  distance: number;
  delay_minutes: number;
  delay_status: "on_time" | "moderate_delay" | "severe_delay";
  is_delayed: number;
  day_of_week?: number;
  dep_hour?: number;
  ingested_at: string;
}

export interface ServerFlightMeta {
  total_stored: number;
  filtered_count: number;
  returned_count: number;
  limit: number;
  offset: number;
  delayed_count: number;
  on_time_count: number;
  moderate_delay_count: number;
  severe_delay_count: number;
  delay_rate_pct: number;
  avg_delay_minutes: number;
  avg_distance: number;
  carrier_delays: { code: string; avg_delay: number; flight_count: number }[];
  available_filters: {
    origins: string[];
    destinations: string[];
    carriers: string[];
  };
  last_batch?: {
    window_start?: number;
    window_end?: number;
    inserted_count?: number;
    duplicate_count?: number;
  } | null;
}

export interface ClusterCentroid {
  run_id: string;
  cluster_id: number;
  cluster_name: string;
  short_label: string;
  color_code: string;
  interpretation: string;
  entity_count: number;
  share_pct: number;
  avg_flights: number;
  avg_routes: number;
  avg_distance: number;
  avg_elapsed_time: number;
  peak_hour_ratio: number;
  avg_delay_minutes: number;
  delay_rate_pct: number;
  radar_metrics?: Record<string, number>;
  top_airports?: string[];
}

export interface ClusterAssignment {
  run_id: string;
  entity_type: "airport" | "route";
  entity_code: string;
  entity_name: string;
  cluster_id: number;
  cluster_name: string;
  short_label: string;
  flight_count: number;
  route_count: number;
  avg_distance: number;
  avg_elapsed_time: number;
  peak_hour_ratio: number;
  avg_delay_minutes: number;
  delay_rate_pct: number;
  pca_x: number;
  pca_y: number;
  distance_to_centroid: number;
  membership_probabilities?: Record<string, number>;
}

export interface ClusteringMeta {
  run?: {
    run_id: string;
    model_version: string;
    algorithm: string;
    n_clusters: number;
    silhouette_score: number;
    inertia: number;
    total_airports: number;
    total_routes: number;
    source_flights_count: number;
    created_at: string;
  };
  entity_type: "airport" | "route";
  n_clusters: number;
  silhouette_score: number;
  inertia: number;
  total_airports: number;
  total_routes: number;
  source_flights_count: number;
  centroids: ClusterCentroid[];
}

export interface AirportStat {
  code: string;
  name: string;
  city: string;
  flights: number;
  rate: number;
  delay: number;
}

export interface CarrierStat {
  code: string;
  name: string;
  flights: number;
  rate: number;
}

export interface PredictionItem {
  flight: string;
  carrier: string;
  origin: string;
  destination: string;
  time: string;
  delay: number;
  probability: number;
}

export interface RawFlightItem {
  RAW_ID: number;
  ROW_NUMBER: number;
  DAY_OF_WEEK: string;
  FL_DATE: string;
  OP_UNIQUE_CARRIER: string;
  CARRIER_NAME?: string | null;
  TAIL_NUM?: string | null;
  OP_CARRIER_FL_NUM: string;
  ORIGIN_AIRPORT_ID: string;
  ORIGIN_AIRPORT_SEQ_ID: string;
  ORIGIN_CITY_MARKET_ID: string;
  ORIGIN: string;
  DEST_AIRPORT_ID: string;
  DEST_AIRPORT_SEQ_ID: string;
  DEST_CITY_MARKET_ID: string;
  DEST: string;
  CRS_DEP_TIME: string;
  CRS_ARR_TIME: string;
  CRS_ELAPSED_TIME: string;
  DISTANCE: string;
}

export interface RawFlightsResponse {
  fetched_at: string;
  window_start: number;
  window_end: number;
  window_size: number;
  slide_step: number;
  total: number;
  data: RawFlightItem[];
}

export const CLUSTER_COLORS: Record<number, string> = {
  0: "#ef4444", // Coral Red - Mega-Hub high delay pressure
  1: "#f59e0b", // Amber Orange - Transcontinental long-haul
  2: "#3b82f6", // Sky Blue - Regional medium-haul routes
  3: "#10b981", // Emerald Green - Stable operations, high on-time rate
};

export const statusLabels: Record<FlightItem["delay_status"], string> = {
  on_time: "Đúng giờ (< 15p)",
  moderate_delay: "Trễ nhẹ (15–44p)",
  severe_delay: "Trễ nặng (≥ 45p)",
};

export const statusBadgeClass: Record<FlightItem["delay_status"], "low" | "medium" | "high"> = {
  on_time: "low",
  moderate_delay: "medium",
  severe_delay: "high",
};

export const riskOf = (probability: number) =>
  probability >= 60 ? "high" : probability >= 30 ? "medium" : "low";

export const riskLabels = {
  high: "Nguy cơ cao",
  medium: "Trung bình",
  low: "Nguy cơ thấp",
};

export const number = (value: number) => new Intl.NumberFormat("vi-VN").format(value);
