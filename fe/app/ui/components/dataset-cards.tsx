import { useEffect, useState } from "react";
import { apiRequest } from "../api-client";
import { number } from "../flight-types";
import { Metric } from "./metric-card";

export function DatasetCards() {
  const [samples, setSamples] = useState<number>();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const request = new AbortController();
    apiRequest<{ sources: { training_samples: number }[] }>("/analytics/dataset", { signal: request.signal })
      .then(result => setSamples(result.sources.reduce((total, source) => total + source.training_samples, 0)))
      .catch(() => { if (!request.signal.aborted) setFailed(true); });
    return () => request.abort();
  }, []);

  if (failed) return <p className="analytics-empty" role="status">Chưa tải được số mẫu huấn luyện.</p>;
  return (
    <section className="metrics" aria-label="Dữ liệu huấn luyện">
      <Metric title="Mẫu đủ điều kiện huấn luyện" value={samples === undefined ? "…" : number(samples)}
        unit="mẫu" icon="chart" note="Có số phút chậm khởi hành thực tế và đủ đặc trưng lịch bay" />
    </section>
  );
}
