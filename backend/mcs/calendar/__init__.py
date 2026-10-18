from typing import Protocol, Sequence

from mcs.calendar.planner import SyncAction, SyncOutcome


class CalendarSink(Protocol):
    name: str

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]: ...
