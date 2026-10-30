"""Chart registry. One cache file per patient. Facts are never merged."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PATIENT_ID = "0000-0001"

# Insertion order is the picker order. A new patient is a new row and a new
# cache file. Adding one does not rebuild any other cache.
PATIENTS: dict[str, dict[str, str]] = {
    "0000-0001": {
        "id": "0000-0001",
        "name": "Anna Musterfrau",
        "as_of": "2016-04-15",
        "as_of_label": "15 April 2016",
        "source": "json",
        "cache_name": "matrix.json",
    },
    "0000-0002": {
        "id": "0000-0002",
        "name": "Beispielpatient",
        "as_of": "2021-11-12",
        "as_of_label": "12 November 2021",
        "source": "pdf",
        "cache_name": "matrix-0000-0002.json",
        "folder": "07_Stationaerer_Patientenbrief_2021-11-12 (1)",
    },
}


def cache_path(patient_id: str) -> Path:
    return ROOT / "cache" / PATIENTS[patient_id]["cache_name"]


def public_patient(patient_id: str) -> dict[str, str]:
    item = PATIENTS[patient_id]
    return {
        "id": item["id"],
        "name": item["name"],
        "as_of": item["as_of"],
        "as_of_label": item["as_of_label"],
        "source": item["source"],
    }
