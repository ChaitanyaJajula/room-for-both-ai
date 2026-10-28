import logging

from fastapi import APIRouter, HTTPException

from app.models.schedule import ScheduleRequest, ScheduleResponse
from app.services.scheduler import SchedulingError, generate_schedule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plan", tags=["plan"])


@router.post("/generate", response_model=ScheduleResponse)
def generate(request: ScheduleRequest) -> ScheduleResponse:
    try:
        return generate_schedule(
            request.profile,
            request.commitments,
            request.work_outcome,
            request.personal_outcome,
        )
    except SchedulingError:
        # Details stay in the server log; the caller never sees solver internals.
        logger.exception("Schedule generation failed")
        raise HTTPException(
            status_code=500, detail="The schedule could not be generated safely."
        ) from None
