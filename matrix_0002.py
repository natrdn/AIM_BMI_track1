"""Matrix for patient 0000-0002. Writes only cache/matrix-0000-0002.json."""

from __future__ import annotations

import json
import re
from typing import Any

import patients
import pdf_extract
from matrix import (
    OLLAMA_MODEL,
    call_ollama,
    finalize_measurement_dates,
    make_fact,
    ollama_available,
    quote_in_doc,
)

CACHE_PATH = patients.cache_path("0000-0002")

PDF_DOCS = [
    ("p2-01", "01_Ambulanter_Patientenbrief_Kardiologie_2021-09-14.pdf", "D1", "Outpatient cardiology letter", "2021-09-14"),
    ("p2-02", "02_Echokardiographie_2021-09-20.pdf", "D2", "Echocardiography", "2021-09-20"),
    ("p2-03", "03_Pneumologie_Lungenfunktion_2021-10-05.pdf", "D3", "Lung function", "2021-10-05"),
    ("p2-04", "04_Histologie_2021-10-18.pdf", "D4", "Histology", "2021-10-18"),
    ("p2-05", "05_CT_Thorax_Abdomen_2021-10-25.pdf", "D5", "CT thorax and abdomen", "2021-10-25"),
    ("p2-06", "06_Laborbefund_2021-10-28.pdf", "D6", "Laboratory report", "2021-10-28"),
    ("p2-07", "07_Stationaerer_Patientenbrief_2021-11-12 (1).pdf", "D7", "Inpatient letter", "2021-11-12"),
]

EXPECTED_ALARMS = [
    "P2-BMI",
    "P2-EF",
    "P2-ALLERGY",
    "P2-BIOPSY",
    "P2-SITE",
    "P2-NSTAGE",
    "P2-AGE",
    "P2-SMOKING",
    "P2-DISCHARGE",
]

EXTRACTION_SYSTEM = """You extract clinical facts from German hospital letters for one synthetic patient.
Return ONLY a JSON array. Each item:
{"row":"...","value":"...","display":"...","date":"YYYY-MM-DD","doc_id":"...","quote_de":"..."}
Rules:
- quote_de must be an exact substring of the given document text.
- date is the date of measurement written in the text. Use a labelled sample, visit,
  or admission date when the sentence gives one. Use the letter date only when the
  text does not date the measurement.
- doc_id must be one of the DOC ids in the prompt.
- Use only row names from the list in the prompt.
- Do not invent facts. Do not add medical advice.
- A dose that changed over time is not a conflict. A small measurement difference is not a conflict.
"""


def _fact(docs: dict[str, dict[str, Any]], **item: str) -> dict[str, Any]:
    fact = make_fact(
        item["row"],
        item["value"],
        item["display"],
        item["date"],
        item["doc_id"],
        item["quote"],
        "",
        docs,
    )
    if fact is None:
        raise RuntimeError(f"Unverified quote in {item['doc_id']}: {item['quote']}")
    fact["source"] = "seed"
    return fact


def seed_facts(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw = [
        # Allergy
        dict(row="allergy_penicillin", value="penicillin_exanthem", display="Penicillin allergy (exanthem)", date="2021-09-14", doc_id="p2-01", quote="Penicillin-Allergie (Exanthem)"),
        dict(row="allergy_none", value="none_stated", display="Discharge letter: no allergies known", date="2021-11-12", doc_id="p2-07", quote="Allergien: keine bekannt"),
        dict(row="allergy_contrast", value="none_known", display="No known contrast-media allergy (CT request)", date="2021-10-25", doc_id="p2-05", quote="Keine bekannte Kontrastmittelallergie"),
        # Body size. 1-0-0 style doses below are read from the morning/midday/evening/night table cells.
        dict(row="height_cm", value="182", display="182 cm (14 Sep 2021)", date="2021-09-14", doc_id="p2-01", quote="Größe: 182 cm"),
        dict(row="weight_kg", value="95", display="95 kg (14 Sep 2021)", date="2021-09-14", doc_id="p2-01", quote="Gewicht: 95 kg"),
        dict(row="bmi_stated", value="26.1", display="BMI 26.1 (14 Sep 2021)", date="2021-09-14", doc_id="p2-01", quote="BMI: 26,1"),
        dict(row="bmi_from_height_weight", value="28.7", display="BMI from height/weight ≈ 28.7 (14 Sep 2021)", date="2021-09-14", doc_id="p2-01", quote="Gewicht: 95 kg"),
        dict(row="height_cm", value="181", display="181 cm on admission (8 Nov 2021)", date="2021-11-12", doc_id="p2-07", quote="Größe: 181 cm"),
        dict(row="weight_kg", value="91", display="91 kg on admission (8 Nov 2021)", date="2021-11-12", doc_id="p2-07", quote="Gewicht: 91 kg"),
        dict(row="bmi_stated", value="27.8", display="BMI 27.8 on admission (8 Nov 2021)", date="2021-11-12", doc_id="p2-07", quote="BMI: 27,8"),
        dict(row="bmi_from_height_weight", value="27.8", display="BMI from height/weight ≈ 27.8 on admission (8 Nov 2021)", date="2021-11-12", doc_id="p2-07", quote="Gewicht: 91 kg"),
        # Heart
        dict(row="lvef_pct", value="35", display="EF 35%, severely reduced systolic function (echo findings, 20 Sep 2021)", date="2021-09-20", doc_id="p2-02", quote="Hochgradig eingeschränkte systolische LV-Funktion (EF 35%)"),
        dict(row="lvef_pct", value="45", display="EF 45%, moderately reduced, in the echo summary (20 Sep 2021)", date="2021-09-20", doc_id="p2-02", quote="mittelgradig eingeschränkter LV-Funktion (EF 45%)"),
        dict(row="lvef_pct", value="35", display="EF 35% (discharge letter, 12 Nov 2021)", date="2021-11-12", doc_id="p2-07", quote="eingeschränkte linksventrikuläre Funktion (EF 35%)"),
        dict(row="heart_failure", value="hfref", display="Heart failure with reduced ejection fraction", date="2021-09-14", doc_id="p2-01", quote="Herzinsuffizienz mit reduzierter Ejektionsfraktion"),
        dict(row="heart_failure", value="hfref", display="Heart failure with reduced EF", date="2021-11-12", doc_id="p2-07", quote="Herzinsuffizienz mit reduzierter EF"),
        dict(row="atrial_fibrillation", value="permanent", display="Permanent atrial fibrillation", date="2021-09-14", doc_id="p2-01", quote="Permanentes Vorhofflimmern"),
        dict(row="atrial_fibrillation", value="permanent", display="Permanent atrial fibrillation (VHF)", date="2021-11-12", doc_id="p2-07", quote="Permanentes VHF"),
        dict(row="blood_pressure_mmHg", value="152/92", display="152/92 mmHg (14 Sep 2021)", date="2021-09-14", doc_id="p2-01", quote="RR: 152/92 mmHg"),
        dict(row="blood_pressure_mmHg", value="138/84", display="138/84 mmHg on admission (8 Nov 2021)", date="2021-11-12", doc_id="p2-07", quote="RR bei Aufnahme: 138/84 mmHg"),
        # Antithrombotic and other meds. 1-0-0 is the table under Xarelto (morning only).
        dict(row="rivaroxaban", value="20mg_1-0-0", display="Xarelto (rivaroxaban) 20 mg 1-0-0", date="2021-09-14", doc_id="p2-01", quote="Xarelto 20mg"),
        dict(row="rivaroxaban", value="20mg_continued", display="Rivaroxaban 20 mg continued", date="2021-09-14", doc_id="p2-01", quote="Rivaroxaban 20 mg wird fortgeführt"),
        dict(row="rivaroxaban", value="15mg", display="Rivaroxaban reduced to 15 mg because eGFR is 36 ml/min", date="2021-11-12", doc_id="p2-07", quote="Rivaroxaban-Dosis auf 15 mg"),
        dict(row="rivaroxaban", value="15mg_1-0-0", display="Xarelto (rivaroxaban) 15 mg 1-0-0 at discharge", date="2021-11-12", doc_id="p2-07", quote="Xarelto 15mg"),
        dict(row="rivaroxaban", value="hold_2_days", display="Rivaroxaban paused 2 days before the operation", date="2021-11-12", doc_id="p2-07", quote="Rivaroxaban wird 2 Tage vor dem Eingriff pausiert."),
        dict(row="ramipril_5mg", value="5mg", display="Ramipril 5 mg", date="2021-09-14", doc_id="p2-01", quote="Ramipril 5mg"),
        dict(row="ramipril_5mg", value="5mg", display="Ramipril 5 mg", date="2021-11-12", doc_id="p2-07", quote="Ramipril 5mg"),
        dict(row="bisoprolol_5mg", value="5mg", display="Bisoprolol 5 mg", date="2021-09-14", doc_id="p2-01", quote="Bisoprolol 5mg"),
        dict(row="bisoprolol_5mg", value="5mg", display="Bisoprolol 5 mg", date="2021-11-12", doc_id="p2-07", quote="Bisoprolol 5mg"),
        dict(row="tiotropium", value="18ug_1-0-0", display="Tiotropium 18 µg 1-0-0 inhaled, started 5 Oct 2021", date="2021-10-05", doc_id="p2-03", quote="Beginn von Tiotropium 18 µg 1-0-0 inhalativ"),
        dict(row="tiotropium", value="continued", display="Tiotropium continued at discharge", date="2021-11-12", doc_id="p2-07", quote="Tiotropium wurde fortgeführt"),
        # Lungs, kidney, blood count
        dict(row="copd", value="gold_ii", display="COPD GOLD II", date="2021-09-14", doc_id="p2-01", quote="COPD GOLD II"),
        dict(row="copd", value="gold_ii", display="COPD GOLD II, obstructive ventilatory defect", date="2021-10-05", doc_id="p2-03", quote="Obstruktive Ventilationsstörung, COPD GOLD II, bei aktivem Nikotinabusus mit Lungenemphysem."),
        dict(row="smoking_status", value="ex_smoker_2010", display="Ex-smoker, stopped 2010, 30 pack-years", date="2021-10-05", doc_id="p2-03", quote="Nikotinstopp 2010"),
        dict(row="smoking_status", value="active", display="Active nicotine use (same lung-function letter)", date="2021-10-05", doc_id="p2-03", quote="bei aktivem Nikotinabusus"),
        dict(row="ckd", value="g3b", display="Chronic kidney disease, stage G3b", date="2021-09-14", doc_id="p2-01", quote="Chronische Niereninsuffizienz Stadium G3b"),
        dict(row="ckd", value="g3b", display="Chronic kidney disease, stage G3b", date="2021-11-12", doc_id="p2-07", quote="Chronische Niereninsuffizienz G3b"),
        dict(row="egfr", value="36", display="eGFR 36 ml/min", date="2021-11-12", doc_id="p2-07", quote="Bei eGFR 36 ml/min"),
        dict(row="creatinine", value="1.2", display="Creatinine 1.2 mg/dl on 22 Oct 2021 (CT request)", date="2021-10-22", doc_id="p2-05", quote="Kreatinin vom 22.10.2021: 1,2 mg/dl"),
        dict(row="creatinine", value="1.7", display="Creatinine 1.7 mg/dl on admission (8 Nov 2021)", date="2021-11-08", doc_id="p2-07", quote="Kreatinin 1,7 mg/dl"),
        dict(row="haemoglobin", value="12.1", display="Haemoglobin 12.1 g/dl on admission (8 Nov 2021)", date="2021-11-08", doc_id="p2-07", quote="Hb 12,1 g/dl"),
        dict(row="creatinine", value="1.9", display="Creatinine 1.9 mg/dl (sample 28 Oct 2021)", date="2021-10-28", doc_id="p2-06", quote="Kreatinin\n1,9"),
        dict(row="egfr", value="36", display="eGFR 36 ml/min (sample 28 Oct 2021)", date="2021-10-28", doc_id="p2-06", quote="eGFR\n36"),
        dict(row="haemoglobin", value="10.8", display="Haemoglobin 10.8 g/dl (sample 28 Oct 2021)", date="2021-10-28", doc_id="p2-06", quote="H\u00e4moglobin\n10,8"),
        dict(row="hypertension", value="yes", display="Arterial hypertension", date="2021-09-14", doc_id="p2-01", quote="Arterielle Hypertonie"),
        dict(row="hypertension", value="yes", display="Arterial hypertension", date="2021-11-12", doc_id="p2-07", quote="Art. Hypertonie"),
        # Tumour
        dict(row="tumour_histology", value="adeno_colon", display="Adenocarcinoma of the colon, glandular differentiation", date="2021-10-18", doc_id="p2-04", quote="infiltrativ wachsendem Adenokarzinom des Kolons"),
        dict(row="tumour_histology", value="adeno_g2", display="Adenocarcinoma G2 (histology summary)", date="2021-10-18", doc_id="p2-04", quote="Adenokarzinom (G2)"),
        dict(row="tumour_histology", value="adeno_descendens", display="Adenocarcinoma G2 recorded as descending-colon carcinoma (discharge diagnosis)", date="2021-11-12", doc_id="p2-07", quote="Kolonkarzinom des Colon descendens"),
        dict(row="tumour_tnm", value="cT3 cN1 cM0", display="cT3 cN1 cM0 (CT, 25 Oct 2021)", date="2021-10-25", doc_id="p2-05", quote="cT3 cN1 cM0"),
        dict(row="tumour_tnm", value="cT3 cN0 cM0", display="cT3 cN0 cM0 (discharge diagnosis)", date="2021-11-12", doc_id="p2-07", quote="cT3 cN0 cM0"),
        dict(row="tumour_site", value="sigmoid", display="Sigmoid colon (histology specimen, 28 cm from the anus)", date="2021-10-18", doc_id="p2-04", quote="Zangenbiopsien, Colon sigmoideum, 28 cm ab ano"),
        dict(row="tumour_site", value="sigmoid", display="Sigmoid colon wall thickening (CT)", date="2021-10-25", doc_id="p2-05", quote="Zirkuläre Wandverdickung des Colon sigmoideum"),
        dict(row="tumour_site", value="sigmoid", display="Sigmoid colon (discharge history)", date="2021-11-12", doc_id="p2-07", quote="Bei bekanntem Adenokarzinom des Colon sigmoideum"),
        dict(row="tumour_site", value="descendens", display="Descending colon (discharge diagnosis)", date="2021-11-12", doc_id="p2-07", quote="Kolonkarzinom des Colon descendens"),
        dict(row="tumour_size", value="4cm", display="Sigmoid wall thickening over 4 cm (CT)", date="2021-10-25", doc_id="p2-05", quote="auf einer Länge von 4 cm"),
        dict(row="lung_nodule", value="6mm", display="6 mm nodule, right upper lobe (CT)", date="2021-10-25", doc_id="p2-05", quote="Rundherd rechter Oberlappen, 6 mm"),
        dict(row="lung_nodule", value="5mm", display="About 5 mm nodule, right upper lobe (discharge letter)", date="2021-11-12", doc_id="p2-07", quote="Rundherd im rechten Oberlappen von etwa 5 mm"),
        dict(row="tumour_molecular", value="mss_kras_wt", display="MSS, KRAS wild-type, NRAS wild-type, BRAF V600E not mutated", date="2021-10-18", doc_id="p2-04", quote="Mikrosatellitenstabil (MSS). KRAS: Wildtyp. NRAS: Wildtyp. BRAF V600E: nicht mutiert."),
        dict(row="tumour_board_plan", value="sigmoid_resection", display="Tumour board recommends laparoscopic sigmoid resection", date="2021-11-12", doc_id="p2-07", quote="empfiehlt eine laparoskopische Sigmaresektion"),
        dict(row="tumour_board_plan", value="2021-12-06", display="Operation scheduled for 6 Dec 2021", date="2021-11-12", doc_id="p2-07", quote="für den 06.12.2021 terminisiert"),
        dict(row="tumour_board_plan", value="2021-12-06", display="Laparoscopic sigmoid resection on 6 Dec 2021", date="2021-11-12", doc_id="p2-07", quote="Laparoskopische Sigmaresektion am 06.12.2021"),
        dict(row="biopsy_date", value="2021-10-13", display="Sample taken 13 Oct 2021 (histology)", date="2021-10-13", doc_id="p2-04", quote="Entnahmedatum: 13.10.2021"),
        dict(row="biopsy_date", value="2021-10-14", display="Colonoscopy with biopsy on 14 Oct 2021 (discharge letter)", date="2021-10-14", doc_id="p2-07", quote="Koloskopie mit Biopsie am 14.10.2021"),
        # Age and dates
        dict(row="date_of_birth", value="1953-08-22", display="Born 22 Aug 1953", date="1953-08-22", doc_id="p2-01", quote="geb. 22.08.1953"),
        dict(row="date_of_birth", value="1953-08-22", display="Born 22 Aug 1953", date="1953-08-22", doc_id="p2-07", quote="geb. 22.08.1953"),
        dict(row="age_years", value="68", display="68 years old (cardiology letter)", date="2021-09-14", doc_id="p2-01", quote="Der 68-jährige Patient"),
        dict(row="age_years", value="68", display="68 years old (discharge examination)", date="2021-11-12", doc_id="p2-07", quote="68-jähriger Pat."),
        dict(row="age_years", value="72", display="72 years old (CT request)", date="2021-10-25", doc_id="p2-05", quote="72-jähriger Patient"),
        dict(row="admission_date", value="2021-11-08", display="Admitted 8 Nov 2021 (letter header)", date="2021-11-08", doc_id="p2-07", quote="Aufnahme am 08/11/2021"),
        dict(row="admission_date", value="2021-11-08", display="Admitted 8 Nov 2021 (narrative)", date="2021-11-08", doc_id="p2-07", quote="wurde am 08.11.2021 in reduziertem Allgemeinzustand"),
        dict(row="discharge_date", value="2021-11-12", display="Discharged 12 Nov 2021 (letter header)", date="2021-11-12", doc_id="p2-07", quote="Entlassen am 12/11/2021"),
        dict(row="discharge_date", value="2021-11-13", display="Went home 13 Nov 2021 (narrative)", date="2021-11-13", doc_id="p2-07", quote="wurde am 13.11.2021 in gutem Allgemeinzustand"),
        dict(row="planned_follow_up", value="gp_kidney_1w", display="Kidney values with the GP in 1 week", date="2021-11-12", doc_id="p2-07", quote="Kontrolle der Nierenwerte beim Hausarzt in 1 Woche"),
        dict(row="planned_follow_up", value="nephrology", display="Nephrology referral recommended", date="2021-11-12", doc_id="p2-07", quote="Nephrologische Vorstellung"),
        dict(row="planned_follow_up", value="lung_6m", display="Lung function check in 6 months", date="2021-10-05", doc_id="p2-03", quote="Kontrolle der Lungenfunktion in 6 Monaten"),
        dict(row="planned_follow_up", value="ct_3m", display="CT follow-up of the lung nodule in 3 months", date="2021-10-25", doc_id="p2-05", quote="CT-Kontrolle in 3 Monaten empfohlen"),
    ]
    return finalize_measurement_dates([_fact(docs, **item) for item in raw], docs)


def _passage(docs: dict[str, dict[str, Any]], doc_id: str, quote: str) -> dict[str, str]:
    if not quote_in_doc(quote, docs[doc_id]["text"]):
        raise RuntimeError(f"Alarm quote missing in {doc_id}: {quote}")
    return {"doc_id": doc_id, "quote_de": quote, "date": docs[doc_id]["date"]}


def build_contradictions(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Real clashes only. Dose changes and values on different days stay out."""
    contradictions = [
        {
            "id": "P2-BMI",
            "row": "bmi_stated",
            "title": "BMI vs height/weight (September 2021)",
            "summary": (
                "The cardiology letter states BMI 26.1 with 182 cm and 95 kg. "
                "95 / 1.82² ≈ 28.7. The November letter (181 cm, 91 kg, BMI 27.8) matches its own figures."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-01", "Größe: 182 cm"),
                _passage(docs, "p2-01", "Gewicht: 95 kg"),
                _passage(docs, "p2-01", "BMI: 26,1"),
            ],
        },
        {
            "id": "P2-EF",
            "row": "lvef_pct",
            "title": "Ejection fraction in the same echo report",
            "summary": (
                "The echo findings say EF 35% (severely reduced). The summary of the same "
                "report says EF 45% (moderately reduced). The discharge letter repeats 35%."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-02", "Hochgradig eingeschränkte systolische LV-Funktion (EF 35%)"),
                _passage(docs, "p2-02", "mittelgradig eingeschränkter LV-Funktion (EF 45%)"),
                _passage(docs, "p2-07", "eingeschränkte linksventrikuläre Funktion (EF 35%)"),
            ],
        },
        {
            "id": "P2-ALLERGY",
            "row": "allergy_penicillin",
            "title": "Penicillin allergy",
            "summary": (
                "The cardiology letter documents a penicillin allergy with a rash. "
                "The discharge letter says no allergies are known. "
                "The CT note of no known contrast allergy is a different statement."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-01", "Penicillin-Allergie (Exanthem)"),
                _passage(docs, "p2-07", "Allergien: keine bekannt"),
            ],
        },
        {
            "id": "P2-BIOPSY",
            "row": "biopsy_date",
            "title": "Biopsy date",
            "summary": (
                "Histology lists the sample date as 13 Oct 2021. "
                "The discharge letter dates the colonoscopy and biopsy to 14 Oct 2021."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-04", "Entnahmedatum: 13.10.2021"),
                _passage(docs, "p2-07", "Koloskopie mit Biopsie am 14.10.2021"),
            ],
        },
        {
            "id": "P2-SITE",
            "row": "tumour_site",
            "title": "Site of the colon carcinoma",
            "summary": (
                "Histology, CT, and the discharge history place the carcinoma in the sigmoid colon. "
                "The discharge diagnosis line says descending colon."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-04", "Zangenbiopsien, Colon sigmoideum, 28 cm ab ano"),
                _passage(docs, "p2-05", "Zirkuläre Wandverdickung des Colon sigmoideum"),
                _passage(docs, "p2-07", "Bei bekanntem Adenokarzinom des Colon sigmoideum"),
                _passage(docs, "p2-07", "Kolonkarzinom des Colon descendens"),
            ],
        },
        {
            "id": "P2-NSTAGE",
            "row": "tumour_tnm",
            "title": "Lymph-node stage",
            "summary": "CT staging says cT3 cN1 cM0. The discharge diagnosis says cT3 cN0 cM0.",
            "alarming": True,
            "passages": [
                _passage(docs, "p2-05", "cT3 cN1 cM0"),
                _passage(docs, "p2-07", "cT3 cN0 cM0"),
            ],
        },
        {
            "id": "P2-AGE",
            "row": "age_years",
            "title": "Stated age",
            "summary": (
                "Born 22 Aug 1953, so he is 68 in autumn 2021. "
                "The cardiology letter and the discharge examination say 68. The CT calls him 72."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-01", "geb. 22.08.1953"),
                _passage(docs, "p2-01", "Der 68-jährige Patient"),
                _passage(docs, "p2-07", "68-jähriger Pat."),
                _passage(docs, "p2-05", "72-jähriger Patient"),
            ],
        },
        {
            "id": "P2-SMOKING",
            "row": "smoking_status",
            "title": "Smoking status in one letter",
            "summary": (
                "The lung-function letter says he stopped smoking in 2010, "
                "then assesses COPD with active nicotine use."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-03", "Nikotinstopp 2010"),
                _passage(docs, "p2-03", "bei aktivem Nikotinabusus"),
            ],
        },
        {
            "id": "P2-DISCHARGE",
            "row": "discharge_date",
            "title": "Discharge date",
            "summary": (
                "The letter header says he was discharged on 12 Nov 2021. "
                "The narrative says he went home on 13 Nov 2021."
            ),
            "alarming": True,
            "passages": [
                _passage(docs, "p2-07", "Entlassen am 12/11/2021"),
                _passage(docs, "p2-07", "wurde am 13.11.2021 in gutem Allgemeinzustand"),
            ],
        },
    ]
    found = [item["id"] for item in contradictions]
    if found != EXPECTED_ALARMS:
        raise RuntimeError(f"Alarm ids changed: {found}")
    return contradictions


def enrich_with_llama(
    docs: dict[str, dict[str, Any]],
    seed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Keep a Llama fact only when its quote is in that letter and its row is already known."""
    if not ollama_available():
        return seed, "ollama_unavailable"

    allowed = {fact["row"] for fact in seed}
    chunks = []
    for doc_id, _filename, _short, _title, _date in PDF_DOCS:
        document = docs[doc_id]
        chunks.append(
            f"=== DOC {doc_id} date={document['date']} title={document['title']} ===\n{document['text']}"
        )
    prompt = (
        "Extract additional facts as a JSON array. Allowed row names: "
        + ", ".join(sorted(allowed))
        + "\n\n"
        + "\n\n".join(chunks)
    )
    try:
        response = call_ollama(prompt, system=EXTRACTION_SYSTEM, timeout=120)
    except Exception as exc:  # noqa: BLE001
        print(f"[matrix-0002] Ollama extraction failed: {exc}")
        return seed, f"ollama_error:{exc}"

    match = re.search(r"\[.*\]", response, re.DOTALL)
    if not match:
        print("[matrix-0002] Ollama returned no JSON array; using seed only")
        return seed, "ollama_no_json"
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        print("[matrix-0002] Ollama JSON parse failed; using seed only")
        return seed, "ollama_bad_json"

    seed_keys = {(fact["row"], fact["doc_id"], fact["quote_de"]) for fact in seed}
    merged = list(seed)
    verified = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("doc_id", ""))
        quote = str(item.get("quote_de", "")).strip()
        row = str(item.get("row", "")).strip()
        if doc_id not in docs or row not in allowed or not quote:
            continue
        if not quote_in_doc(quote, docs[doc_id]["text"]):
            continue
        key = (row, doc_id, quote)
        if key in seed_keys:
            continue
        seed_keys.add(key)
        verified += 1
        merged.append(
            {
                "row": row,
                "value": str(item.get("value", "")),
                "display": str(item.get("display") or item.get("value") or row),
                "unit": "",
                "date": str(item.get("date") or docs[doc_id]["date"]),
                "doc_id": doc_id,
                "quote_de": quote,
                "sentence_id": f"{doc_id}:{abs(hash(quote)) % 10_000_000}",
                "source": "llama",
            }
        )
    return finalize_measurement_dates(merged, docs), f"ollama_ok:{verified}_verified"


def build_matrix(force: bool = False) -> dict[str, Any]:
    if CACHE_PATH.name != "matrix-0000-0002.json":
        raise RuntimeError(f"Refusing to write {CACHE_PATH.name}")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_PATH.exists() and not force:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    folder = patients.ROOT / patients.PATIENTS["0000-0002"]["folder"]
    print(f"[matrix-0002] Reading PDFs in {folder.name}...")
    docs = pdf_extract.load_pdf_documents(folder, PDF_DOCS)
    print("[matrix-0002] Checking seed quotes...")
    seed = seed_facts(docs)
    print(f"[matrix-0002] Seed facts kept: {len(seed)}")
    facts, llama_status = enrich_with_llama(docs, seed)
    print(f"[matrix-0002] Llama status: {llama_status}; facts total: {len(facts)}")
    contradictions = build_contradictions(docs)
    print(f"[matrix-0002] Alarms: {[item['id'] for item in contradictions]}")

    payload = {
        "status": "ready",
        "patient_id": "0000-0002",
        "patient_key": "0000-0002|1953-08-22",
        "as_of": "2021-11-12",
        "llama_status": llama_status,
        "model": OLLAMA_MODEL,
        "facts": facts,
        "contradictions": contradictions,
        "documents": {
            doc_id: {
                "id": doc_id,
                "title": document["title"],
                "date": document["date"],
                "short": document["short"],
                "filename": document["filename"],
                "text": document["text"],
            }
            for doc_id, document in docs.items()
        },
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[matrix-0002] Cached to {CACHE_PATH}")
    return payload


if __name__ == "__main__":
    build_matrix(force=True)
