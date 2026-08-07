from urllib.parse import urlencode


GOOGLE_MAPS_TRANSIT_DISCLAIMER = (
    "Open Google Maps for current public-transport directions. Routes, "
    "departure times, disruptions, and availability may change; verify "
    "the latest information before travelling."
)


def get_google_maps_transit_url(latitude: float, longitude: float) -> str:
    """Build a key-free Google Maps transit directions URL."""

    parameters = urlencode(
        {
            "api": "1",
            "destination": f"{latitude},{longitude}",
            "travelmode": "transit",
            "dir_action": "navigate",
        }
    )
    return f"https://www.google.com/maps/dir/?{parameters}"
