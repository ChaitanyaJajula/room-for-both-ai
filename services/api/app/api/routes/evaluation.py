import logging

from fastapi import APIRouter, HTTPException

from app.models.evaluation import EvaluationReport
from app.services.evaluation import run_evaluation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


@router.post("/run", response_model=EvaluationReport)
def run() -> EvaluationReport:
    """Runs the fixed deterministic suite. It takes no input and makes no model call."""
    try:
        return run_evaluation()
    except Exception:
        # A failing case is reported inside the report; this means no report could be built.
        logger.exception("Evaluation report could not be built")
        raise HTTPException(
            status_code=500, detail="The evaluation report could not be produced."
        ) from None
