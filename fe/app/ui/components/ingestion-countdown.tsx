"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../flight-types";

type IngestionHealth = {
  scheduler_enabled: boolean;
  next_run_in_seconds: number | null;
  job_running: boolean;
};

export function IngestionCountdown({ direct }: { direct: boolean }) {
  const endpoint = direct ? "http://127.0.0.1:2004/health" : API_BASE + "/ingestion/health";
  const [label, setLabel] = useState("Đang đọc lịch");

  useEffect(() => {
    let health: IngestionHealth | undefined;
    let deadline = 0;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();

    function updateLabel() {
      if (!health) return;
      const remaining = deadline - performance.now();
      if (health.job_running) {
        setLabel("Đang nạp");
      } else if (!health.scheduler_enabled) {
        setLabel("Tự động tắt");
      } else if (health.next_run_in_seconds === null || remaining <= 0) {
        setLabel("Đang chờ");
      } else {
        const seconds = Math.ceil(remaining / 1000);
        const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
        setLabel(minutes + ":" + String(seconds % 60).padStart(2, "0"));
      }
    }

    async function sync() {
      try {
        const response = await fetch(endpoint, { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Could not read ingestion schedule");
        const next: IngestionHealth = await response.json();
        if (controller.signal.aborted) return;
        if (next.next_run_in_seconds === undefined) {
          health = undefined;
          setLabel("Chưa có lịch");
          return;
        }
        health = next;
        deadline = performance.now() + (next.next_run_in_seconds ?? 0) * 1000;
        updateLabel();
      } catch {
        if (!controller.signal.aborted) {
          health = undefined;
          setLabel("Mất kết nối");
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(sync, 5000);
      }
    }

    void sync();
    const ticker = setInterval(updateLabel, 1000);
    return () => {
      controller.abort();
      clearTimeout(timer);
      clearInterval(ticker);
    };
  }, [endpoint]);

  return (
    <span className="status-badge-pill ingestion-countdown" role="timer">
      Nạp tự động · <strong>{label}</strong>
    </span>
  );
}
