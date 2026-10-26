from fastapi import APIRouter

from app.models.calendar import DemoCalendarResponse
from app.services.demo_calendar import get_demo_calendar

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


@router.get("/demo", response_model=DemoCalendarResponse)
def demo_calendar() -> DemoCalendarResponse:
    return get_demo_calendar()
