from jarvis.capabilities.hotel.metadata import HOTEL_CAPABILITY_METADATA
from jarvis.capabilities.hotel.tools import (
    HotelComplaintManualTool,
    HotelComplaintReportTool,
    HotelSchedulePlannerTool,
)


class HotelCapability:
    """Capability skeleton for hotel workflows."""

    metadata = HOTEL_CAPABILITY_METADATA

    def get_tools(self):
        """Return tools owned by this capability."""
        return [
            HotelSchedulePlannerTool(),
            HotelComplaintReportTool(),
            HotelComplaintManualTool(),
        ]


def create_capability():
    """Create the Hotel capability."""
    return HotelCapability()
