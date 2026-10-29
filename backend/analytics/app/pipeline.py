from app.schemas import PipelineOutput


class Pipeline:
    async def run(self) -> PipelineOutput:
        """Read flight observations, calculate time-series statistics, trends, seasonality and correlations, then return a PipelineOutput."""
        # Replace this method when the source/storage/model contracts are ready.
        # Offload CPU-bound model work from the event loop when implementing it.
        raise NotImplementedError("analytics pipeline is not implemented yet.")
