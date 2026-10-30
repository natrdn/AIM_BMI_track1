"""Hard-coded role/task catalogue for the five scored situations and extras."""

SITUATIONS = {
    "1": {
        "id": "1",
        "title": "Pre-operative anaesthesia check",
        "role": "Anaesthetist",
        "description": (
            "You are the anaesthetist. She is scheduled for a quadrantectomy "
            "(partial removal of the breast) with intraoperative radiotherapy on 16 May 2016."
        ),
        "answers": [
            {
                "id": "1.1",
                "question": "Which antithrombotic drug (blood thinner) does she take and at what dose?",
                "rows": ["aspirin_100mg"],
                "column_rule": "latest",
                "answer": "Thrombo ASS (acetylsalicylic acid) 100 mg, once in the morning (1-0-0).",
                "preferred_docs": ["12340011", "12340012", "12340018"],
            },
            {
                "id": "1.2",
                "question": "Which allergy is documented?",
                "rows": ["allergy_contrast"],
                "column_rule": "all",
                "answer": "Contrast media allergy, with nausea, dizziness and vomiting.",
                "preferred_docs": ["12340012", "12340018"],
            },
            {
                "id": "1.3",
                "question": (
                    "What was the last documented left-ventricular ejection fraction "
                    "(how much blood the heart pumps out with each beat)?"
                ),
                "rows": ["lvef_pct"],
                "column_rule": "all",
                "answer": "60%, normal systolic function, from the echocardiography in June 2015.",
                "preferred_docs": ["12340012"],
            },
        ],
        "extra_rows": [
            "osa",
            "diabetes",
            "hypertension",
            "metformin_1000mg",
            "candesartan_16mg",
        ],
        "not_documented": [
            "Airway assessment",
            "Kidney function",
            "Prior anaesthesia complications",
        ],
        "hidden_rows": ["receptors_ki67", "tumour_tnm", "tumour_histology"],
        "contradiction_ids": ["C1", "C2", "C3", "C4", "C5"],
    },
    "2": {
        "id": "2",
        "title": "Surgery planning after the tumour board, April 2016",
        "role": "Surgeon",
        "description": "You are the surgeon planning her operation after the tumour board.",
        "answers": [
            {
                "id": "2.1",
                "question": "What is the histology (tissue type) and the TNM stage (tumour size, lymph nodes, spread)?",
                "rows": ["tumour_histology", "tumour_tnm"],
                "column_rule": "latest",
                "answer": (
                    "Invasive ductal carcinoma of the left breast, T2 N0 M0 V0 G2, "
                    "from the core biopsy in April 2016."
                ),
                "preferred_docs": ["12340016", "12340018"],
            },
            {
                "id": "2.2",
                "question": "What is the receptor status and the Ki-67 rate (how fast the tumour cells divide)?",
                "rows": ["receptors_ki67"],
                "column_rule": "latest",
                "answer": (
                    "Oestrogen receptor positive (100%, Allred 8), progesterone receptor positive "
                    "(70%, Allred 7), HER2 negative. Ki-67 20%."
                ),
                "preferred_docs": ["12340016"],
            },
            {
                "id": "2.3",
                "question": "What did the tumour board recommend and when is it scheduled?",
                "rows": ["tumour_board_plan"],
                "column_rule": "latest",
                "answer": "Quadrantectomy with intraoperative radiotherapy (IORT), on 16 May 2016.",
                "preferred_docs": ["12340018"],
            },
        ],
        "extra_rows": ["axillary_nodes", "tumour_size"],
        "not_documented": [],
        "hidden_rows": [],
        "contradiction_ids": ["C4", "C5"],
    },
    "3": {
        "id": "3",
        "title": "Diabetes review at the GP",
        "role": "GP",
        "description": "You are her general practitioner (GP), reviewing her diabetes in spring 2016.",
        "answers": [
            {
                "id": "3.1",
                "question": "Which glucose-lowering drugs does she take and at what doses?",
                "rows": ["metformin_1000mg", "pioglitazone_30mg", "exenatide_5ug"],
                "column_rule": "latest",
                "answer": (
                    "Metformin (Glucophage) 1000 mg 1-1-1, pioglitazone (Actos) 30 mg 0-1-0, "
                    "exenatide (Byetta) 5 µg subcutaneous 1-0-1."
                ),
                "preferred_docs": ["12340012", "12340018"],
            },
            {
                "id": "3.2",
                "question": "What is her latest HbA1c and from when?",
                "rows": ["hba1c_pct"],
                "column_rule": "latest",
                "answer": "6.4%, from June 2015. No later value is documented.",
                "preferred_docs": ["12340011", "12340012"],
                "append_if_stale": "No later value is documented.",
            },
            {
                "id": "3.3",
                "question": "How did her weight change between June 2015 and April 2016?",
                "rows": ["weight_kg"],
                "column_rule": "all",
                "answer": (
                    "78 kg in June 2015, 67 kg on 4 April 2016 and 66 kg during her hospital stay "
                    "in April 2016. She lost about 12 kg."
                ),
                "preferred_docs": ["12340012", "12340014", "12340018"],
            },
        ],
        "extra_rows": ["bmi_stated", "bmi_from_height_weight"],
        "not_documented": ["Any HbA1c after June 2015"],
        "hidden_rows": [],
        "contradiction_ids": ["C2", "C3"],
    },
    "4": {
        "id": "4",
        "title": "Emergency department at night",
        "role": "Emergency physician",
        "description": (
            "You are the emergency physician on night duty. She arrives at 02:00 with dizziness "
            "and blurred vision in the left eye."
        ),
        "answers": [
            {
                "id": "4.1",
                "question": "Has this happened before and what was found to be the cause?",
                "rows": ["prior_episode", "carotid_stenosis_side"],
                "column_rule": "all",
                "answer": (
                    "Yes. In June 2015 she had a hypertensive crisis with dizziness and brief vision "
                    "loss in the left eye (amaurosis fugax). It was put down to a 60% stenosis of the "
                    "left internal carotid artery."
                ),
                "preferred_docs": ["12340011", "12340012", "12340008"],
            },
            {
                "id": "4.2",
                "question": (
                    "Is anything documented that matters before giving iodinated contrast "
                    "(the dye for a CT scan of the blood vessels)?"
                ),
                "rows": ["allergy_contrast", "prior_ct_type", "metformin_1000mg"],
                "column_rule": "latest",
                "answer": (
                    "Yes. She has a contrast media allergy (nausea, dizziness, vomiting). "
                    "Her head CT in 2015 was done without contrast for that reason. "
                    "She also takes metformin (Glucophage 1000 mg 1-1-1). "
                    "Her kidney function is not documented."
                ),
                "preferred_docs": ["12340012", "12340018"],
                "force_not_documented": ["Kidney function"],
            },
            {
                "id": "4.3",
                "question": "Which antihypertensive (blood pressure drug) does she take and at what dose?",
                "rows": ["candesartan_16mg"],
                "column_rule": "latest",
                "answer": "Candesartan (Blopress) 16 mg 1-0-1, as of April 2016.",
                "preferred_docs": ["12340018"],
            },
        ],
        "extra_rows": [],
        "not_documented": ["Kidney function"],
        "hidden_rows": [],
        "contradiction_ids": ["C1"],
    },
    "5": {
        "id": "5",
        "title": "Open follow-ups from the 2015 hospital stay",
        "role": "GP",
        "description": (
            "You are her GP. You check which follow-ups from her June 2015 hospital stay are still open."
        ),
        "answers": [
            {
                "id": "5.1",
                "question": "Which follow-ups were recommended at discharge in June 2015?",
                "rows": ["follow_up_2015"],
                "column_rule": "all",
                "answer": (
                    "A carotid duplex ultrasound in two months, regular eye check-ups and regular "
                    "blood pressure checks with medication adjustment by the GP."
                ),
                "preferred_docs": ["12340011", "12340012"],
            },
            {
                "id": "5.2",
                "question": "Is there a record that the follow-up carotid ultrasound took place?",
                "rows": ["follow_up_carotid_done"],
                "column_rule": "after_plan",
                "answer": "No. None of the eight documents records it.",
                "preferred_docs": [],
                "expect_empty": True,
            },
            {
                "id": "5.3",
                "question": "On which side is the carotid stenosis?",
                "rows": ["carotid_stenosis_side"],
                "column_rule": "all",
                "answer": "Left. Up to 60% stenosis of the left internal carotid artery.",
                "preferred_docs": ["12340008", "12340011", "12340012"],
            },
        ],
        "extra_rows": [],
        "not_documented": ["Follow-up carotid ultrasound after June 2015"],
        "hidden_rows": [],
        "contradiction_ids": ["C1"],
    },
    "6": {
        "id": "6",
        "title": "Radiotherapy planning for IORT",
        "role": "Radiation oncologist",
        "description": (
            "You are the radiation oncologist preparing the IORT planned with the "
            "quadrantectomy on 16 May 2016."
        ),
        "answers": [
            {
                "id": "6.1",
                "question": "What are the tumour's size, histology and receptor status?",
                "rows": ["tumour_histology", "tumour_tnm", "receptors_ki67", "tumour_size"],
                "column_rule": "latest",
                "answer": (
                    "Invasive ductal carcinoma, left breast, T2 N0 M0 V0 G2, 3 x 1.5 cm on ultrasound "
                    "(3 cm per external mammography); ER pos, PR pos, HER2 neg, Ki-67 20%."
                ),
                "preferred_docs": ["12340016", "12340018", "12340014"],
            },
            {
                "id": "6.2",
                "question": "Is any autoimmune or connective tissue disease documented?",
                "rows": ["sle"],
                "column_rule": "all",
                "answer": "Yes: systemic lupus erythematosus (SLE).",
                "preferred_docs": ["12340012", "12340014", "12340018"],
            },
            {
                "id": "6.3",
                "question": "Has she had prior radiotherapy to the breast or chest?",
                "rows": ["prior_radiotherapy"],
                "column_rule": "all",
                "answer": "Not documented.",
                "preferred_docs": [],
                "expect_empty": True,
            },
        ],
        "extra_rows": [],
        "not_documented": ["Prior radiotherapy to the breast or chest"],
        "hidden_rows": [],
        "contradiction_ids": ["C4", "C5"],
    },
}

# Rows Llama may choose for a free-text situation
AVAILABLE_ROWS = [
    "date_of_birth",
    "allergy_contrast",
    "aspirin_100mg",
    "metformin_1000mg",
    "pioglitazone_30mg",
    "exenatide_5ug",
    "candesartan_16mg",
    "lvef_pct",
    "hba1c_pct",
    "blood_pressure_mmHg",
    "weight_kg",
    "height_cm",
    "bmi_stated",
    "carotid_stenosis_side",
    "prior_episode",
    "prior_ct_type",
    "tumour_histology",
    "tumour_tnm",
    "receptors_ki67",
    "tumour_size",
    "tumour_board_plan",
    "axillary_nodes",
    "follow_up_2015",
    "sle",
    "osa",
    "diabetes",
    "hypertension",
    "biopsy_date",
    "april_2016_admission",
]

ROLE_KEYWORDS = {
    "anaesthet": "1",
    "anesthet": "1",
    "pre-op": "1",
    "preoperative": "1",
    "pre-operative": "1",
    "surgeon": "2",
    "surgery": "2",
    "tumour board": "2",
    "tumor board": "2",
    "diabetes": "3",
    "gp": "3",
    "general practitioner": "3",
    "emergency": "4",
    "ed physician": "4",
    "dizziness": "4",
    "follow-up": "5",
    "follow up": "5",
    "carotid": "5",
    "radiotherapy": "6",
    "radiation": "6",
    "iort": "6",
}
