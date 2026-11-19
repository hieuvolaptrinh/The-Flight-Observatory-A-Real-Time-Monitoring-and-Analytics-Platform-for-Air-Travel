"use client";

import { flightDateRange, ViewMode } from "./flight-types";
import { useFlightObservatory } from "./hooks/use-flight-observatory";
import { Icon } from "./components/icons";
import { TopHeader } from "./components/top-header";
import { FilterBar } from "./components/filter-bar";
import { BottomNavDock } from "./components/bottom-nav-dock";
import { FlightsView } from "./views/flights-view";
import { ClusteringView } from "./views/clustering-view";
import { ForecastView } from "./views/forecast-view";
import { OverviewView } from "./views/overview-view";
import { AnalyticsView } from "./views/analytics-view";
import { CustomSelect } from "./components/custom-select";

export default function Dashboard({ view }: { view: ViewMode }) {
  const obs = useFlightObservatory(view);
  const provider = obs.serverMeta?.provider_status;
  const warnings = [...new Set(provider?.warnings ?? [])];
  const pageCap = warnings.some(message => message.includes("page cap reached"));
  const checkedAt = provider?.checked_at
    ? new Date(provider.checked_at).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })
    : null;
  const visibleErrors = Object.entries(obs.apiErrors).filter(([service, error]) => error && (
    service === "ingestion" && !obs.isAnalytics || service === "clustering" && (obs.isFlights || obs.isClustering)
    || service === "prediction" && obs.isForecast || service === "raw" && obs.isFlights && obs.dataLayer === "raw"
  ));
  const predictionReason = obs.predictionMeta?.reason;


  return (
    <div className="app-shell">
      <TopHeader
        pageTitle={obs.pageTitle}
        pageSubtitle={obs.pageSubtitle}
        apiMode={obs.isAnalytics ? "gateway" : obs.apiMode}
        busy={obs.busy}
        onTriggerClustering={obs.isForecast ? obs.triggerPredictionRun : obs.triggerClusteringRun}
        runLabel={obs.isForecast ? "Chạy dự báo" : "Chạy K-Means"}
        showRun={obs.isForecast || obs.isFlights || obs.isClustering}
        onExportCsv={obs.exportCsv}
      />

      <main className="main-workspace">
        {visibleErrors.map(([service, error]) => <p className="api-error" role="alert" key={service}>{error}</p>)}
        <div className="dashboard-context">
          <div className="dashboard-source-bar">
            {(obs.isOverview || obs.isFlights) && (
              <CustomSelect ariaLabel="Nguồn chuyến bay" value={obs.flightSource} size="compact"
                onChange={value => {
                  obs.resetFilters();
                  obs.setFlightSource(value as typeof obs.flightSource);
                }}
                options={[
                  { value: "airlabs", label: "AirLabs" },
                  { value: "legacy", label: "Lịch sử đã lưu" },
                  { value: "all", label: "Tất cả nguồn" },
                ]} />
            )}
            <details className="dashboard-source-details">
              <summary>
                <strong>Thông tin dữ liệu</strong>
                {checkedAt && <span>API kiểm tra lúc {checkedAt}</span>}
                {pageCap && <span className="dashboard-source-warning">Giới hạn phân trang</span>}
              </summary>
              <div className="dashboard-source-content">
                <div><strong>Nguồn tự động</strong> · Lịch bay AirLabs, thời tiết OpenWeather</div>
                {!obs.isAnalytics && obs.serverMeta?.first_flight_date && obs.serverMeta.last_flight_date && (
                  <div><strong>Khoảng chuyến khớp bộ lọc</strong> · {flightDateRange(obs.serverMeta.first_flight_date, obs.serverMeta.last_flight_date)}</div>
                )}
                {!obs.isAnalytics && obs.updated && (
                  <div><strong>Bản ghi mới nhất trong kết quả</strong> · {new Date(obs.updated).toLocaleString("vi-VN")}</div>
                )}
                {warnings.map(message => (
                  <div key={message}>{message.includes("page cap reached")
                    ? `${message.split(":")[0]} đã chạm giới hạn số trang. Số chuyến chỉ phản ánh phần lịch bay đã thu thập.`
                    : message}</div>
                ))}
              </div>
            </details>
          </div>
          {obs.isForecast && !obs.filteredPredictions.length && (
            <p className="analytics-status">{predictionReason === "model_missing"
              ? "Prediction API đã kết nối nhưng chưa có model đã huấn luyện để dự báo."
              : "Chưa có dự báo cho bộ lọc này. Cần chuyến bay và thời tiết phù hợp."}</p>
          )}
          {!obs.isAnalytics && !obs.isClustering && (
            <FilterBar
              airport={obs.airport}
              setAirport={obs.setAirport}
              destAirport={obs.destAirport}
              setDestAirport={obs.setDestAirport}
              carrier={obs.carrier}
              setCarrier={obs.setCarrier}
              flightStatus={obs.flightStatus}
              setFlightStatus={obs.setFlightStatus}
              selectedClusterId={obs.selectedClusterId}
              setSelectedClusterId={obs.setSelectedClusterId}
              search={obs.search}
              setSearch={obs.setSearch}
              uniqueOrigins={obs.uniqueOrigins}
              uniqueDests={obs.uniqueDests}
              uniqueCarriers={obs.uniqueCarriers}
              centroids={obs.isFlights ? obs.radarCentroids : []}
              busy={obs.busy}
              onRefresh={obs.refresh}
              onResetFilters={obs.resetFilters}
            />
          )}
        </div>

        {obs.isFlights && (
          <FlightsView
            apiMode={obs.apiMode}
            apiReady={obs.apiReady}
            totalFilteredCount={obs.totalFilteredCount}
            batchMeta={obs.batchMeta}
            flightsOnTimeCount={obs.flightsOnTimeCount}
            flightsDelayedCount={obs.flightsDelayedCount}
            flightsDelayRate={obs.flightsDelayRate}
            flightsAvgDelay={obs.flightsAvgDelay}
            flightsAvgDistance={obs.flightsAvgDistance}
            statusCounts={obs.statusCounts}
            clusteringMeta={obs.clusteringMeta}
            mapFlights={obs.mapFlights}
            selectedFlightKey={obs.selectedFlightKey}
            setSelectedFlightKey={obs.setSelectedFlightKey}
            airport={obs.airport}
            setAirport={obs.setAirport}
            autoPollEnabled={obs.autoPollEnabled}
            setAutoPollEnabled={obs.setAutoPollEnabled}
            routeClusterMap={obs.routeClusterMap}
            selectedClusterId={obs.selectedClusterId}
            setSelectedClusterId={obs.setSelectedClusterId}
            centroids={obs.radarCentroids}
            clusterAssignments={obs.radarRoutes}
            flightStatus={obs.flightStatus}
            setFlightStatus={obs.setFlightStatus}
            carrier={obs.carrier}
            setCarrier={obs.setCarrier}
            carrierDelayBars={obs.carrierDelayBars}
            sort={obs.sort}
            setSort={obs.setSort}
            pageSize={obs.pageSize}
            setPageSize={obs.setPageSize}
            paginatedFlights={obs.paginatedFlights}
            startIndex={obs.startIndex}
            safePage={obs.safePage}
            totalPages={obs.totalPages}
            pageNumbers={obs.pageNumbers}
            setCurrentPage={obs.setCurrentPage}
            dataLayer={obs.dataLayer}
            setDataLayer={obs.setDataLayer}
            rawFlights={obs.rawFlights}
            rawLoading={obs.rawLoading}
            rawCursor={obs.rawCursor}
            setRawCursor={obs.setRawCursor}
            rawTotal={obs.rawTotal}
            rawPageSize={obs.rawPageSize}
            notify={obs.notify}
          />
        )}

        {obs.isClustering && (
          <>
          {!obs.clusteringReady && !obs.apiErrors.clustering && <p className="analytics-status">
            Chưa có kết quả phân cụm sẵn sàng. Chạy K-Means sau khi có đủ dữ liệu sân bay hoặc tuyến bay.
          </p>}
          <ClusteringView
            clusteringMeta={obs.clusteringMeta}
            clusterEntityType={obs.clusterEntityType}
            setClusterEntityType={obs.setClusterEntityType}
            clusterAssignments={obs.clusterAssignments}
            selectedClusterId={obs.selectedClusterId}
            setSelectedClusterId={obs.setSelectedClusterId}
            centroids={obs.centroids}
          />
          </>
        )}

        {obs.isForecast && (
          <ForecastView
            scoped={obs.scoped}
            filteredPredictions={obs.filteredPredictions}
            forecastAvg={obs.forecastAvg}
            highCount={obs.highCount}
            meanProbability={obs.meanProbability}
            risk={obs.risk}
            setRisk={obs.setRisk}
          />
        )}

        {obs.isAnalytics && <AnalyticsView />}

        {obs.isOverview && !obs.serverMeta && <p className="analytics-empty" role="status">
          {obs.apiErrors.ingestion ? "Chưa đọc được số liệu tổng quan." : "Đang tải số liệu tổng quan…"}
        </p>}
        {obs.isOverview && obs.serverMeta && (
          <OverviewView
            total={obs.total}
            rate={obs.rate}
            delayed={obs.delayed}
            avg={obs.avg}
            day={obs.serverMeta?.last_flight_date ?? null}
            hourly={obs.serverMeta?.hourly ?? []}
            onTime={obs.statusCounts.on_time}
            unknown={obs.statusCounts.unknown}
            selection={obs.selection}
            carriers={obs.carriers}
            rankBy={obs.rankBy}
            setRankBy={obs.setRankBy}
          />
        )}
      </main>

      <BottomNavDock view={view} />

      {obs.toast && (
        <div className="toast" role="status">
          <Icon name="check" size={17} />
          {obs.toast}
        </div>
      )}
    </div>
  );
}
