from fastapi import APIRouter

from app.models.analysis import WeeklyAnalysisRequest, WeeklyAnalysisResponse
from app.services.capacity_engine import calculate_capacity
from app.services.weekly_analysis import analyze_week

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post("/weekly", response_model=WeeklyAnalysisResponse)
def weekly_analysis(request: WeeklyAnalysisRequest) -> WeeklyAnalysisResponse:
    capacity = calculate_capacity(request.profile, request.commitments)
    analysis = analyze_week(request.profile, request.commitments, capacity)
    return WeeklyAnalysisResponse(capacity=capacity, analysis=analysis)
