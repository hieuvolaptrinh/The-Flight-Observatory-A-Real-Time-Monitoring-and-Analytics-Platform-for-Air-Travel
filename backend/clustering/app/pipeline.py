from app.schemas import PipelineOutput


class Pipeline:
    async def run(self) -> PipelineOutput:
        """Read aggregated airport or route features, load or fit the clustering model as appropriate, then return cluster labels and summaries."""
        # Replace this method when the source/storage/model contracts are ready.
        # Offload CPU-bound model work from the event loop when implementing it.
        raise NotImplementedError("clustering pipeline is not implemented yet.")
