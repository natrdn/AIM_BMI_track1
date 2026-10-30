"""Role overlay for patient 0000-0002.

The situation buttons stay the ones in catalogue.py. This file only chooses
his rows, the card description, and which of his alarms belong on that role.
Answer sentences are built from his fact displays.
"""

ROW_GAPS = {
    "receptors_ki67": "Receptor status and Ki-67",
    "metformin_1000mg": "Metformin",
    "pioglitazone_30mg": "Pioglitazone",
    "exenatide_5ug": "Exenatide",
    "hba1c_pct": "HbA1c",
    "prior_episode": "A prior episode of this kind",
    "carotid_stenosis_side": "Side of a carotid stenosis",
    "follow_up_2015": "Follow-ups recommended in June 2015",
    "follow_up_carotid_done": "A completed follow-up carotid ultrasound",
    "sle": "Autoimmune or connective tissue disease",
    "prior_radiotherapy": "Prior radiotherapy",
    "aspirin_100mg": "Acetylsalicylic acid",
    "candesartan_16mg": "Candesartan",
}

SITUATIONS = {
    "1": {
        "description": (
            "You are the anaesthetist. He is scheduled for a laparoscopic "
            "sigmoid resection on 6 December 2021."
        ),
        "answers": [
            {"id": "1.1", "rows": ["rivaroxaban"], "column_rule": "all"},
            {"id": "1.2", "rows": ["allergy_penicillin", "allergy_none"], "column_rule": "all"},
            {"id": "1.3", "rows": ["lvef_pct"], "column_rule": "all"},
        ],
        "extra_rows": [
            "copd",
            "smoking_status",
            "ckd",
            "egfr",
            "creatinine",
            "haemoglobin",
            "hypertension",
            "heart_failure",
            "bisoprolol_5mg",
            "ramipril_5mg",
            "tiotropium",
        ],
        "not_documented": [
            "Airway assessment",
            "Prior anaesthesia complications",
        ],
        "contradiction_ids": ["P2-EF", "P2-ALLERGY", "P2-BMI", "P2-AGE", "P2-SMOKING"],
    },
    "2": {
        "title": "Surgery planning after the tumour board",
        "description": (
            "You are the surgeon planning his operation after the tumour board "
            "on 10 November 2021."
        ),
        "answers": [
            {"id": "2.1", "rows": ["tumour_histology", "tumour_tnm"], "column_rule": "all"},
            {"id": "2.2", "rows": ["receptors_ki67"], "column_rule": "latest"},
            {"id": "2.3", "rows": ["tumour_board_plan"], "column_rule": "all"},
        ],
        "extra_rows": ["tumour_site", "tumour_size", "tumour_molecular", "biopsy_date"],
        "not_documented": ["Receptor status and Ki-67"],
        "contradiction_ids": ["P2-SITE", "P2-NSTAGE", "P2-BIOPSY", "P2-DISCHARGE"],
    },
    "3": {
        "description": "You are his general practitioner, reviewing the chart in November 2021.",
        "answers": [
            {
                "id": "3.1",
                "rows": ["metformin_1000mg", "pioglitazone_30mg", "exenatide_5ug"],
                "column_rule": "latest",
            },
            {"id": "3.2", "rows": ["hba1c_pct"], "column_rule": "latest"},
            {"id": "3.3", "rows": ["weight_kg"], "column_rule": "all"},
        ],
        "extra_rows": ["bmi_stated", "bmi_from_height_weight", "height_cm"],
        "not_documented": ["Glucose-lowering drugs", "HbA1c"],
        "contradiction_ids": ["P2-BMI"],
    },
    "4": {
        "description": (
            "You are the emergency physician. These letters are what you have "
            "before any decision about iodinated contrast."
        ),
        "answers": [
            {"id": "4.1", "rows": ["prior_episode", "carotid_stenosis_side"], "column_rule": "all"},
            {
                "id": "4.2",
                "rows": ["allergy_contrast", "allergy_penicillin", "creatinine", "egfr"],
                "column_rule": "all",
            },
            {"id": "4.3", "rows": ["ramipril_5mg"], "column_rule": "all"},
        ],
        "extra_rows": ["blood_pressure_mmHg", "heart_failure", "allergy_none"],
        "not_documented": [
            "A prior episode of dizziness or visual loss",
            "Carotid stenosis",
        ],
        "contradiction_ids": ["P2-ALLERGY", "P2-AGE"],
    },
    "5": {
        "description": (
            "You are his GP, checking which follow-ups from a June 2015 hospital "
            "stay are still open. His letters start in September 2021."
        ),
        "answers": [
            {"id": "5.1", "rows": ["follow_up_2015"], "column_rule": "all"},
            {"id": "5.2", "rows": ["follow_up_carotid_done"], "column_rule": "all"},
            {"id": "5.3", "rows": ["carotid_stenosis_side"], "column_rule": "all"},
        ],
        "extra_rows": ["planned_follow_up"],
        "not_documented": [
            "Follow-ups from a June 2015 hospital stay",
            "A follow-up carotid ultrasound",
            "Side of a carotid stenosis",
        ],
        "contradiction_ids": [],
    },
    "6": {
        "title": "Radiotherapy planning",
        "description": (
            "You are the radiation oncologist reviewing the colon carcinoma "
            "described in his letters."
        ),
        "answers": [
            {
                "id": "6.1",
                "rows": ["tumour_histology", "tumour_tnm", "tumour_size"],
                "column_rule": "all",
            },
            {"id": "6.2", "rows": ["sle"], "column_rule": "all"},
            {"id": "6.3", "rows": ["prior_radiotherapy"], "column_rule": "all"},
        ],
        "extra_rows": ["tumour_molecular", "tumour_site", "lung_nodule"],
        "not_documented": [
            "Receptor status and Ki-67",
            "Autoimmune or connective tissue disease",
            "Prior radiotherapy",
        ],
        "contradiction_ids": ["P2-SITE", "P2-NSTAGE", "P2-BIOPSY"],
    },
}
