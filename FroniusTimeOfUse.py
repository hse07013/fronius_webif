
import json
import datetime as dt
from attr import dataclass
from enum import StrEnum, IntFlag, auto
from typing import Optional
from copy import copy


class StrUpperEnum(StrEnum):
    def __str__(self):
        return self.value.upper()


class FroniusScheduleTypeEnum(StrUpperEnum):
    CHARGE_MAX = auto()
    CHARGE_MIN = auto()
    DISCHARGE_MAX = auto()
    DISCHARGE_MIN = auto()
    UNKNOWN = auto()


class WorkdayEnum(IntFlag):
        NONE = 0
        MONDAY = auto()
        TUESDAY = auto()
        WEDNESDAY = auto()
        THURSDAY = auto()
        FRIDAY = auto()
        SATURDAY = auto()
        SUNDAY = auto()


@dataclass(frozen=False)
class TimeOfUse:
    Active: bool = False
    Power: int = 0
    ScheduleType: FroniusScheduleTypeEnum = FroniusScheduleTypeEnum.UNKNOWN
    Start: dt.time = dt.time(0, 0)  # Default to 00:00
    End: dt.time = dt.time(0, 0)    # Default to 00:00
    Workdays: WorkdayEnum = WorkdayEnum.NONE  # No days active by default      


    @staticmethod
    def parse(config: dict) -> 'TimeOfUse':
        """Parses a single time of use entry from the Fronius configuration format."""
        try:
            schedule_type = FroniusScheduleTypeEnum[config["ScheduleType"].upper()]
            start_time = dt.datetime.strptime(config["TimeTable"]["Start"], "%H:%M").time()
            end_time = dt.datetime.strptime(config["TimeTable"]["End"], "%H:%M").time()
            weekdays = config["Weekdays"]
            workdays = WorkdayEnum.NONE
            workdays |= WorkdayEnum.MONDAY if weekdays.get("Mon", False) else WorkdayEnum.NONE
            workdays |= WorkdayEnum.TUESDAY if weekdays.get("Tue", False) else WorkdayEnum.NONE
            workdays |= WorkdayEnum.WEDNESDAY if weekdays.get("Wed", False) else WorkdayEnum.NONE
            workdays |= WorkdayEnum.THURSDAY if weekdays.get("Thu", False) else WorkdayEnum.NONE
            workdays |= WorkdayEnum.FRIDAY if weekdays.get("Fri", False) else WorkdayEnum.NONE
            workdays |= WorkdayEnum.SATURDAY if weekdays.get("Sat", False) else WorkdayEnum.NONE
            workdays |= WorkdayEnum.SUNDAY if weekdays.get("Sun", False) else WorkdayEnum.NONE

            return TimeOfUse(
                Active = config["Active"],
                Power = config["Power"],
                ScheduleType = schedule_type,
                Start = start_time,
                End = end_time,
                Workdays = workdays
            )
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid time of use configuration: {e}")


    def overlaps(self, otherTimeOfUse: 'TimeOfUse') -> bool:
        """Determines if this time of use entry overlaps with another entry of the same schedule type."""
        if self.ScheduleType != otherTimeOfUse.ScheduleType:
            return False  # Different schedule types do not overlap
        if self.Workdays & otherTimeOfUse.Workdays == WorkdayEnum.NONE:
            return False  # No overlapping active days
        if self.Start >= self.End or otherTimeOfUse.Start >= otherTimeOfUse.End:
            return False  # Invalid time ranges do not overlap
        return (self.Start < otherTimeOfUse.End) and (otherTimeOfUse.Start < self.End)  # Check time overlap


    def validate(self) -> bool:
        """Validates a time of use entry to ensure it meets expected criteria."""
        if self.ScheduleType == FroniusScheduleTypeEnum.UNKNOWN:
            return False  # Schedule type must be known
        if not isinstance(self.Power, int) or self.Power < 0:
            return False  # Power must be a non-negative integer
        if self.Start >= self.End:
            return False  # Start time must be before end time
        if self.Workdays == WorkdayEnum.NONE:
            return False  # At least one weekday must be active
        return True
    
    
    def getJson(self) -> dict:
        """Returns a JSON-serializable dictionary representation of this time of use entry."""
        return {
            "Active": self.Active,
            "Power": self.Power,
            "ScheduleType": self.ScheduleType.value.upper(),
            "TimeTable": {
                "Start": self.Start.strftime("%H:%M"),
                "End": self.End.strftime("%H:%M")
            },
            "Weekdays": {
                "Mon": bool(self.Workdays & WorkdayEnum.MONDAY),
                "Tue": bool(self.Workdays & WorkdayEnum.TUESDAY),
                "Wed": bool(self.Workdays & WorkdayEnum.WEDNESDAY),
                "Thu": bool(self.Workdays & WorkdayEnum.THURSDAY),
                "Fri": bool(self.Workdays & WorkdayEnum.FRIDAY),
                "Sat": bool(self.Workdays & WorkdayEnum.SATURDAY),
                "Sun": bool(self.Workdays & WorkdayEnum.SUNDAY)
            }
        }



class FroniusTimeOfUseContainer:
    """This class manages the time of use configuration for a Fronius inverter.
      It provides methods to read the current configuration and update it as needed."""

    _timeofuse : list[TimeOfUse] = []


    def __init__(self, parseFronius: Optional[dict] = None):
        """Initializes the manager with an optional parsed Fronius configuration."""
        _timeofuse = []
        if parseFronius is not None:
            self.parseConfig(parseFronius)    


    def parseConfig(self, config: dict):
        """Parses the entire time of use configuration from the Fronius format."""

        if "ScheduleType" in config:
            try:
                tou_entry = TimeOfUse.parse(config)
                self.addEntry(tou_entry)
            except ValueError as e:
                print(f"Skipping invalid time of use entry: {e}")

        if "timeofuse" in config:
            for c in config["timeofuse"]:
                try:
                    tou_entry = TimeOfUse.parse(c)
                    self.addEntry(tou_entry)
                except ValueError as e:
                    print(f"Skipping invalid time of use entry: {e}")
    

    def overlapsWithExistingEntry(self, entry: TimeOfUse) -> bool:
        """Checks if the given time of use entry overlaps with any existing entries of the same schedule type."""
        for existing in self._timeofuse:
            if existing.overlaps(entry):
                return True
        return False
       

    def removeEntry(self, schedule_type: FroniusScheduleTypeEnum, workdays: WorkdayEnum,
                              startTime: dt.time, endTime: dt.time) -> tuple[int, list[TimeOfUse]]:
        collectedRemove : list[TimeOfUse] = []
        for existing in self._timeofuse:
            dummyTimeOfUse = TimeOfUse(ScheduleType=schedule_type, Workdays=workdays, Start=startTime, End=endTime)
            if not dummyTimeOfUse.validate():
                raise ValueError("Invalid criteria for removing time of use entry.")
            if self.overlapsWithExistingEntry(dummyTimeOfUse):
                collectedRemove.append(existing)
                self._timeofuse.remove(existing)
        return (len(collectedRemove), collectedRemove)


    def addEntry(self, entry: TimeOfUse) -> None:
        """Adds a new time of use entry to the configuration."""
        if not entry.validate():
            raise ValueError("Invalid time of use entry.")
        if self.overlapsWithExistingEntry(entry):
            raise ValueError("New entry overlaps with existing entries of the same schedule type.")
        self._timeofuse.append(entry)


    def addOrReplaceEntry(self, entry: TimeOfUse) -> tuple[int, list[TimeOfUse]]:
        """Adds a new time of use entry, replacing any existing entries that overlap with it.
           Returns the number of entries that were removed to accommodate the new entry."""
        # Remove overlapping entries
        rm_ret = self.removeEntry(schedule_type=entry.ScheduleType, workdays=entry.Workdays, startTime=entry.Start, endTime=entry.End)
        
        # Add the new entry
        self._timeofuse.append(entry)

        return rm_ret  # Return the number of entries that were removed


    def getCopy(self, timeOfUseOverlap: Optional[TimeOfUse] = None, includeOverlap: bool = True) -> list[TimeOfUse]:
        """Returns a list of the current time of use entries."""
        if timeOfUseOverlap is not None:
            return [copy(entry) for entry in self._timeofuse if entry.overlaps(timeOfUseOverlap) == includeOverlap]
        return self._timeofuse.copy()


    def getJson(self) -> dict:
        """
        Returns a JSON-serializable dictionary representation of the entire time of use configuration.
        """
        return {
            "timeofuse": [
                entry.getJson() for entry in self._timeofuse
            ]
        }


    def __str__(self):
        return json.dumps(self.getJson(), indent=2)
    