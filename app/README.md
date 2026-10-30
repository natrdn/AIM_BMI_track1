# Situation card (Track 1)

One screen for one clinical situation. The clinician picks a patient, then a role and task. The page shows only the facts that job needs, each linked to a German sentence in that patient's letters. Missing facts say **not documented**. Real clashes show in red with every passage. Anna Musterfrau remains the scored chart.

## Architecture

```
Browser (app/index.html)
    │
    ▼
server.py  ── one patient id per request
    │
    ├── patients.py          (registry only: id, name, cache file)
    ├── cache/matrix.json    (Anna Musterfrau, 0000-0001)
    ├── cache/matrix-0000-0002.json
    ├── data/patient-0000-0001/documents/*.json
    ├── pdf_extract.py       (stdlib text from the 0000-0002 PDFs)
    └── Ollama  (Llama 3.1 at localhost:11434)
```

1. **One matrix per patient.** The typed name or chart id chooses a patient. Facts are never merged, and building one chart does not rewrite another cache. Anna stays in `cache/matrix.json`. Beispielpatient (0000-0002) is built only into `cache/matrix-0000-0002.json` from the PDF folder `07_Stationaerer_Patientenbrief_2021-11-12 (1)`.
2. **Matrix 1** — On first run the server normalises Anna’s eight letters (`<BR>` → newlines), builds a quote-verified fact table, and asks **Llama 3.1** (via Ollama) to enrich it. A fact is kept only if its German quote appears verbatim in that letter. The PDF chart uses the same rule on text extracted from the ReportLab letters.
3. **Matrix 3** — Hard rules mark Anna’s five alarms (C1–C5) and, separately, the clashes in the 2021 letters. Fewer allergy symptoms than a fuller description is **not** alarming. Weight change and dose change over time are **not** alarming.
4. **Matrix 2** — `catalogue.py` maps each scored situation to Anna’s rows. `catalogue_0002.py` maps the same buttons onto his rows. Filtering a cache is instant (no second model call). A typed situation the catalogue does not know triggers a short Llama call that may **only select rows already in that patient’s cache**.

The chart name or id sits in the top bar. It stays closed until a role is chosen. Tasks for that role are listed under **Purpose**. A typed purpose uses **Open brief**.

Llama decides wording and row mapping. The card never shows a sentence that failed the quote check, and it never adds advice that is not in a letter.

## Requirements

- Python 3.10+ (standard library only)
- [Ollama](https://ollama.com) with Llama 3.1
- Local copy of the hackathon `data/` folder (not published)

```bash
ollama pull llama3.1
```

Optional env vars:

- `OLLAMA_URL` — default `http://localhost:11434`
- `OLLAMA_MODEL` — default `llama3.1`

## Run

From the repository root (where `server.py` and `data/` live):

```bash
python3 server.py
```

The server listens on every network interface, port 8765. On this machine open **http://127.0.0.1:8765/**

On startup it prints a Share URL, such as `http://192.168.1.42:8765/`. Other computers on the same network open that address. If macOS asks to allow incoming connections for Python, allow it.

Wait while the brief is loading (first build calls Llama and writes `cache/matrix.json`). Choose a role, open a chart, then choose a task under **Purpose**, or describe the purpose and choose **Open brief**. Type **Beispielpatient** (or `0000-0002`) in the chart field and open that chart to read the 2021 PDF letters instead. That chart is cached separately as `cache/matrix-0000-0002.json`.

To rebuild one chart:

```text
GET http://127.0.0.1:8765/api/rebuild?patient=0000-0001
GET http://127.0.0.1:8765/api/rebuild?patient=0000-0002
```

If Ollama is down, the app still starts from the quote-verified seed so the five scored situations work; free-text mapping falls back to a general row subset.

## Hosting

GitHub can store this repository. It cannot serve the brief. GitHub Pages only publishes static files, and every chart is loaded by `server.py`.

The public copy is on Fly.io: https://aim-bmi-track1-brief.fly.dev/

That machine includes the letters and the cache. It sleeps when idle and wakes on the next visit. Llama is not hosted there. Ollama stays on a local machine only, at `localhost:11434`. On the Fly copy the five scored situations still open from the quote-checked cache. A typed visit does not call Llama, so that brief stays thinner than one opened on a machine where Ollama is running.

`Dockerfile` and `fly.toml` describe that deploy. The server listens on the `PORT` Fly sets, and on 8765 when you start it locally.

## Submission note

Keep `data/` and `cache/` out of the public repository (already listed in `.gitignore`). Clone the challenge data separately when you run the demo.
