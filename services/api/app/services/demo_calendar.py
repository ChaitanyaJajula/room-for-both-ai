from datetime import time

from app.models.calendar import CalendarCommitment, CommitmentCategory, DemoCalendarResponse
from app.models.planning_profile import DayOfWeek

W, P = CommitmentCategory.work, CommitmentCategory.personal


def _c(id, title, day, start, end, category, description=None) -> CalendarCommitment:
    return CalendarCommitment(
        id=id,
        title=title,
        day=day,
        start_time=time(*start),
        end_time=time(*end),
        category=category,
        is_fixed=True,
        description=description,
    )


def get_demo_calendar() -> DemoCalendarResponse:
    """A small, fictional fixed weekly calendar for demonstrations."""
    mon, tue, wed, thu, fri, sat = (
        DayOfWeek.monday,
        DayOfWeek.tuesday,
        DayOfWeek.wednesday,
        DayOfWeek.thursday,
        DayOfWeek.friday,
        DayOfWeek.saturday,
    )
    return DemoCalendarResponse(
        name="Demo week",
        description="A fictional fixed weekly calendar for demonstrating capacity planning.",
        commitments=[
            _c("mon-standup", "Team standup", mon, (9, 30), (10, 0), W),
            _c("mon-review", "Project review", mon, (14, 0), (15, 30), W, "Monthly milestone review"),
            _c("mon-dinner", "Family dinner", mon, (18, 0), (19, 30), P),
            _c("tue-team", "Team meeting", tue, (10, 0), (11, 30), W),
            _c("tue-dentist", "Dentist appointment", tue, (13, 0), (14, 0), P),
            _c("wed-lunch", "Lunch with mentor", wed, (12, 0), (13, 0), P),
            _c("wed-planning", "Sprint planning", wed, (13, 30), (15, 0), W),
            _c("thu-review", "Design review", thu, (11, 0), (12, 30), W),
            _c("thu-client", "Client call", thu, (11, 30), (12, 0), W, "Overlaps the design review"),
            _c("thu-gym", "Gym class", thu, (7, 0), (8, 0), P),
            _c("fri-sync", "Release sync", fri, (16, 30), (17, 30), W, "Runs past the end of the workday"),
            _c("sat-market", "Farmers market", sat, (10, 0), (11, 0), P),
        ],
    )
