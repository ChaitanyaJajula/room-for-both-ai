from fastapi import APIRouter

from app.models.conflict import ConflictRequest, ConflictResponse
from app.services.conflict_detection import detect_conflicts

router = APIRouter(prefix="/api/v1/conflicts", tags=["conflicts"])


@router.post("/detect", response_model=ConflictResponse)
def detect(request: ConflictRequest) -> ConflictResponse:
    return detect_conflicts(
        request.profile,
        request.commitments,
        request.approved_plan,
        request.unexpected_commitment,
    )
