from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import SCHEDULE_MODI, TIMEBLOCK_TYPEN, VALID_TAGS

WOCHENTAGE = ["mo", "di", "mi", "do", "fr", "sa", "so"]


def _tags_pruefen(tags: list[str]) -> list[str]:
    unbekannt = set(tags) - VALID_TAGS
    if unbekannt:
        gueltig = ", ".join(sorted(VALID_TAGS))
        raise ValueError(f"Unbekannte Tags: {sorted(unbekannt)}. Gültig sind: {gueltig}")
    return sorted(set(tags))


# --- Tasks ---


class TaskCreate(BaseModel):
    titel: str = Field(min_length=1, max_length=300)
    beschreibung: str = ""
    tags: list[str] = []

    _tags = field_validator("tags")(_tags_pruefen)


class TaskUpdate(BaseModel):
    titel: str | None = Field(default=None, min_length=1, max_length=300)
    beschreibung: str | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titel: str
    beschreibung: str
    position: int
    tags: list[str]
    erstellt_am: datetime
    geaendert_am: datetime


class TagEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag: str
    aktion: str
    zeitpunkt: datetime


class QueueOrder(BaseModel):
    """Komplette Ziel-Reihenfolge, wie sie nach dem Drag & Drop aussieht."""

    task_ids: list[int] = Field(min_length=1)


# --- Termine & Blocker ---


class TimeBlockCreate(BaseModel):
    titel: str = Field(min_length=1, max_length=300)
    typ: str
    start: datetime
    ende: datetime

    @field_validator("typ")
    @classmethod
    def typ_pruefen(cls, v: str) -> str:
        if v not in TIMEBLOCK_TYPEN:
            raise ValueError(f"typ muss eins sein von: {sorted(TIMEBLOCK_TYPEN)}")
        return v

    @model_validator(mode="after")
    def zeitraum_pruefen(self) -> "TimeBlockCreate":
        if self.ende <= self.start:
            raise ValueError("ende muss nach start liegen")
        return self


class TimeBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titel: str
    typ: str
    start: datetime
    ende: datetime


# --- Arbeitszeit ---


class ScheduleUpdate(BaseModel):
    modus: str
    stunden_pro_tag: float = Field(default=8.0, gt=0, le=24)
    zeiten: dict[str, list[str] | None] | None = None

    @field_validator("modus")
    @classmethod
    def modus_pruefen(cls, v: str) -> str:
        if v not in SCHEDULE_MODI:
            raise ValueError(f"modus muss eins sein von: {sorted(SCHEDULE_MODI)}")
        return v

    @model_validator(mode="after")
    def zeiten_pruefen(self) -> "ScheduleUpdate":
        if self.modus == "feste_zeiten":
            if not self.zeiten:
                raise ValueError("modus feste_zeiten braucht zeiten")
            unbekannt = set(self.zeiten) - set(WOCHENTAGE)
            if unbekannt:
                raise ValueError(f"Unbekannte Wochentage: {sorted(unbekannt)}")
            for tag, fenster in self.zeiten.items():
                if fenster is None:
                    continue
                if len(fenster) != 2:
                    raise ValueError(f"{tag}: zeiten brauchen genau [start, ende]")
                start, ende = (_minuten(fenster[0]), _minuten(fenster[1]))
                if ende <= start:
                    raise ValueError(f"{tag}: ende muss nach start liegen")
        return self


def _minuten(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        wert = int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        raise ValueError(f"Ungültige Uhrzeit: {hhmm!r}, erwartet HH:MM") from None
    if not 0 <= wert < 24 * 60:
        raise ValueError(f"Uhrzeit außerhalb des Tages: {hhmm!r}")
    return wert


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    modus: str
    stunden_pro_tag: float
    zeiten: dict[str, list[str] | None] | None


# --- GitLab ---


class ConnectionUpdate(BaseModel):
    url: str = Field(min_length=8, max_length=300)  # https://…
    token: str = Field(default="", max_length=300)  # leer = bestehenden behalten
    projekt_ids: list[int] = []


class ConnectionOut(BaseModel):
    """Der Token geht nie wieder raus."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    projekt_ids: list[int]


class SyncResult(BaseModel):
    importiert: int
    aktualisiert_lokal: int
    gepusht: int
    geschlossen: int
    konflikte: list[str]


class CapacityOut(BaseModel):
    datum: str
    modus: str
    arbeitszeit_minuten: int
    geblockt_minuten: int
    frei_minuten: int
    bloecke: list[TimeBlockOut]
