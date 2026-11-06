"use client";

import Link from "next/link";
import { useState } from "react";
import { airports, carriers, predictions, riskOf, riskLabels, number } from "./demo-data";

type IconName = "plane" | "grid" | "spark" | "chart" | "clock" | "arrow" | "download" | "refresh" | "calendar" | "search" | "chevron" | "check" | "alert" | "globe";
function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    plane: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="m22 2-11 11" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" /><path d="M21 2v4m-2-2h4" /></>,
    chart: <path d="M4 4v16h17M8 15l4-5 4 3 5-7" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    download: <path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5" />,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M7 3v4m10-4v4M3 11h18" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    chevron: <path d="m8 10 4 4 4-4" />,
    check: <path d="m5 12 4 4L19 6" />,
    alert: <><path d="m12 3 10 18H2Z" /><path d="M12 9v4m0 3v1" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Metric({ title, value, unit, icon, note, color = "teal" }: { title: string; value: string; unit?: string; icon: IconName; note: string; color?: string }) {
  return <article className="metric"><div className="metric-top"><span>{title}</span><span className={`metric-icon ${color}`}><Icon name={icon} size={19} /></span></div><div className="metric-value">{value}<span>{unit}</span></div><div className="metric-note"><span className={`tiny-dot ${color}`} />{note}</div></article>;
}

function TrendChart({ rate, day }: { rate: number; day: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const values = [12,10,13,11,15,20,17,23,18,24,29,23,26].map(v => Math.min(39, v*rate/21));
  const points = values.map((v,i) => `${48+i*46},${190-v*3.7}`).join(" ");
  return <div className="trend-chart"><svg viewBox="0 0 640 235" role="img" aria-label={`Tỷ lệ chuyến bay trễ theo giờ ngày ${day}`}>
    <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#14a58e" stopOpacity=".21" /><stop offset="100%" stopColor="#14a58e" stopOpacity="0" /></linearGradient></defs>
    {[0,10,20,30,40].map(n => <g key={n}><line x1="48" x2="610" y1={190-n*3.7} y2={190-n*3.7} stroke="#e9edf0" strokeDasharray="4 5" /><text x="32" y={194-n*3.7} textAnchor="end">{n}%</text></g>)}
    <polygon points={`48,190 ${points} 600,190`} fill="url(#area)" /><polyline points={points} fill="none" stroke="#0b9d87" strokeWidth="3" strokeLinejoin="round" />
    {values.map((v,i) => <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}><rect x={30+i*46} y="30" width="40" height="165" fill="transparent" />{hover === i && <><line x1={48+i*46} x2={48+i*46} y1="30" y2="190" stroke="#0b9d87" strokeDasharray="3 3" /><circle cx={48+i*46} cy={190-v*3.7} r="5" fill="#0b9d87" stroke="white" strokeWidth="3" /><text x={Math.min(575,Math.max(70,48+i*46))} y={175-v*3.7} textAnchor="middle" className="chart-tooltip">{v.toFixed(1)}%</text></>}</g>)}
    {[0,2,4,6,8,10,12].map(i => <text key={i} x={48+i*46} y="220" textAnchor="middle">{String(i*2).padStart(2,"0")}:00</text>)}
  </svg></div>;
}

export default function Dashboard({ view }: { view: "overview" | "forecast" }) {
  const forecast = view === "forecast";
  const [airport,setAirport] = useState("all");
  const [carrier,setCarrier] = useState("all");
  const [day,setDay] = useState("06/11/2026");
  const [rankBy,setRankBy] = useState<"airports" | "carriers">("airports");
  const [risk,setRisk] = useState("all");
  const [search,setSearch] = useState("");
  const [sort,setSort] = useState("time");
  const [updated,setUpdated] = useState("14:35 · 06/11/2026 UTC");
  const [toast,setToast] = useState("");
  const [busy,setBusy] = useState(false);
  const selection = airports.filter(a => airport === "all" || a.code === airport);
  const carrierRate = carrier === "all" ? 1 : carriers.find(c => c.code === carrier)!.rate/20;
  const factor = (day === "06/11/2026" ? 1 : day === "05/11/2026" ? .91 : .86) * (carrier === "all" ? 1 : carriers.find(c => c.code === carrier)!.flights/12480);
  const total = Math.round(selection.reduce((s,a) => s+a.flights,0)*factor);
  const rate = selection.reduce((s,a) => s+a.rate*a.flights,0)/selection.reduce((s,a) => s+a.flights,0)*carrierRate;
  const delayed = Math.round(total*rate/100);
  const avg = selection.reduce((s,a) => s+a.delay*a.flights,0)/selection.reduce((s,a) => s+a.flights,0);
  const scoped = predictions.filter(p => (airport === "all" || p.origin === airport) && (carrier === "all" || p.carrier === carrier));
  const filtered = scoped.filter(p => (risk === "all" || riskOf(p.probability) === risk) && `${p.flight} ${p.origin} ${p.destination}`.toLowerCase().includes(search.toLowerCase())).sort((a,b) => sort === "risk" ? b.probability-a.probability : sort === "delay" ? b.delay-a.delay : a.time.localeCompare(b.time));
  const highCount = scoped.filter(p => riskOf(p.probability) === "high").length;
  const forecastAvg = scoped.length ? scoped.reduce((s,p) => s+p.delay,0)/scoped.length : 0;
  const meanProbability = scoped.length ? scoped.reduce((s,p) => s+p.probability,0)/scoped.length : 0;
  function notify(message: string) { setToast(message); setTimeout(() => setToast(""),4000); }
  function refresh() {
    setBusy(true);
    setTimeout(() => { setUpdated(new Intl.DateTimeFormat("vi-VN",{timeZone:"UTC",hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(new Date())+" · xem lại demo (UTC)"); setBusy(false); notify("Đã tải lại dữ liệu mẫu. Chưa kết nối API."); },650);
  }
  function exportCsv() {
    const rows = forecast ? [["flight","origin","destination","departure_local","forecast_date","delay_minutes","delay_probability_percent","risk"],...filtered.map(p => [p.flight,p.origin,p.destination,p.time,"2026-11-07",p.delay,p.probability,riskLabels[riskOf(p.probability)]])] : [["airport","date","carrier_filter","flights","delay_rate_percent"],...selection.map(a => [a.code,day,carrier,Math.round(a.flights*factor),(a.rate*carrierRate).toFixed(1)])];
    const blob = new Blob(["\uFEFF"+rows.map(row => row.join(",")).join("\r\n")],{type:"text/csv;charset=utf-8;"});
    const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href=url; link.download=`flightlens-${view}-demo.csv`; link.click(); URL.revokeObjectURL(url); notify("Đã xuất CSV theo bộ lọc hiện tại.");
  }
  return <div className="app-shell">
    <aside className="sidebar">
      <Link href="/" className="brand"><span className="brand-mark"><Icon name="plane" size={25} /></span><span>flightlens<span className="brand-period">.</span><small>FLIGHT INTELLIGENCE</small></span></Link>
      <div className="workspace"><span className="workspace-icon"><Icon name="globe" /></span><div>US Flight Operations<small>Không gian làm việc</small></div><span className="workspace-chevron"><Icon name="chevron" size={15} /></span></div>
      <div className="nav-label">KHÔNG GIAN PHÂN TÍCH</div>
      <nav aria-label="Điều hướng chính"><Link href="/" aria-label="Tổng quan" aria-current={!forecast ? "page" : undefined} className={!forecast ? "nav-item active" : "nav-item"}><Icon name="grid" />Tổng quan{!forecast && <span className="active-dot" />}</Link><Link href="/forecast" aria-label="Dự báo ngày mai" aria-current={forecast ? "page" : undefined} className={forecast ? "nav-item active" : "nav-item"}><Icon name="spark" />Dự báo ngày mai<span className="nav-new">AI</span></Link></nav>
      <div className="sidebar-bottom"><div className="sidebar-card"><span className="orbit-icon"><Icon name="chart" size={25} /></span><strong>Mỗi chuyến bay,<br />một góc nhìn rõ hơn.</strong><p>Theo dõi hôm nay.<br />Chủ động cho ngày mai.</p><span className="sidebar-card-line" /></div><div className="demo-status"><span className="status-dot" />Chế độ demo UI<span>v1.0</span></div><div className="profile"><span className="avatar">H</span><div>Hiếu<small>Flight Delay Project</small></div><span className="profile-badge">HV</span></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumbs">Workspace<span>/</span><strong>{forecast ? "Dự báo ngày mai" : "Tổng quan"}</strong></div><div className="topbar-right"><span className="sample-pill">DỮ LIỆU MẪU</span><span className="header-divider" /><Icon name="globe" size={17} /><span>Tiếng Việt</span><span className="mini-avatar">H</span></div></header>
      <main className="main-content">
        <div className="page-heading"><div><div className="eyebrow">{forecast ? "NHÌN TRƯỚC MỘT BƯỚC" : "BỨC TRANH TOÀN CẢNH"}</div><h1>{forecast ? "Dự báo ngày mai" : "Tổng quan chuyến bay"}<span className="heading-dot">.</span></h1><p>{forecast ? "Biến dữ liệu hôm nay thành sự chủ động cho ngày mai." : "Mọi chuyển động trên bầu trời, trong một góc nhìn."}</p></div><button className="button secondary" onClick={exportCsv} aria-label="Xuất báo cáo CSV"><Icon name="download" size={17} />Xuất báo cáo</button></div>
        <div className="filter-bar"><div className="filters"><div className="filter-control"><Icon name="calendar" size={17} />{forecast ? <span>Ngày mai · 07/11/2026</span> : <select aria-label="Ngày dữ liệu" value={day} onChange={e => setDay(e.target.value)}><option>06/11/2026</option><option>05/11/2026</option><option>04/11/2026</option></select>}</div><div className="filter-control"><Icon name="plane" size={17} /><select aria-label="Sân bay" value={airport} onChange={e => setAirport(e.target.value)}><option value="all">Tất cả sân bay</option>{airports.map(a => <option key={a.code} value={a.code}>{a.code} · {a.city}</option>)}</select></div><div className="filter-control"><select aria-label="Hãng bay" value={carrier} onChange={e => setCarrier(e.target.value)}><option value="all">Tất cả hãng bay</option>{carriers.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}</select></div></div><button className="refresh-button" onClick={refresh} disabled={busy} aria-label="Làm mới dữ liệu mẫu"><span className={busy ? "spinning" : ""}><Icon name="refresh" size={16} /></span>{busy ? "Đang tải…" : "Làm mới"}</button></div>
        <div className="update-line"><span className="status-dot" /><span>Dữ liệu mẫu · Lần cập nhật: <strong>{updated}</strong></span><span className="update-divider">|</span><span>{forecast ? "Phiên bản mô hình minh họa: v1.2" : "Chu kỳ cập nhật dự kiến: 5 phút"}</span></div>
        {forecast ? <>
          <section className="forecast-banner"><span className="banner-icon"><Icon name="spark" size={26} /></span><div><span className="banner-eyebrow">DỰ BÁO CHO THỨ BẢY, 07 THÁNG 11</span><h2>Sẵn sàng cho hành trình ngày mai.</h2><p>Nhận diện sớm chuyến bay có nguy cơ trễ để chủ động lên kế hoạch.</p></div><div className="banner-date"><strong>07</strong><span>THÁNG 11, 2026</span></div><span className="banner-orbit" /></section>
          <section className="metrics" aria-label="Chỉ số dự báo"><Metric title="Chuyến bay được dự báo" value={number(scoped.length)} unit="chuyến" icon="plane" note="Trong phạm vi dữ liệu mẫu" /><Metric title="Delay dự kiến trung bình" value={forecastAvg.toFixed(1)} unit="phút" icon="clock" note="Trung bình các chuyến đã lọc" color="blue" /><Metric title="Chuyến bay nguy cơ cao" value={number(highCount)} unit="chuyến" icon="alert" note="Xác suất trễ từ 60%" color="coral" /><Metric title="Xác suất trễ trung bình" value={meanProbability.toFixed(1)} unit="%" icon="chart" note="Trung bình xác suất phân loại" color="purple" /></section>
          <div className="forecast-charts"><section className="panel"><div className="panel-heading"><div><h2>Delay dự kiến theo sân bay</h2><p>Số phút trễ trung bình tại sân bay khởi hành</p></div><span className="chart-unit">ĐƠN VỊ: PHÚT</span></div><div className="airport-bars">{selection.map(a => { const rows=scoped.filter(p => p.origin===a.code); const value=rows.length ? rows.reduce((s,p) => s+p.delay,0)/rows.length : 0; return <div className="airport-bar" key={a.code}><span className="airport-bar-value">{rows.length ? value.toFixed(1) : "—"}</span><div className="airport-bar-track"><div style={{height:`${value/45*100}%`}} className={value>=28 ? "bar-coral" : "bar-teal"} /></div><strong>{a.code}</strong></div>; })}</div></section><section className="panel risk-panel"><div className="panel-heading"><div><h2>Phân bố nguy cơ</h2><p>Xác suất chuyến bay trễ ≥ 15 phút</p></div><Icon name="spark" size={19} /></div><div className="risk-distribution">{(["high","medium","low"] as const).map(r => { const count=scoped.filter(p => riskOf(p.probability)===r).length; return <button className={`risk-row ${risk===r ? "selected" : ""}`} key={r} onClick={() => setRisk(risk===r ? "all" : r)} aria-pressed={risk===r}><span className={`risk-symbol ${r}`}><Icon name={r==="high" ? "alert" : r==="low" ? "check" : "clock"} size={18} /></span><span className="risk-row-text"><strong>{riskLabels[r]}</strong><small>{r==="high" ? "≥ 60%" : r==="medium" ? "30% – dưới 60%" : "Dưới 30%"}</small></span><strong>{count}<small>chuyến</small></strong><span className={`risk-mini-bar ${r}`} style={{width:`${scoped.length ? count/scoped.length*100 : 0}%`}} /></button>; })}</div><div className="panel-footnote">Chọn một nhóm để lọc danh sách bên dưới.</div></section></div>
          <section className="panel predictions-panel"><div className="panel-heading"><div><h2>Chi tiết dự báo <span className="count-pill">{filtered.length}</span></h2><p>Ngày 07/11/2026 · Giờ khởi hành theo địa phương sân bay</p></div><div className="table-tools"><label className="search-box"><Icon name="search" size={16} /><input placeholder="Tìm chuyến bay, sân bay…" aria-label="Tìm chuyến bay" value={search} onChange={e => setSearch(e.target.value)} /></label><select aria-label="Lọc nguy cơ" value={risk} onChange={e => setRisk(e.target.value)}><option value="all">Tất cả nguy cơ</option><option value="high">Nguy cơ cao</option><option value="medium">Trung bình</option><option value="low">Nguy cơ thấp</option></select><select aria-label="Sắp xếp" value={sort} onChange={e => setSort(e.target.value)}><option value="time">Giờ khởi hành</option><option value="risk">Nguy cơ giảm dần</option><option value="delay">Delay giảm dần</option></select></div></div><div className="table-scroll"><table><thead><tr><th>CHUYẾN BAY</th><th>HÀNH TRÌNH</th><th>KHỞI HÀNH</th><th>DELAY DỰ KIẾN</th><th>XÁC SUẤT TRỄ</th><th>PHÂN LOẠI NGUY CƠ</th></tr></thead><tbody>{filtered.map(p => <tr key={p.flight}><td><span className={`airline-mark airline-${p.carrier}`}>{p.carrier}</span><strong>{p.flight}</strong></td><td><span className="route">{p.origin}<Icon name="arrow" size={15} />{p.destination}</span></td><td className="tabular">{p.time}</td><td><strong className={p.delay>=30 ? "coral-text" : ""}>+{p.delay}</strong><span className="muted"> phút</span></td><td><div className="probability"><span>{p.probability}%</span><div><span className={riskOf(p.probability)} style={{width:`${p.probability}%`}} /></div></div></td><td><span className={`risk-badge ${riskOf(p.probability)}`}><span />{riskLabels[riskOf(p.probability)]}</span></td></tr>)}</tbody></table>{!filtered.length && <div className="empty-state"><Icon name="search" size={30} /><h3>Không có chuyến bay phù hợp</h3><p>Thử tìm kiếm khác hoặc đặt lại bộ lọc.</p><button className="button secondary" onClick={() => {setAirport("all");setCarrier("all");setSearch("");setRisk("all");}}>Đặt lại bộ lọc</button></div>}</div><div className="table-footer">Hiển thị {filtered.length} / {scoped.length} chuyến trong phạm vi đã chọn<span>Kết quả minh họa · Chưa chạy mô hình thực tế</span></div></section>
        </> : <>
          <section className="metrics" aria-label="Chỉ số tổng quan"><Metric title="Tổng chuyến bay" value={number(total)} icon="plane" note={`${selection.length} sân bay trong phạm vi theo dõi`} /><Metric title="Tỷ lệ chuyến bay trễ" value={rate.toFixed(1)} unit="%" icon="chart" note="Quy ước demo: trễ từ 15 phút" color="coral" /><Metric title="Số chuyến bay trễ" value={number(delayed)} unit="chuyến" icon="clock" note="Theo ngày và bộ lọc đã chọn" color="blue" /><Metric title="Delay trung bình" value={avg.toFixed(1)} unit="phút" icon="clock" note="Trung bình trên tất cả chuyến bay" color="purple" /></section>
          <div className="overview-charts"><section className="panel"><div className="panel-heading"><div><h2>Nhịp bay trong ngày</h2><p>Biến động tỷ lệ chuyến bay trễ theo giờ · UTC</p></div><span className="legend"><i />Tỷ lệ trễ</span></div><TrendChart rate={rate} day={day} /><div className="chart-caption"><Icon name="clock" size={15} /><span>Dữ liệu biểu đồ minh họa cho ngày {day}</span></div></section><section className="panel donut-panel"><div className="panel-heading"><div><h2>Trạng thái chuyến bay</h2><p>Tỷ trọng theo dữ liệu đã lọc</p></div></div><div className="donut" style={{background:`conic-gradient(#0b9d87 0 ${100-rate}%, #f3aa77 ${100-rate}% 100%)`}} role="img" aria-label={`${(100-rate).toFixed(1)}% đúng giờ, ${rate.toFixed(1)}% trễ`}><div><span>Đúng giờ</span><strong>{(100-rate).toFixed(1)}<small>%</small></strong><span className="donut-check"><Icon name="check" size={13} />Đang theo dõi</span></div></div><div className="donut-legend"><div><i className="teal-bg" /><span>Đúng giờ / sớm</span><strong>{number(total-delayed)}</strong></div><div><i className="orange-bg" /><span>Trễ ≥ 15 phút</span><strong>{number(delayed)}</strong></div></div></section></div>
          <div className="bottom-grid"><section className="panel ranking-panel"><div className="panel-heading"><div><h2>Điểm nóng chậm chuyến</h2><p>Xếp hạng theo tỷ lệ trễ giảm dần</p></div><div className="segmented"><button className={rankBy==="airports" ? "selected" : ""} onClick={() => setRankBy("airports")}>Sân bay</button><button className={rankBy==="carriers" ? "selected" : ""} onClick={() => setRankBy("carriers")}>Hãng bay</button></div></div><div className="ranking-list">{(rankBy==="airports" ? selection.map(a => ({...a,rate:a.rate*carrierRate})) : carriers.filter(c => carrier==="all" || c.code===carrier)).slice(0,5).map((a,i) => <div className="ranking-row" key={a.code}><span className="rank-number">{String(i+1).padStart(2,"0")}</span><span className="airport-code">{a.code}</span><div className="ranking-name"><strong>{a.name}</strong><span>{rankBy==="airports" ? "Sân bay quốc tế" : "Hãng hàng không"}</span></div><div className="ranking-track"><div style={{width:`${a.rate/40*100}%`}} /></div><strong className="rank-rate">{a.rate.toFixed(1)}<small>%</small></strong></div>)}</div><div className="panel-footnote">Phạm vi xếp hạng: {rankBy==="airports" ? "sân bay đã chọn" : "hãng bay đã chọn, toàn bộ sân bay"} · Dữ liệu demo</div></section><section className="tomorrow-card"><span className="tomorrow-tag"><Icon name="spark" size={15} />GÓC NHÌN NGÀY MAI</span><h2>Hành trình tốt hơn<br />bắt đầu từ dự báo.</h2><p>Khám phá mức delay dự kiến và nguy cơ chậm chuyến cho ngày 07/11/2026.</p><div className="flight-illustration" aria-hidden="true"><span className="flight-code">TODAY</span><span className="flight-dashes" /><span className="flight-plane"><Icon name="plane" size={27} /></span><span className="flight-dashes" /><span className="flight-code">TOMORROW</span></div><Link href="/forecast" className="forecast-link">Khám phá dự báo<Icon name="arrow" size={18} /></Link></section></div>
        </>}
        <footer className="page-footer"><span><strong>flightlens.</strong> Rõ dữ liệu. Chủ động hành trình.</span><span>Mẫu giao diện · US Flight Delay · 2026</span></footer>
      </main>
    </div>{toast && <div className="toast" role="status"><Icon name="check" size={18} />{toast}</div>}
  </div>;
}
