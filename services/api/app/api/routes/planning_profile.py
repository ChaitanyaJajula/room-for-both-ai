from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.planning_profile import PlanningProfile

router = APIRouter(prefix="/api/v1/planning-profile", tags=["planning-profile"])


class PlanningProfileValidationResponse(BaseModel):
    status: Literal["valid"]
    profile: PlanningProfile


@router.post("/validate", response_model=PlanningProfileValidationResponse)
def validate_planning_profile(profile: PlanningProfile) -> PlanningProfileValidationResponse:
    return PlanningProfileValidationResponse(status="valid", profile=profile)
