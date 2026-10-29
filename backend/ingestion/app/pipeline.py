from app.schemas import PipelineOutput


class Pipeline:
    async def run(self) -> PipelineOutput:
        """Call the separately deployed data-simulator using the agreed API contract, validate and normalize the batch, deduplicate flights, then return ingested records. Advance the replay cursor only after the batch has been accepted."""
        # Replace this method when the source/storage/model contracts are ready.
        # Offload CPU-bound model work from the event loop when implementing it.
        raise NotImplementedError("ingestion pipeline is not implemented yet.")
