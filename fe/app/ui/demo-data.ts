// Dữ liệu tổng hợp để review UI. Tự động thay bằng response API khi kết nối backend.
export const airports = [
  { code: "JFK", name: "John F. Kennedy", city: "New York", flights: 1842, rate: 28.4, delay: 24 },
  { code: "ORD", name: "O’Hare International", city: "Chicago", flights: 2310, rate: 25.6, delay: 22 },
  { code: "LAX", name: "Los Angeles International", city: "Los Angeles", flights: 2184, rate: 21.8, delay: 19 },
  { code: "DFW", name: "Dallas Fort Worth", city: "Dallas", flights: 2016, rate: 18.2, delay: 16 },
  { code: "ATL", name: "Hartsfield–Jackson", city: "Atlanta", flights: 2498, rate: 15.6, delay: 14 },
  { code: "SFO", name: "San Francisco International", city: "San Francisco", flights: 1630, rate: 14.8, delay: 13 },
];
export const carriers = [
  { code: "AA", name: "American Airlines", flights: 3420, rate: 24.8 },
  { code: "UA", name: "United Airlines", flights: 2980, rate: 22.1 },
  { code: "WN", name: "Southwest Airlines", flights: 3160, rate: 18.6 },
  { code: "DL", name: "Delta Air Lines", flights: 2920, rate: 14.2 },
];
export const predictions = [
  { flight: "AA 102", carrier: "AA", origin: "JFK", destination: "LAX", time: "08:30", delay: 42, probability: 82 },
  { flight: "UA 245", carrier: "UA", origin: "ORD", destination: "SFO", time: "09:15", delay: 35, probability: 76 },
  { flight: "DL 418", carrier: "DL", origin: "ATL", destination: "JFK", time: "10:00", delay: 8, probability: 18 },
  { flight: "WN 730", carrier: "WN", origin: "LAX", destination: "DFW", time: "11:45", delay: 21, probability: 48 },
  { flight: "AA 856", carrier: "AA", origin: "DFW", destination: "ORD", time: "13:20", delay: 14, probability: 34 },
  { flight: "UA 512", carrier: "UA", origin: "SFO", destination: "JFK", time: "14:10", delay: 6, probability: 12 },
  { flight: "DL 921", carrier: "DL", origin: "JFK", destination: "ATL", time: "15:30", delay: 31, probability: 68 },
  { flight: "WN 304", carrier: "WN", origin: "ORD", destination: "LAX", time: "16:45", delay: 27, probability: 57 },
  { flight: "AA 637", carrier: "AA", origin: "ATL", destination: "DFW", time: "17:15", delay: 5, probability: 15 },
  { flight: "DL 276", carrier: "DL", origin: "LAX", destination: "SFO", time: "18:00", delay: 18, probability: 42 },
  { flight: "UA 880", carrier: "UA", origin: "DFW", destination: "JFK", time: "19:10", delay: 29, probability: 64 },
  { flight: "WN 159", carrier: "WN", origin: "SFO", destination: "ATL", time: "20:30", delay: 9, probability: 24 },
];

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
  ingested_at: string;
}

export const demoFlights: FlightItem[] = [
  { flight_key: "2025-01-06_AA_16_SFO_JFK_1321", fl_date: "2025-01-06", op_unique_carrier: "AA", carrier_name: "American Airlines", tail_num: "N102NN", op_carrier_fl_num: "16", flight_code: "AA 16", origin: "SFO", dest: "JFK", route: "SFO → JFK", crs_dep_time: "13:21", crs_arr_time: "21:59", crs_elapsed_time: 338, distance: 2586, delay_minutes: 4, delay_status: "on_time", is_delayed: 0, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_AA_179_JFK_SFO_0829", fl_date: "2025-01-06", op_unique_carrier: "AA", carrier_name: "American Airlines", tail_num: "N102NN", op_carrier_fl_num: "179", flight_code: "AA 179", origin: "JFK", dest: "SFO", route: "JFK → SFO", crs_dep_time: "08:29", crs_arr_time: "12:22", crs_elapsed_time: 413, distance: 2586, delay_minutes: 28, delay_status: "moderate_delay", is_delayed: 1, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_AA_2056_CLT_LGA_1839", fl_date: "2025-01-06", op_unique_carrier: "AA", carrier_name: "American Airlines", tail_num: "N102UW", op_carrier_fl_num: "2056", flight_code: "AA 2056", origin: "CLT", dest: "LGA", route: "CLT → LGA", crs_dep_time: "18:39", crs_arr_time: "20:30", crs_elapsed_time: 111, distance: 544, delay_minutes: 56, delay_status: "severe_delay", is_delayed: 1, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_UA_412_ORD_LAX_1510", fl_date: "2025-01-06", op_unique_carrier: "UA", carrier_name: "United Airlines", tail_num: "N384UA", op_carrier_fl_num: "412", flight_code: "UA 412", origin: "ORD", dest: "LAX", route: "ORD → LAX", crs_dep_time: "15:10", crs_arr_time: "17:45", crs_elapsed_time: 275, distance: 1744, delay_minutes: 34, delay_status: "moderate_delay", is_delayed: 1, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_DL_809_ATL_DFW_0940", fl_date: "2025-01-06", op_unique_carrier: "DL", carrier_name: "Delta Air Lines", tail_num: "N912DL", op_carrier_fl_num: "809", flight_code: "DL 809", origin: "ATL", dest: "DFW", route: "ATL → DFW", crs_dep_time: "09:40", crs_arr_time: "11:05", crs_elapsed_time: 145, distance: 731, delay_minutes: 2, delay_status: "on_time", is_delayed: 0, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_WN_1105_LAX_ORD_1620", fl_date: "2025-01-06", op_unique_carrier: "WN", carrier_name: "Southwest Airlines", tail_num: "N781WN", op_carrier_fl_num: "1105", flight_code: "WN 1105", origin: "LAX", dest: "ORD", route: "LAX → ORD", crs_dep_time: "16:20", crs_arr_time: "22:15", crs_elapsed_time: 235, distance: 1744, delay_minutes: 19, delay_status: "moderate_delay", is_delayed: 1, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_DL_314_JFK_ATL_1745", fl_date: "2025-01-06", op_unique_carrier: "DL", carrier_name: "Delta Air Lines", tail_num: "N504DN", op_carrier_fl_num: "314", flight_code: "DL 314", origin: "JFK", dest: "ATL", route: "JFK → ATL", crs_dep_time: "17:45", crs_arr_time: "20:25", crs_elapsed_time: 160, distance: 760, delay_minutes: 62, delay_status: "severe_delay", is_delayed: 1, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_UA_618_SFO_ORD_0715", fl_date: "2025-01-06", op_unique_carrier: "UA", carrier_name: "United Airlines", tail_num: "N291UA", op_carrier_fl_num: "618", flight_code: "UA 618", origin: "SFO", dest: "ORD", route: "SFO → ORD", crs_dep_time: "07:15", crs_arr_time: "13:30", crs_elapsed_time: 255, distance: 1846, delay_minutes: 0, delay_status: "on_time", is_delayed: 0, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_WN_502_DFW_LAX_1130", fl_date: "2025-01-06", op_unique_carrier: "WN", carrier_name: "Southwest Airlines", tail_num: "N442WN", op_carrier_fl_num: "502", flight_code: "WN 502", origin: "DFW", dest: "LAX", route: "DFW → LAX", crs_dep_time: "11:30", crs_arr_time: "12:55", crs_elapsed_time: 205, distance: 1235, delay_minutes: 7, delay_status: "on_time", is_delayed: 0, ingested_at: "2026-11-07T02:30:00Z" },
  { flight_key: "2025-01-06_AA_924_ORD_JFK_1915", fl_date: "2025-01-06", op_unique_carrier: "AA", carrier_name: "American Airlines", tail_num: "N819AA", op_carrier_fl_num: "924", flight_code: "AA 924", origin: "ORD", dest: "JFK", route: "ORD → JFK", crs_dep_time: "19:15", crs_arr_time: "22:35", crs_elapsed_time: 140, distance: 740, delay_minutes: 49, delay_status: "severe_delay", is_delayed: 1, ingested_at: "2026-11-07T02:30:00Z" },
];

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

export const riskOf = (probability: number) => probability >= 60 ? "high" : probability >= 30 ? "medium" : "low";
export const riskLabels = { high: "Nguy cơ cao", medium: "Trung bình", low: "Nguy cơ thấp" };
export const number = (value: number) => new Intl.NumberFormat("vi-VN").format(value);
