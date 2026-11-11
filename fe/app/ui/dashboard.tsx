"use client";

import { ViewMode } from "./flight-types";
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

export default function Dashboard({ view }: { view: ViewMode }) {
  const obs = useFlightObservatory(view);

  return (
    <div className="app-shell">
      <TopHeader
        pageTitle={obs.pageTitle}
        pageSubtitle={obs.pageSubtitle}
        apiMode={obs.apiMode}
        busy={obs.busy}
        onTriggerIngestion={obs.triggerIngestionRun}
        onTriggerClustering={obs.triggerClusteringRun}
        onExportCsv={obs.exportCsv}
      />

      <main className="main-workspace">
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
          centroids={obs.centroids}
          busy={obs.busy}
          onRefresh={obs.refresh}
          onResetFilters={obs.resetFilters}
        />

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
            airportClusterMap={obs.airportClusterMap}
            selectedClusterId={obs.selectedClusterId}
            setSelectedClusterId={obs.setSelectedClusterId}
            centroids={obs.centroids}
            clusterAssignments={obs.clusterAssignments}
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
          <ClusteringView
            clusteringMeta={obs.clusteringMeta}
            clusterEntityType={obs.clusterEntityType}
            setClusterEntityType={obs.setClusterEntityType}
            fetchClusteringResults={obs.fetchClusteringResults}
            clusterAssignments={obs.clusterAssignments}
            selectedClusterId={obs.selectedClusterId}
            setSelectedClusterId={obs.setSelectedClusterId}
            centroids={obs.centroids}
          />
        )}

        {obs.isForecast && (
          <ForecastView
            scoped={obs.scoped}
            filteredPredictions={obs.filteredPredictions}
            forecastAvg={obs.forecastAvg}
            highCount={obs.highCount}
            meanProbability={obs.meanProbability}
            selection={obs.selection}
            risk={obs.risk}
            setRisk={obs.setRisk}
          />
        )}

        {obs.isAnalytics && (
          <AnalyticsView
            flights={obs.mapFlights && obs.mapFlights.length > 0 ? obs.mapFlights : obs.paginatedFlights}
            total={obs.total}
            rate={obs.rate}
            avgDelay={obs.avg}
            avgDistance={obs.flightsAvgDistance || 1252}
          />
        )}

        {obs.isOverview && (
          <OverviewView
            total={obs.total}
            rate={obs.rate}
            delayed={obs.delayed}
            avg={obs.avg}
            day={obs.day}
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
