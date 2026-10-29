from app.schemas import PipelineOutput


class Pipeline:
    async def run(self) -> PipelineOutput:
        """Load pre-trained regression and classification models with their preprocessing artifacts, read features available at prediction time, then return predictions. Do not train models on every scheduled run."""
        # Replace this method when the source/storage/model contracts are ready.
        # Offload CPU-bound model work from the event loop when implementing it.
        raise NotImplementedError("prediction pipeline is not implemented yet.")
