# AIM BMI Track 1 - clinical situation card

One screen for one clinical role and task. The clinician enters who they are and what they are about to do. The page shows only the patient facts that job needs. Each fact links to the German sentence it comes from. A fact the task needs and the letters do not contain is marked **not documented**. Real clashes are listed with every passage.

Anna Musterfrau (0000-0001) is the scored chart. Present-tense facts are as of 15 April 2016.

## Architecture

    Browser (app/index.html)
        |
        v
    server.py
        |
        +-- patients.py          chart id, name, cache file
        +-- cache/matrix.json    built locally on first run
        +-- data/                hackathon letters, kept on your machine
        +-- Ollama               Llama 3.1 at localhost:11434

The server keeps one cache per patient. Facts from one chart are never merged into another.

On first run it normalises the letters and builds a fact table. A fact is kept only when its German quote appears in that letter.

catalogue.py maps the five scored situations onto those rows. Opening one of them does not call the model again.

A typed situation the catalogue does not know sends a short Llama 3.1 call. That call may only select rows already in the cache.

Llama chooses wording. The screen shows a sentence only after the quote check passes.

## Run

Requirements: Python 3.10+ (standard library only) and Ollama with Llama 3.1.

    ollama pull llama3.1

Place the hackathon data/ directory beside server.py. This repository does not contain it.

    python3 server.py

Open http://127.0.0.1:8765/

Optional environment variables: OLLAMA_URL (default http://localhost:11434) and OLLAMA_MODEL (default llama3.1).

The first start writes cache/matrix.json. Later starts load that file. If Ollama is down, the five scored situations still open from the quote-checked cache.

## Metrics

Measured on the five situations in cases/.

| Metric | Result | Target |
|---|---|---|
| Correct answers |  | 15 of 15 |
| Traceability |  | 100% |
| Invented facts |  | 0 |
| Contradictions |  | 5 or more |
| Load time |  | Under 10 s |
