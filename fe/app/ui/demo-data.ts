// Dữ liệu tổng hợp để review UI. Thay bằng response API khi tích hợp backend.
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
export const riskOf = (probability: number) => probability >= 60 ? "high" : probability >= 30 ? "medium" : "low";
export const riskLabels = { high: "Nguy cơ cao", medium: "Trung bình", low: "Nguy cơ thấp" };
export const number = (value: number) => new Intl.NumberFormat("vi-VN").format(value);
