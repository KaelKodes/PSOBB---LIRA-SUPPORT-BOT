"""The partner's name, and the section ID Blue Burst assigns to it.

Each character contributes the ones digit of its Unicode value. Blue Burst
then adds a class offset. The ones digit of that total is the section ID.
"""

from __future__ import annotations

from force_brain import ForceClass

SECTIONS = (
    "Viridia",
    "Greenill",
    "Skyly",
    "Bluefull",
    "Purplenum",
    "Pinkal",
    "Redria",
    "Oran",
    "Yellowboze",
    "Whitill",
)

# Blue Burst only. FOnewearl is 3, HUcast is 7.
CLASS_OFFSET = {
    ForceClass.FOMAR: 5,
    ForceClass.FOMARL: 1,
    ForceClass.FONEWEARL: 3,
}

CHARACTER_NAME = "Lira"
CHARACTER_CLASS = ForceClass.FONEWEARL


def section_id(name: str, force: ForceClass = CHARACTER_CLASS) -> str:
    total = sum(ord(ch) % 10 for ch in name) + CLASS_OFFSET[force]
    return SECTIONS[total % 10]
