"""South Carolina place matching.

Two jobs:
  1. Filter. A national query for "commercial structure fire" returns mostly
     out-of-state noise. If we can't place a story in SC, we drop it.
  2. Tag. Knowing the city lets the board group by market and lets you sort by
     drive time from your nearest crew.

Ambiguous names are handled by requiring a state marker. Columbia, Florence,
Greenville, Manning, Union and Camden all exist in other states, so those need
"South Carolina" or "S.C." somewhere in the text before they count.
"""

from __future__ import annotations

import re

STATE_MARKERS = [
    "south carolina",
    "s.c.",
    " sc ",
    ", sc",
    "upstate",
    "lowcountry",
    "midlands",
    "pee dee",
    "grand strand",
]

# City -> county. Not exhaustive; add as you find gaps.
SC_CITIES: dict[str, str] = {
    "columbia": "Richland",
    "charleston": "Charleston",
    "north charleston": "Charleston",
    "mount pleasant": "Charleston",
    "summerville": "Dorchester",
    "goose creek": "Berkeley",
    "moncks corner": "Berkeley",
    "hanahan": "Berkeley",
    "greenville": "Greenville",
    "greer": "Greenville",
    "simpsonville": "Greenville",
    "mauldin": "Greenville",
    "travelers rest": "Greenville",
    "taylors": "Greenville",
    "spartanburg": "Spartanburg",
    "boiling springs": "Spartanburg",
    "duncan": "Spartanburg",
    "inman": "Spartanburg",
    "anderson": "Anderson",
    "clemson": "Pickens",
    "easley": "Pickens",
    "pickens": "Pickens",
    "seneca": "Oconee",
    "walhalla": "Oconee",
    "rock hill": "York",
    "fort mill": "York",
    "tega cay": "York",
    "york": "York",
    "clover": "York",
    "myrtle beach": "Horry",
    "north myrtle beach": "Horry",
    "conway": "Horry",
    "surfside beach": "Horry",
    "socastee": "Horry",
    "florence": "Florence",
    "lake city": "Florence",
    "sumter": "Sumter",
    "manning": "Clarendon",
    "orangeburg": "Orangeburg",
    "aiken": "Aiken",
    "north augusta": "Aiken",
    "beaufort": "Beaufort",
    "bluffton": "Beaufort",
    "hilton head": "Beaufort",
    "hilton head island": "Beaufort",
    "port royal": "Beaufort",
    "hardeeville": "Jasper",
    "walterboro": "Colleton",
    "georgetown": "Georgetown",
    "pawleys island": "Georgetown",
    "lexington": "Lexington",
    "cayce": "Lexington",
    "west columbia": "Lexington",
    "irmo": "Lexington",
    "chapin": "Lexington",
    "batesburg": "Lexington",
    "camden": "Kershaw",
    "lugoff": "Kershaw",
    "newberry": "Newberry",
    "laurens": "Laurens",
    "clinton": "Laurens",
    "greenwood": "Greenwood",
    "abbeville": "Abbeville",
    "union": "Union",
    "gaffney": "Cherokee",
    "chester": "Chester",
    "lancaster": "Lancaster",
    "indian land": "Lancaster",
    "darlington": "Darlington",
    "hartsville": "Darlington",
    "bennettsville": "Marlboro",
    "cheraw": "Chesterfield",
    "dillon": "Dillon",
    "marion": "Marion",
    "mullins": "Marion",
    "kingstree": "Williamsburg",
    "moncks": "Berkeley",
    "st. george": "Dorchester",
    "ridgeland": "Jasper",
    "barnwell": "Barnwell",
    "bamberg": "Bamberg",
    "allendale": "Allendale",
    "edgefield": "Edgefield",
    "saluda": "Saluda",
    "winnsboro": "Fairfield",
    "bishopville": "Lee",
    "johnsonville": "Florence",
    "murrells inlet": "Georgetown",
    "little river": "Horry",
    "james island": "Charleston",
    "west ashley": "Charleston",
    "daniel island": "Charleston",
    "isle of palms": "Charleston",
    "folly beach": "Charleston",
}

# Cities that also exist in other states. Need a state marker to count.
AMBIGUOUS = {
    "columbia", "florence", "greenville", "manning", "union", "camden",
    "lexington", "marion", "georgetown", "chester", "lancaster", "york",
    "newberry", "clinton", "aiken", "anderson", "beaufort", "dillon",
    "charleston", "greenwood", "laurens", "saluda", "abbeville",
}

SC_COUNTIES = sorted({c.lower() for c in SC_CITIES.values()})


def _has_state_marker(text: str) -> bool:
    return any(m in text for m in STATE_MARKERS)


def locate(text: str) -> tuple[str, str, bool]:
    """Return (place, county, is_south_carolina).

    Longest city name wins, so "north charleston" isn't swallowed by
    "charleston" and "north myrtle beach" isn't swallowed by "myrtle beach".
    """
    lowered = text.lower()
    marker = _has_state_marker(lowered)

    best_city = ""
    for city in sorted(SC_CITIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(city)}\b", lowered):
            if city in AMBIGUOUS and not marker:
                continue
            best_city = city
            break

    if best_city:
        return best_city.title(), SC_CITIES[best_city], True

    # No city, but a county named alongside a state marker still places it.
    if marker:
        for county in SC_COUNTIES:
            if re.search(rf"\b{re.escape(county)}\s+county\b", lowered):
                return "", county.title(), True
        return "", "", True

    return "", "", False


def is_south_carolina(text: str) -> bool:
    return locate(text)[2]
