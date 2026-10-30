"""Build Matrix 1 (verified facts) and Matrix 3 (alarms) from the eight letters."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "patient-0000-0001"
DOCS_DIR = DATA_DIR / "documents"
CACHE_DIR = ROOT / "cache"
CACHE_PATH = CACHE_DIR / "matrix.json"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

DOC_META = {
    "12340008": {"short": "D1", "title": "Carotid duplex", "date": "2015-06-11"},
    "12340009": {"short": "D2", "title": "Long-term ECG", "date": "2015-06-12"},
    "12340010": {"short": "D3", "title": "24-hour blood pressure", "date": "2015-06-13"},
    "12340011": {"short": "D4", "title": "Eye consult", "date": "2015-06-13"},
    "12340012": {"short": "D5", "title": "Inpatient letter, hypertensive crisis", "date": "2015-06-28"},
    "12340014": {"short": "D6", "title": "Outpatient oncology letter", "date": "2016-04-05"},
    "12340016": {"short": "D7", "title": "Histology", "date": "2016-04-13"},
    "12340018": {"short": "D8", "title": "Inpatient letter, breast cancer", "date": "2016-04-15"},
}


def normalize_text(raw: str) -> str:
    text = raw.replace("<BR>", "\n")
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def load_documents() -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for doc_id, meta in DOC_META.items():
        path = DOCS_DIR / f"{doc_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = normalize_text(payload.get("text", ""))
        docs[doc_id] = {
            "id": doc_id,
            "title": meta["title"],
            "date": meta["date"],
            "short": meta["short"],
            "text": text,
            "lines": [ln.strip() for ln in text.split("\n") if ln.strip()],
        }
    return docs


def quote_in_doc(quote: str, text: str) -> bool:
    if not quote:
        return False
    if quote in text:
        return True
    # tolerate collapsed whitespace
    collapsed_q = re.sub(r"\s+", " ", quote).strip()
    collapsed_t = re.sub(r"\s+", " ", text)
    return collapsed_q in collapsed_t


# Admission and discharge: the day in the sentence is compared with the letter date.
EVENT_ROWS = {
    "april_2016_admission",
    "admission_date",
    "discharge_date",
}

# Rows whose time is when the value was measured, not when the letter was signed.
MEASUREMENT_ROWS = {
    "height_cm",
    "weight_kg",
    "bmi_stated",
    "bmi_from_height_weight",
    "lvef_pct",
    "hba1c_pct",
    "blood_pressure_mmHg",
    "creatinine",
    "haemoglobin",
    "egfr",
    "tumour_size",
    "biopsy_date",
}
VITAL_ROWS = {
    "height_cm",
    "weight_kg",
    "bmi_stated",
    "bmi_from_height_weight",
    "blood_pressure_mmHg",
}
LAB_ROWS = {"creatinine", "haemoglobin", "egfr", "hba1c_pct"}

_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)")
_MONTH_DATE = re.compile(
    r"(?<!\d)(\d{1,2})\.?\s+"
    r"(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)"
    r"\s+(\d{4})",
    re.IGNORECASE,
)


def _iso_date(day: str, month: str, year: str) -> str | None:
    try:
        d, m, y = int(day), int(month), int(year)
    except ValueError:
        return None
    if not (1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def dates_in(text: str) -> list[str]:
    """Calendar dates written in text, in order, without duplicates in a row."""
    found: list[tuple[int, str]] = []
    for match in _NUMERIC_DATE.finditer(text):
        iso = _iso_date(match.group(1), match.group(2), match.group(3))
        if iso:
            found.append((match.start(), iso))
    for match in _MONTH_DATE.finditer(text):
        month = _MONTHS[match.group(2).lower()]
        iso = _iso_date(match.group(1), str(month), match.group(3))
        if iso:
            found.append((match.start(), iso))
    found.sort(key=lambda item: item[0])
    ordered: list[str] = []
    for _, iso in found:
        if iso not in ordered:
            ordered.append(iso)
    return ordered


def _one_date(text: str) -> str | None:
    found = dates_in(text)
    if len(found) == 1:
        return found[0]
    return None


def _admission_dates(text: str) -> list[str]:
    found: list[str] = []
    patterns = (
        r"Aufnahme am\s+(\d{1,2}[./]\d{1,2}[./]\d{4})",
        r"wurde am\s+(\d{1,2}[./]\d{1,2}[./]\d{4}).{0,80}aufgenommen",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            iso = dates_in(match.group(1))
            if iso and iso[0] not in found:
                found.append(iso[0])
    return found


def resolve_measurement_date(text: str, quote: str, row: str, fallback: str) -> tuple[str, bool]:
    """Return (date, found_in_text).

    A date written on the measurement wins over the letter date. The letter
    date is only the fallback when the text does not date the measurement.
    """
    if row not in MEASUREMENT_ROWS and row not in EVENT_ROWS:
        return fallback, False

    in_quote = _one_date(quote)
    if in_quote:
        return in_quote, True
    if row not in MEASUREMENT_ROWS:
        return fallback, False

    idx = text.find(quote)
    if idx < 0:
        collapsed = re.sub(r"\s+", " ", text)
        collapsed_q = re.sub(r"\s+", " ", quote).strip()
        idx = collapsed.find(collapsed_q)
        text = collapsed
        quote = collapsed_q
    if idx < 0:
        return fallback, False

    # A date counts only when a label ties it to this measurement. A date earlier
    # on the same wrapped line can belong to a different sentence.
    prefix = text[max(0, idx - 80) : idx]
    labelled = list(
        re.finditer(
            r"(?:vom|bei Aufnahme\s*\(|Labor bei Aufnahme\s*\(|Probenentnahme:\s*|Entnahmedatum:\s*|Beginn:\s*)"
            r"(\d{1,2}[./]\d{1,2}[./]\d{4})",
            prefix,
            re.IGNORECASE,
        )
    )
    if labelled:
        parsed = dates_in(labelled[-1].group(1))
        if parsed:
            return parsed[0], True

    window = text[max(0, idx - 250) : idx + len(quote) + 400]
    if re.search(r"bei Aufnahme|Zeitpunkt der Aufnahme", window, re.IGNORECASE):
        admitted = _admission_dates(text)
        if len(admitted) == 1:
            return admitted[0], True
        local = text[max(0, idx - 80) : idx + len(quote)]
        labelled = re.search(
            r"(?:bei Aufnahme|Labor bei Aufnahme)\s*\(?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})",
            local,
            re.IGNORECASE,
        )
        if labelled:
            parsed = dates_in(labelled.group(1))
            if parsed:
                return parsed[0], True

    if row in LAB_ROWS:
        sample = None
        for match in re.finditer(
            r"(Probenentnahme|Entnahmedatum)\s*:?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})",
            text[:idx],
            re.IGNORECASE,
        ):
            parsed = dates_in(match.group(2))
            if parsed:
                sample = parsed[0]
        if sample:
            return sample, True

    if row in VITAL_ROWS:
        visit = re.search(
            r"am\s+(\d{1,2}[./]\d{1,2}[./]\d{4}).{0,100}in Behandlung",
            text,
            re.IGNORECASE,
        )
        if visit:
            parsed = dates_in(visit.group(1))
            if parsed:
                return parsed[0], True
        begun = None
        for match in re.finditer(
            r"Beginn:\s*(\d{1,2}[./]\d{1,2}[./]\d{4})",
            text[:idx],
            re.IGNORECASE,
        ):
            parsed = dates_in(match.group(1))
            if parsed:
                begun = parsed[0]
        if begun:
            return begun, True

    if row == "tumour_size":
        lines = [line.strip() for line in text[:idx].split("\n") if line.strip()]
        for line in reversed(lines[-4:]):
            if re.search(r"(Ultraschall|Mammograph|Histolog)", line, re.IGNORECASE) and re.search(
                r"\bvom\b", line, re.IGNORECASE
            ):
                heading = _one_date(line)
                if heading:
                    return heading, True

    return fallback, False


def finalize_measurement_dates(
    facts: list[dict[str, Any]],
    docs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Store date_of_measurement from the text, and use it as the fact date."""
    for fact in facts:
        document = docs.get(fact["doc_id"])
        if document is None:
            fact["date_of_measurement"] = fact["date"]
            continue
        fact["document_date"] = document["date"]
        measured, from_text = resolve_measurement_date(
            document["text"],
            fact["quote_de"],
            fact["row"],
            fact["date"],
        )
        if from_text:
            fact["date"] = measured
        fact["date_of_measurement"] = fact["date"]

    # A later letter that pastes the same sentence is not a new measurement.
    # Short vital lines such as "Gewicht: 78 kg" are excluded: the same wording
    # can be a real later reading.
    vital_line = re.compile(r"^(Größe|Gewicht|BMI|RR)\b")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        if fact["row"] not in MEASUREMENT_ROWS or vital_line.match(fact["quote_de"].strip()):
            continue
        key = (
            fact["row"],
            fact["value"],
            re.sub(r"\s+", " ", fact["quote_de"]).strip(),
        )
        groups.setdefault(key, []).append(fact)
    for group in groups.values():
        if len({fact["doc_id"] for fact in group}) < 2:
            continue
        true = min(fact["date_of_measurement"] for fact in group)
        for fact in group:
            fact["date"] = true
            fact["date_of_measurement"] = true

    for fact in facts:
        documented = fact.get("document_date")
        in_text = fact.get("date_of_measurement")
        row = fact.get("row") or ""
        if row in MEASUREMENT_ROWS:
            kind = "measurement"
        elif "discharge" in row:
            kind = "discharge"
        elif "admission" in row:
            kind = "admission"
        else:
            kind = ""
        if kind and documented and in_text and documented != in_text:
            fact["date_mismatch"] = {
                "kind": kind,
                "documented": documented,
                "in_text": in_text,
            }
        else:
            fact.pop("date_mismatch", None)
    return facts


def make_fact(
    row: str,
    value: str,
    display: str,
    date: str,
    doc_id: str,
    quote_de: str,
    unit: str = "",
    docs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if docs is not None and not quote_in_doc(quote_de, docs[doc_id]["text"]):
        return None
    return {
        "row": row,
        "value": value,
        "display": display,
        "unit": unit,
        "date": date,
        "doc_id": doc_id,
        "quote_de": quote_de,
        "sentence_id": f"{doc_id}:{abs(hash(quote_de)) % 10_000_000}",
    }


def seed_facts(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic Matrix 1 cells with German quotes verified against the letters."""
    raw = [
        # Allergy
        ("allergy_contrast", "contrast_media", "Contrast media allergy (nausea, dizziness, vomiting)", "2015-06-28", "12340012", "KM-Allergie (Übelkeit, Schwindel, Erbrechen)"),
        ("allergy_contrast", "contrast_media", "Contrast media allergy (nausea and vomiting wording)", "2015-06-28", "12340012", "Allergie: KM-Allergie mit Übelkeit und Erbrechen bei letzter Untersuchung"),
        ("allergy_contrast", "contrast_media", "Contrast media allergy (nausea, dizziness, vomiting)", "2016-04-15", "12340018", "KM-Allergie (Übelkeit, Schwindel, Erbrechen)"),
        # Vitals / BMI
        ("height_cm", "170", "170 cm", "2015-06-28", "12340012", "Größe: 170 cm", "cm"),
        ("weight_kg", "78", "78 kg", "2015-06-28", "12340012", "Gewicht: 78 kg", "kg"),
        ("bmi_stated", "29.4", "BMI 29.4", "2015-06-28", "12340012", "BMI: 29.4"),
        ("bmi_from_height_weight", "27.0", "BMI from height/weight ≈ 27.0", "2015-06-28", "12340012", "Gewicht: 78 kg"),
        ("height_cm", "171", "171 cm", "2016-04-05", "12340014", "Größe: 171 cm", "cm"),
        ("weight_kg", "67", "67 kg (visit 04.04.2016)", "2016-04-05", "12340014", "Gewicht: 67 kg", "kg"),
        ("bmi_stated", "29", "BMI 29", "2016-04-05", "12340014", "BMI: 29"),
        ("bmi_from_height_weight", "22.9", "BMI from height/weight ≈ 22.9", "2016-04-05", "12340014", "Gewicht: 67 kg"),
        ("height_cm", "170", "170 cm", "2016-04-15", "12340018", "Größe: 170 cm", "cm"),
        ("weight_kg", "66", "66 kg", "2016-04-15", "12340018", "Gewicht: 66 kg", "kg"),
        ("bmi_stated", "22.8", "BMI 22.8", "2016-04-15", "12340018", "BMI: 22,8"),
        ("bmi_from_height_weight", "22.8", "BMI from height/weight ≈ 22.8", "2016-04-15", "12340018", "Gewicht: 66 kg"),
        # Heart / labs
        ("lvef_pct", "60", "EF 60%, normal systolic LV function", "2015-06-28", "12340012", "Normale systolische LV-Funktion (EF 60%)", "%"),
        ("hba1c_pct", "6.4", "HbA1c 6.4%", "2015-06-13", "12340011", "HbA1c von 6,4%", "%"),
        ("hba1c_pct", "6.4", "HbA1c 6.4% (copied in discharge letter)", "2015-06-28", "12340012", "HbA1c von 6,4%", "%"),
        # Meds
        ("aspirin_100mg", "1-0-0", "Thrombo ASS 100 mg 1-0-0", "2015-06-13", "12340011", "Thrombo ASS 100 mg 1-0-0"),
        ("aspirin_100mg", "1-0-0", "Thrombo ASS 100 mg 1-0-0", "2015-06-28", "12340012", "Thrombo ASS 100mg oral 1 0 0 0 ST"),
        ("aspirin_100mg", "1-0-0", "Thrombo ASS 100 mg 1-0-0", "2016-04-15", "12340018", "Thrombo ASS 100mg oral 1 0 0 0 ST"),
        ("metformin_1000mg", "1-1-1", "Glucophage (metformin) 1000 mg 1-1-1", "2015-06-28", "12340012", "Glucophage 1000mg oral 1 1 1 0 ST"),
        ("metformin_1000mg", "1-1-1", "Glucophage (metformin) 1000 mg 1-1-1", "2016-04-15", "12340018", "Glucophage 1000mg oral 1 1 1 0 ST"),
        ("pioglitazone_30mg", "0-1-0", "Actos (pioglitazone) 30 mg 0-1-0", "2015-06-28", "12340012", "Actos 30mg oral 0 1 0 0 ST"),
        ("pioglitazone_30mg", "0-1-0", "Actos (pioglitazone) 30 mg 0-1-0", "2016-04-15", "12340018", "Actos 30mg oral 0 1 0 0 ST"),
        ("exenatide_5ug", "1-0-1", "Byetta (exenatide) 5 µg s.c. 1-0-1", "2015-06-28", "12340012", "Byetta Injektionslösung 5mcg 0,5 s.c. 1 0 1 0"),
        ("exenatide_5ug", "1-0-1", "Byetta (exenatide) 5 µg s.c. 1-0-1", "2016-04-15", "12340018", "Byetta Injektionslösung 5 mcg s.c. 1 0 1 0 Dosen"),
        ("candesartan_16mg", "1-0-1/2", "Blopress (candesartan) 16 mg 1-0-1/2", "2015-06-28", "12340012", "Blopress 16mg oral 1 0 1/2 0 ST"),
        ("candesartan_16mg", "1-0-1", "Blopress (candesartan) 16 mg 1-0-1", "2016-04-15", "12340018", "Blopress 16mg oral 1 0 1 0 ST"),
        # Carotid
        ("carotid_stenosis_side", "left", "Left ICA stenosis about 60%", "2015-06-11", "12340008", "Maximal 60%ige Abgangsstenose der Arteria carotis interna links."),
        ("carotid_stenosis_side", "left", "Left ICA about 60% on duplex body", "2015-06-11", "12340008", "Links findet sich in der A. carotis interna eine abgangsnahe Flussgeschwindigkeit von 150 cm/sek duch Einengung durch Kalkplaques sowie Verdickung des Intima media Komplexes. zu etwa 60%."),
        ("carotid_stenosis_side", "left", "60% left carotid stenosis", "2015-06-13", "12340011", "60% Karotisstenose links"),
        ("carotid_stenosis_side", "left", "Left ICA 60% (diagnosis line)", "2015-06-28", "12340012", "Carotissklerose li. (60%)"),
        ("carotid_stenosis_side", "left", "Left ICA 60% (conclusion)", "2015-06-28", "12340012", "Maximal 60%ige Abgangsstenose der Arteria carotis interna links."),
        ("carotid_stenosis_side", "right", "Copied duplex paragraph places 60% on the right", "2015-06-28", "12340012", "Rechts findet sich in der A. carotis interna eine abgangsnahe Flussgeschwindigkeit von 150 cm/sek duch Einengung durch Kalkplaques sowie Verdickung des Intima media Komplexes. zu etwa 60%."),
        # Prior episode / CT
        ("prior_episode", "hypertensive_crisis_2015", "Hypertensive crisis with amaurosis fugax, June 2015", "2015-06-13", "12340011", "Diagnose: Amaurosis fugax li. Auge mit 60% Stenose der A. Carotis sin., Fundus hypertonicus bds."),
        ("prior_episode", "hypertensive_crisis_2015", "Hypertensive crisis with dizziness and visual loss", "2015-06-28", "12340012", "Hypertensive Krise mit Schwindel und Sehstörung"),
        ("prior_ct_type", "native", "Head CT without contrast because of contrast allergy", "2015-06-28", "12340012", "Schädel-CT (nativ aufgrund einer bekannten KM-Allergie)"),
        # Tumour
        ("tumour_histology", "invasive_ductal_left", "Invasive ductal carcinoma, left breast", "2016-04-13", "12340016", "Stanzbiopsie der linken Brust mit Formationen eines invasiv duktalen Mammakarzinoms (T2 N0 M0 V0 G2)."),
        ("tumour_histology", "invasive_ductal_left", "Invasive ductal carcinoma, left breast", "2016-04-15", "12340018", "Histologie: invasiv duktales Mammakarzinom, Hormonrezeptor positiv, Her2neu negativ, Ki67-Proliferationsrate 20%, T2 N0 M0 V0 G2"),
        ("tumour_tnm", "T2 N0 M0 V0 G2", "T2 N0 M0 V0 G2", "2016-04-13", "12340016", "T2 N0 M0 V0 G2"),
        ("tumour_tnm", "T2 N0 M0 V0 G2", "T2 N0 M0 V0 G2", "2016-04-15", "12340018", "T2 N0 M0 V0 G2"),
        ("receptors_ki67", "ER+/PR+/HER2-/Ki67 20%", "ER 100% Allred 8, PR 70% Allred 7, HER2 neg, Ki-67 20%", "2016-04-13", "12340016", "Östrogenrezeptor: positiv (100% rezeptorpositive Tumorzellen) Allred-Score: 8 Progesteronrezeptor: positiv (70% rezeptorpositive Tumorzellen) Allred-Score: 7 Her2neu-Expression: negativ"),
        ("receptors_ki67", "Ki-67 20%", "Ki-67 20%", "2016-04-13", "12340016", "Ki67-Proliferationsrate: 20%"),
        ("tumour_size", "3x1.5cm", "Ultrasound 3 x 1.5 cm, BI-RADS V", "2016-04-15", "12340018", "Bekannte suspekte Läsion der linken Brust mit maximaler Ausdehnung 3 x 1,5 cm. BI-RADS V, ACR II."),
        ("tumour_size", "3cm", "External mammography about 3 cm", "2016-04-05", "12340014", "wurde als 3cm beschrieben"),
        ("tumour_board_plan", "quadrantectomy_iort_2016-05-16", "Quadrantectomy + IORT on 16.05.2016", "2016-04-15", "12340018", "Quadrantenresektion + IORT am 16.05.2016 an der chirurgischen Abteilung des Beispielkrankenhauses"),
        ("axillary_nodes", "enlarged_right_exam", "Enlarged right axillary nodes on examination", "2016-04-05", "12340014", "vergrößerte Lymphknoten rechts axillär."),
        ("axillary_nodes", "none_on_ultrasound", "No enlarged axillary nodes on ultrasound", "2016-04-15", "12340018", "Sonographisch zeigen sich axillär keine vergrößerten Lymphknoten."),
        ("biopsy_date", "2016-04-11", "Sample taken 11.04.2016", "2016-04-13", "12340016", "Entnahmedatum: 11.04.2016"),
        ("biopsy_date", "2016-04-12", "Ultrasound 12.04.2016 with biopsy described", "2016-04-15", "12340018", "Ultraschalluntersuchung der linken Brust vom 12.04.2016:"),
        ("april_2016_admission", "2016-04-10", "Header admits 10.04.2016", "2016-04-15", "12340018", "Aufnahme am 10/04/2016"),
        ("april_2016_admission", "2016-04-12", "Narrative admits 12.04.2016", "2016-04-15", "12340018", "wurde am 12.04.2016 in gutem Allgemeinzustand auf der Station aufgenommen"),
        ("april_2016_admission", "2016-04-10_planned", "Outpatient letter scheduled admission 10.04.2016", "2016-04-05", "12340014", "Stationäre Aufnahme auf Abteilung XX für den 10.04.2016 terminisiert"),
        # Follow-ups / comorbidities
        ("follow_up_2015", "carotid_duplex_2_months", "Carotid duplex in 2 months", "2015-06-28", "12340012", "Nächste geplanter Duplexsonographie der Karotisgefäße in 2 Monaten."),
        ("follow_up_2015", "eye_checks", "Regular eye checks", "2015-06-13", "12340011", "Regelmäßige augenärztliche Kontrollen empfohlen."),
        ("follow_up_2015", "bp_checks", "BP checks and GP medication adjustment", "2015-06-28", "12340012", "Regelmäßige Blutdruckkontrollen und eine weitere Anpassung der Medikation durch den Hausarzt sollten stattfinden."),
        ("sle", "yes", "Systemic lupus erythematosus", "2015-06-28", "12340012", "Systemischer Lupus erythematodes"),
        ("sle", "yes", "Systemic lupus erythematosus", "2016-04-05", "12340014", "Systemischer Lupus erythematodes"),
        ("sle", "yes", "SLE", "2016-04-15", "12340018", "SLE"),
        ("osa", "yes", "Sleep apnoea", "2015-06-28", "12340012", "Schlafapnoe"),
        ("diabetes", "yes", "Diabetes mellitus type II", "2015-06-28", "12340012", "Diabetes Mellitus Typ II"),
        ("date_of_birth", "1959-03-15", "Born 15.03.1959 (age 57 on 15 April 2016)", "1959-03-15", "12340012", "geb. 15.03.1959"),
        ("date_of_birth", "1959-03-15", "Born 15.03.1959 (age 57 on 15 April 2016)", "1959-03-15", "12340018", "geb. 15.03.1959"),
        ("date_of_birth", "1959-03-15", "Born 15.03.1959 (age 57 on 15 April 2016)", "1959-03-15", "12340010", "geb 15.03.1959"),
        ("hypertension", "yes", "Arterial hypertension", "2015-06-28", "12340012", "Art. Hypertonie"),
        ("blood_pressure_mmHg", "185/110", "185/110 mmHg during the hypertensive crisis", "2015-06-28", "12340012", "185/110 mmHg"),
        ("blood_pressure_mmHg", "145/90", "145/90 mmHg once the crisis had settled", "2015-06-28", "12340012", "Zum Zeitpunkt der Aufnahme hatte sich der Blutdruck bereits auf 145/90 mmHg normalisiert."),
        ("blood_pressure_mmHg", "140/90", "140/90 mmHg on the admission examination", "2015-06-28", "12340012", "140/90 mmHg"),
        ("blood_pressure_mmHg", "135/84", "24-hour mean 135/84 mmHg", "2015-06-13", "12340010", "24-Mittelwert: 135/84 mmHg"),
        ("blood_pressure_mmHg", "140/88", "Daytime mean 140/88 mmHg", "2015-06-13", "12340010", "Tagesmittelwert: 140/88 mmHg"),
        ("blood_pressure_mmHg", "170/85", "Morning peak up to 170/85 mmHg", "2015-06-13", "12340010", "erhöhter Blutdruck bis 170/85 mmHg"),
        ("blood_pressure_mmHg", "145/88", "145/88 mmHg on 4 April 2016", "2016-04-05", "12340014", "RR: 145/88 mmHg"),
    ]

    facts: list[dict[str, Any]] = []
    for item in raw:
        if len(item) == 6:
            row, value, display, date, doc_id, quote = item
            unit = ""
        else:
            row, value, display, date, doc_id, quote, unit = item
        fact = make_fact(row, value, display, date, doc_id, quote, unit, docs)
        if fact:
            facts.append(fact)
        else:
            print(f"[matrix] dropped unverified quote in {doc_id}: {quote[:60]}...")
    return finalize_measurement_dates(facts, docs)


def build_contradictions(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Matrix 3: C1–C5 only. Allergy symptom subsets are not alarming."""
    def passage(doc_id: str, quote: str) -> dict[str, str] | None:
        if not quote_in_doc(quote, docs[doc_id]["text"]):
            return None
        return {"doc_id": doc_id, "quote_de": quote, "date": DOC_META[doc_id]["date"]}

    contradictions = []

    c1_passages = [
        passage("12340008", "Maximal 60%ige Abgangsstenose der Arteria carotis interna links."),
        passage("12340011", "60% Karotisstenose links"),
        passage("12340012", "Carotissklerose li. (60%)"),
        passage("12340012", "Maximal 60%ige Abgangsstenose der Arteria carotis interna links."),
        passage(
            "12340012",
            "Rechts findet sich in der A. carotis interna eine abgangsnahe Flussgeschwindigkeit von 150 cm/sek duch Einengung durch Kalkplaques sowie Verdickung des Intima media Komplexes. zu etwa 60%.",
        ),
    ]
    c1_passages = [p for p in c1_passages if p]
    if len(c1_passages) >= 2:
        contradictions.append(
            {
                "id": "C1",
                "row": "carotid_stenosis_side",
                "title": "Side of carotid stenosis",
                "summary": (
                    "Most passages place a ~60% stenosis on the left ICA. A duplex paragraph "
                    "copied into the June 2015 letter places the 60% stenosis on the right."
                ),
                "alarming": True,
                "passages": c1_passages,
            }
        )

    c2_passages = [
        passage("12340012", "Größe: 170 cm"),
        passage("12340012", "Gewicht: 78 kg"),
        passage("12340012", "BMI: 29.4"),
    ]
    c2_passages = [p for p in c2_passages if p]
    if len(c2_passages) >= 2:
        contradictions.append(
            {
                "id": "C2",
                "row": "bmi_stated",
                "title": "BMI vs height/weight (June 2015)",
                "summary": "D5 states BMI 29.4 with 170 cm and 78 kg; 78 / 1.70² ≈ 27.0 (difference > 0.5).",
                "alarming": True,
                "passages": c2_passages,
            }
        )

    c3_passages = [
        passage("12340014", "Größe: 171 cm"),
        passage("12340014", "Gewicht: 67 kg"),
        passage("12340014", "BMI: 29"),
        passage("12340018", "BMI: 22,8"),
    ]
    c3_passages = [p for p in c3_passages if p]
    if len(c3_passages) >= 2:
        contradictions.append(
            {
                "id": "C3",
                "row": "bmi_stated",
                "title": "BMI vs height/weight (April 2016 outpatient)",
                "summary": (
                    "D6 states BMI 29 with 171 cm and 67 kg; 67 / 1.71² ≈ 22.9. "
                    "D8 (66 kg, BMI 22.8) matches its own figures."
                ),
                "alarming": True,
                "passages": c3_passages,
            }
        )

    c4_passages = [
        passage("12340018", "Aufnahme am 10/04/2016"),
        passage("12340018", "wurde am 12.04.2016 in gutem Allgemeinzustand auf der Station aufgenommen"),
        passage("12340014", "Stationäre Aufnahme auf Abteilung XX für den 10.04.2016 terminisiert"),
    ]
    c4_passages = [p for p in c4_passages if p]
    if len(c4_passages) >= 2:
        contradictions.append(
            {
                "id": "C4",
                "row": "april_2016_admission",
                "title": "Admission date April 2016",
                "summary": (
                    "D8 header admits her on 10.04.2016; the narrative admits her on 12.04.2016. "
                    "D6 had scheduled 10.04.2016."
                ),
                "alarming": True,
                "passages": c4_passages,
            }
        )

    c5_passages = [
        passage("12340016", "Entnahmedatum: 11.04.2016"),
        passage("12340018", "Ultraschalluntersuchung der linken Brust vom 12.04.2016:"),
        passage("12340018", "Es erfolgte die ultraschallgezielte Biopsie von 5 Stanzzylindern."),
    ]
    c5_passages = [p for p in c5_passages if p]
    if len(c5_passages) >= 2:
        contradictions.append(
            {
                "id": "C5",
                "row": "biopsy_date",
                "title": "Biopsy date",
                "summary": (
                    "Histology lists sample date 11.04.2016; the April 2016 letter describes "
                    "ultrasound-guided biopsy with the 12.04.2016 ultrasound."
                ),
                "alarming": True,
                "passages": c5_passages,
            }
        )

    return contradictions


def ollama_available() -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def call_ollama(prompt: str, system: str = "", timeout: int = 180) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if system:
        payload["system"] = system
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("response", "")


EXTRACTION_SYSTEM = """You extract clinical facts from German hospital letters for one synthetic patient.
Return ONLY a JSON array. Each item:
{"row":"...","value":"...","display":"...","date":"YYYY-MM-DD","doc_id":"...","quote_de":"..."}
Rules:
- quote_de must be an exact substring of the given document text.
- date is the date of measurement written in the text. Use a labelled sample, visit,
  or admission date when the sentence gives one. Use the letter date only when the
  text does not date the measurement.
- Use row names from: allergy_contrast, aspirin_100mg, metformin_1000mg, weight_kg, height_cm,
  bmi_stated, lvef_pct, hba1c_pct, carotid_stenosis_side, tumour_histology, tumour_tnm,
  receptors_ki67, tumour_board_plan, sle, candesartan_16mg, prior_episode, prior_ct_type.
- Fewer allergy symptoms than a fuller line is the SAME allergy, not a conflict.
- Do not invent facts. Do not add medical advice.
"""


def enrich_with_llama(docs: dict[str, dict[str, Any]], seed: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Ask Llama once to extract facts; keep only quote-verified cells; merge with seed."""
    if not ollama_available():
        return seed, "ollama_unavailable"

    # Send the two longest letters plus histology — enough for meds, tumour, allergy.
    chosen = ["12340012", "12340018", "12340016", "12340014", "12340011", "12340008"]
    chunks = []
    for doc_id in chosen:
        d = docs[doc_id]
        chunks.append(f"=== DOC {doc_id} date={d['date']} title={d['title']} ===\n{d['text'][:6000]}")
    prompt = (
        "Extract facts as a JSON array from these documents.\n\n" + "\n\n".join(chunks)
    )
    try:
        response = call_ollama(prompt, system=EXTRACTION_SYSTEM, timeout=240)
    except Exception as exc:  # noqa: BLE001
        print(f"[matrix] Ollama extraction failed: {exc}")
        return seed, f"ollama_error:{exc}"

    match = re.search(r"\[.*\]", response, re.DOTALL)
    if not match:
        print("[matrix] Ollama returned no JSON array; using seed only")
        return seed, "ollama_no_json"

    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        print("[matrix] Ollama JSON parse failed; using seed only")
        return seed, "ollama_bad_json"

    verified: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("doc_id", ""))
        quote = str(item.get("quote_de", "")).strip()
        row = str(item.get("row", "")).strip()
        if doc_id not in docs or not row or not quote:
            continue
        if not quote_in_doc(quote, docs[doc_id]["text"]):
            continue
        verified.append(
            {
                "row": row,
                "value": str(item.get("value", "")),
                "display": str(item.get("display") or item.get("value") or row),
                "unit": str(item.get("unit", "")),
                "date": str(item.get("date") or DOC_META[doc_id]["date"]),
                "doc_id": doc_id,
                "quote_de": quote,
                "sentence_id": f"{doc_id}:{abs(hash(quote)) % 10_000_000}",
                "source": "llama",
            }
        )

    # Prefer seed for known rows (stable answers); add Llama-only new rows.
    seed_keys = {(f["row"], f["doc_id"], f["quote_de"]) for f in seed}
    merged = list(seed)
    for fact in verified:
        key = (fact["row"], fact["doc_id"], fact["quote_de"])
        if key not in seed_keys:
            fact_marked = dict(fact)
            fact_marked.setdefault("source", "llama")
            merged.append(fact_marked)
    for f in merged:
        f.setdefault("source", "seed")
    return finalize_measurement_dates(merged, docs), f"ollama_ok:{len(verified)}_verified"


def build_matrix(force: bool = False) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_PATH.exists() and not force:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    print("[matrix] Loading documents...")
    docs = load_documents()
    print("[matrix] Building verified seed facts...")
    seed = seed_facts(docs)
    print(f"[matrix] Seed facts kept: {len(seed)}")
    print(f"[matrix] Calling Ollama ({OLLAMA_MODEL}) for enrichment...")
    facts, llama_status = enrich_with_llama(docs, seed)
    print(f"[matrix] Llama status: {llama_status}; facts total: {len(facts)}")
    contradictions = build_contradictions(docs)
    print(f"[matrix] Alarms: {[c['id'] for c in contradictions]}")

    payload = {
        "status": "ready",
        "patient_key": "0000-0001|1959-03-15",
        "as_of": "2016-04-15",
        "llama_status": llama_status,
        "model": OLLAMA_MODEL,
        "facts": facts,
        "contradictions": contradictions,
        "documents": {
            doc_id: {
                "id": doc_id,
                "title": d["title"],
                "date": d["date"],
                "short": d["short"],
                "text": d["text"],
            }
            for doc_id, d in docs.items()
        },
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[matrix] Cached to {CACHE_PATH}")
    return payload


def facts_for_rows(
    matrix: dict[str, Any],
    rows: list[str],
    column_rule: str = "latest",
    preferred_docs: list[str] | None = None,
) -> list[dict[str, Any]]:
    preferred_docs = preferred_docs or []
    selected: list[dict[str, Any]] = []
    for row in rows:
        row_facts = [f for f in matrix["facts"] if f["row"] == row]
        if not row_facts:
            continue
        row_facts = sorted(row_facts, key=lambda f: f.get("date_of_measurement") or f["date"])
        if column_rule == "latest":
            latest_date = row_facts[-1].get("date_of_measurement") or row_facts[-1]["date"]
            latest = [
                f
                for f in row_facts
                if (f.get("date_of_measurement") or f["date"]) == latest_date
            ]
            # Prefer preferred docs among latest, else all latest
            preferred = [f for f in latest if f["doc_id"] in preferred_docs]
            chosen = preferred or latest
            # Also attach earlier preferred sources when the catalogue lists them
            earlier = [
                f
                for f in row_facts
                if f["doc_id"] in preferred_docs and f not in chosen
            ]
            selected.extend(chosen + earlier)
        else:
            if preferred_docs:
                preferred = [f for f in row_facts if f["doc_id"] in preferred_docs]
                selected.extend(preferred or row_facts)
            else:
                selected.extend(row_facts)
    # de-dupe by quote+doc
    seen = set()
    out = []
    for f in selected:
        key = (f["doc_id"], f["quote_de"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


if __name__ == "__main__":
    build_matrix(force=True)
