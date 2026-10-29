from fastapi import APIRouter

from app.models.repair import RepairRequest, RepairResponse
from app.services.repair import build_repair_options

router = APIRouter(prefix="/api/v1/repair", tags=["repair"])


@router.post("/options", response_model=RepairResponse)
def repair_options(request: RepairRequest) -> RepairResponse:
    return build_repair_options(request)
