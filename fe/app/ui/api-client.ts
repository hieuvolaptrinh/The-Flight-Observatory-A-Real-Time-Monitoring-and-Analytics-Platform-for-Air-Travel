import { API_BASE } from "./flight-types";

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(options.method && options.method !== "GET" ? 65000 : 20000);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetch(API_BASE.replace(/\/$/, "") + path, { ...options, cache: "no-store", signal });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error("Không kết nối được API. Kiểm tra gateway và service backend đang chạy.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : "HTTP " + response.status;
    throw new Error(detail);
  }
  if (body === null) throw new Error("API trả dữ liệu không hợp lệ.");
  return body as T;
}
