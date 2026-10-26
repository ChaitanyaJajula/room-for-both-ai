from fastapi import APIRouter

from app.models.capacity import CapacityRequest, CapacityResponse
from app.services.capacity_engine import calculate_capacity

router = APIRouter(prefix="/api/v1/capacity", tags=["capacity"])


@router.post("/calculate", response_model=CapacityResponse)
def calculate(request: CapacityRequest) -> CapacityResponse:
    return calculate_capacity(request.profile, request.commitments)
