#!/usr/bin/env python3
"""Local situation-card server: Matrix 1/3 cache + hard-coded catalogue + Llama free text."""

from __future__ import annotations

import json
import re
import socket
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import catalogue
import catalogue_0002
import matrix as matrix_mod
import matrix_0002
import patients

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
HOST = "0.0.0.0"
PORT = 8765

STATE: dict[str, Any] = {
    "matrices": {},
    "building": {},
    "error": {},
}


def build_cache_async(patient_id: str, force: bool = False) -> None:
    """Build one patient's cache. Other patients' files are not opened for writing."""
    if patient_id not in patients.PATIENTS:
        raise KeyError(patient_id)
    if STATE["building"].get(patient_id):
        return
    STATE["building"][patient_id] = True
    STATE["error"][patient_id] = None
    if force:
        STATE["matrices"][patient_id] = None

    def worker() -> None:
        try:
            if patient_id == "0000-0001":
                STATE["matrices"][patient_id] = matrix_mod.build_matrix(force=force)
            elif patient_id == "0000-0002":
                STATE["matrices"][patient_id] = matrix_0002.build_matrix(force=force)
            else:
                raise RuntimeError(f"No matrix builder for {patient_id}")
            print(f"[server] Matrix ready for {patient_id}.")
        except Exception as exc:  # noqa: BLE001
            STATE["error"][patient_id] = str(exc)
            traceback.print_exc()
            print(f"[server] Matrix build failed for {patient_id}: {exc}")
        finally:
            STATE["building"][patient_id] = False

    threading.Thread(target=worker, daemon=True).start()


def load_cache(patient_id: str) -> bool:
    path = patients.cache_path(patient_id)
    if not path.is_file():
        return False
    try:
        STATE["matrices"][patient_id] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    print(f"[server] Loaded cache for {patient_id}.")
    return True


def ensure_matrix(patient_id: str) -> dict[str, Any] | None:
    current = STATE["matrices"].get(patient_id)
    if current is not None and current.get("status") == "ready":
        return current
    if load_cache(patient_id):
        return STATE["matrices"][patient_id]
    if not STATE["building"].get(patient_id) and not STATE["error"].get(patient_id):
        build_cache_async(patient_id, force=False)
    return STATE["matrices"].get(patient_id)


def resolve_patient_id(parsed: Any, body: dict[str, Any] | None = None) -> str | None:
    query = parse_qs(parsed.query)
    patient_id = (query.get("patient") or [None])[0]
    if body and body.get("patient"):
        patient_id = str(body["patient"])
    if not patient_id:
        patient_id = patients.DEFAULT_PATIENT_ID
    if patient_id not in patients.PATIENTS:
        return None
    return patient_id


def match_situation_by_keywords(text: str) -> str | None:
    lower = text.lower()
    for keyword, sit_id in catalogue.ROLE_KEYWORDS.items():
        if keyword in lower:
            return sit_id
    return None


def extract_row_names(raw: Any, available: set[str]) -> list[str]:
    """Keep row names Llama returned, including when it wraps each name in an object."""
    found: list[str] = []

    def add(name: str) -> None:
        cleaned = name.strip().strip('"').strip("'")
        if cleaned in available and cleaned not in found:
            found.append(cleaned)

    def walk(node: Any) -> None:
        if isinstance(node, str):
            add(node)
            return
        if isinstance(node, dict):
            for key, value in node.items():
                add(str(key))
                walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(raw)
    return found


def parse_llama_json(response: str) -> dict[str, Any]:
    start = response.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    data, _ = json.JSONDecoder().raw_decode(response[start:])
    if not isinstance(data, dict):
        raise ValueError("JSON was not an object")
    return data


def keep_rows_that_answer(question: str, rows: list[str], hints: dict[str, str]) -> dict[str, Any]:
    """Second Llama check: drop rows that do not state the answer."""
    if not rows:
        return {"rows": [], "not_documented": []}
    candidates = [{"row": row, "example": hints.get(row, "")} for row in rows]
    system = (
        "You keep only the candidate rows that directly answer the question. "
        'Return ONLY JSON: {"rows":["row_name"],"not_documented":["what is missing"]}. '
        "rows must be a JSON array of strings copied from the candidates. "
        "Keep a row only when its example states the thing asked. "
        "Do not keep a different measurement. "
        "Height, weight, and BMI do not answer age. Allergy does not answer blood pressure. "
        "If none of the candidates answer, rows must be an empty array."
    )
    prompt = (
        f"Question:\n{question}\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    response = matrix_mod.call_ollama(prompt, system=system, timeout=90)
    data = parse_llama_json(response)
    kept = extract_row_names(data.get("rows", []), set(rows))
    missing = [item for item in data.get("not_documented") or [] if isinstance(item, str)]
    return {"rows": kept, "not_documented": missing}


def llama_select_rows(
    text: str,
    matrix: dict[str, Any],
    allowed_rows: list[str] | None = None,
) -> dict[str, Any]:
    """Llama picks rows, then a second call drops any row that does not answer."""
    row_summaries: dict[str, list[str]] = {}
    for fact in matrix["facts"]:
        row_summaries.setdefault(fact["row"], []).append(fact["display"])
    allow = set(catalogue.AVAILABLE_ROWS) if allowed_rows is None else set(allowed_rows)
    available = sorted(allow & set(row_summaries.keys()))
    available_set = set(available)
    hints = {row: row_summaries[row][0] for row in available}
    system = (
        "You choose which patient-matrix rows answer a clinician's question. "
        'Return ONLY JSON: {"role":"...","task":"...","rows":["row_name"],"not_documented":[]}. '
        "rows must be a JSON array of strings copied exactly from the available names. "
        "Do not wrap a row in an object. "
        "Return only rows whose example states the answer. Usually one row. "
        "If no row states the answer, return an empty rows array and name the gap in not_documented."
    )
    prompt = (
        f"Question:\n{text}\n\n"
        f"Available rows and one example value:\n{json.dumps(hints, ensure_ascii=False)}"
    )
    if not matrix_mod.ollama_available():
        return {
            "role": "general",
            "task": "free text",
            "rows": [],
            "not_documented": [],
            "note": "Ollama is not running, so no rows were selected.",
        }
    try:
        response = matrix_mod.call_ollama(prompt, system=system, timeout=90)
        data = parse_llama_json(response)
        proposed = extract_row_names(data.get("rows", []), available_set)
        checked = keep_rows_that_answer(text, proposed, hints)
        rows = checked["rows"]
        return {
            "role": data.get("role") or "general",
            "task": data.get("task") or "free text",
            "rows": rows,
            "not_documented": [],
            "note": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "role": "general",
            "task": "free text",
            "rows": [],
            "not_documented": [],
            "note": f"Llama mapping failed ({exc}). No rows were added.",
        }


def render_situation(sit: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    answers = []
    for item in sit["answers"]:
        expect_empty = item.get("expect_empty", False)
        facts = matrix_mod.facts_for_rows(
            matrix,
            item["rows"],
            column_rule=item.get("column_rule", "latest"),
            preferred_docs=item.get("preferred_docs"),
        )
        if expect_empty or not facts:
            answers.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "answer": item.get("answer") or "Not documented.",
                    "status": "not_documented",
                    "sources": [],
                }
            )
            continue
        sources = sources_from(facts)
        answers.append(
            {
                "id": item["id"],
                "question": item["question"],
                "answer": item["answer"],
                "status": "documented",
                "sources": sources,
            }
        )

    extra = []
    for row in sit.get("extra_rows", []):
        if row in sit.get("hidden_rows", []):
            continue
        facts = matrix_mod.facts_for_rows(matrix, [row], column_rule="latest")
        if not facts:
            continue
        extra.append(
            {
                "row": row,
                "display": facts[0]["display"],
                "sources": sources_from(facts),
            }
        )

    wanted = set(sit.get("contradiction_ids") or [])
    contradictions = contradictions_for_card(
        matrix, [c for c in matrix["contradictions"] if c["id"] in wanted]
    )

    return {
        "situation_id": sit["id"],
        "title": sit["title"],
        "role": sit["role"],
        "description": sit["description"],
        "answers": answers,
        "extra_facts": extra,
        "not_documented": sit.get("not_documented") or [],
        "contradictions": contradictions,
        "as_of": matrix.get("as_of"),
    }


def render_free_text(text: str, matrix: dict[str, Any]) -> dict[str, Any]:
    matched = match_situation_by_keywords(text)
    if matched and matched in catalogue.SITUATIONS:
        card = render_situation(catalogue.SITUATIONS[matched], matrix)
        card["matched_preset"] = matched
        card["input"] = text
        return card

    selection = llama_select_rows(text, matrix)
    facts_by_row = {}
    for row in selection["rows"]:
        facts = matrix_mod.facts_for_rows(matrix, [row], column_rule="all")
        if facts:
            facts_by_row[row] = facts

    answers = []
    for idx, row in enumerate(selection["rows"], start=1):
        facts = facts_by_row.get(row, [])
        if not facts:
            answers.append(
                {
                    "id": f"free.{idx}",
                    "question": row,
                    "answer": "Not documented.",
                    "status": "not_documented",
                    "sources": [],
                }
            )
            continue
        answers.append(
            {
                "id": f"free.{idx}",
                "question": row.replace("_", " "),
                "answer": "; ".join(dict.fromkeys(f["display"] for f in facts)),
                "status": "documented",
                "sources": sources_from(facts),
            }
        )

    note = selection.get("note")
    if not answers and not note:
        answers.append(
            {
                "id": "free.1",
                "question": text,
                "answer": "not documented",
                "status": "not_documented",
                "sources": [],
            }
        )

    # Attach alarms that touch any selected row
    selected_rows = set(selection["rows"])
    contradictions = contradictions_for_card(
        matrix, [c for c in matrix["contradictions"] if c.get("row") in selected_rows]
    )

    return {
        "situation_id": "free",
        "title": "Custom situation",
        "role": selection.get("role") or "general",
        "description": text,
        "answers": answers,
        "extra_facts": [],
        "not_documented": selection.get("not_documented") or [],
        "contradictions": contradictions,
        "as_of": matrix.get("as_of"),
        "note": note,
        "input": text,
    }


def fact_source(fact: dict[str, Any]) -> dict[str, Any]:
    """One citation. A date mismatch is the letter date against the date in the text."""
    in_text = fact.get("date_of_measurement") or fact["date"]
    source = {
        "doc_id": fact["doc_id"],
        "date": in_text,
        "date_of_measurement": in_text,
        "document_date": fact.get("document_date") or "",
        "quote_de": fact["quote_de"],
        "display": fact["display"],
        "row": fact["row"],
    }
    mismatch = fact.get("date_mismatch")
    if mismatch:
        source["date_mismatch"] = mismatch
    return source


def sources_from(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    sources: list[dict[str, Any]] = []
    for fact in facts:
        key = (fact["doc_id"], fact["quote_de"])
        if key in seen:
            continue
        seen.add(key)
        sources.append(fact_source(fact))
    return sources


def contradictions_for_card(matrix: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy alarms and attach a date mismatch when the passage's text date differs from the letter."""
    index = {
        (fact["doc_id"], fact["quote_de"]): fact["date_mismatch"]
        for fact in matrix.get("facts") or []
        if fact.get("date_mismatch")
    }
    copied = []
    for item in items:
        alarm = dict(item)
        passages = []
        for passage in item.get("passages") or []:
            passage = dict(passage)
            mismatch = index.get((passage.get("doc_id"), passage.get("quote_de")))
            if mismatch:
                passage["date_mismatch"] = mismatch
            passages.append(passage)
        alarm["passages"] = passages
        copied.append(alarm)
    return copied


def render_patient_situation(sit_id: str, matrix: dict[str, Any]) -> dict[str, Any]:
    """Same questions as Anna's catalogue. Answers come only from this matrix."""
    base = catalogue.SITUATIONS[sit_id]
    overlay = catalogue_0002.SITUATIONS[sit_id]
    questions = {item["id"]: item["question"] for item in base["answers"]}
    answers = []
    for item in overlay["answers"]:
        found: list[dict[str, Any]] = []
        missing: list[str] = []
        for row in item["rows"]:
            facts = matrix_mod.facts_for_rows(
                matrix,
                [row],
                column_rule=item.get("column_rule", "latest"),
            )
            if facts:
                found.extend(facts)
            else:
                missing.append(catalogue_0002.ROW_GAPS.get(row, row.replace("_", " ")))
        question = questions.get(item["id"], item["id"])
        if not found:
            answers.append(
                {
                    "id": item["id"],
                    "question": question,
                    "answer": "Not documented.",
                    "status": "not_documented",
                    "sources": [],
                }
            )
            continue
        answer = "; ".join(dict.fromkeys(fact["display"] for fact in found))
        if missing:
            answer += ". Not documented: " + ", ".join(missing) + "."
        answers.append(
            {
                "id": item["id"],
                "question": question,
                "answer": answer,
                "status": "documented",
                "sources": sources_from(found),
            }
        )

    extra = []
    for row in overlay.get("extra_rows", []):
        facts = matrix_mod.facts_for_rows(matrix, [row], column_rule="all")
        if not facts:
            continue
        extra.append(
            {
                "row": row,
                "display": "; ".join(dict.fromkeys(fact["display"] for fact in facts)),
                "sources": sources_from(facts),
            }
        )

    wanted = set(overlay.get("contradiction_ids") or [])
    contradictions = contradictions_for_card(
        matrix, [item for item in matrix["contradictions"] if item["id"] in wanted]
    )
    return {
        "situation_id": sit_id,
        "title": overlay.get("title") or base["title"],
        "role": base["role"],
        "description": overlay.get("description") or base["description"],
        "answers": answers,
        "extra_facts": extra,
        "not_documented": overlay.get("not_documented") or [],
        "contradictions": contradictions,
        "as_of": matrix.get("as_of"),
    }


def render_free_text_patient(text: str, matrix: dict[str, Any]) -> dict[str, Any]:
    matched = match_situation_by_keywords(text)
    if matched and matched in catalogue_0002.SITUATIONS:
        card = render_patient_situation(matched, matrix)
        card["matched_preset"] = matched
        card["input"] = text
        return card

    present_rows = sorted({fact["row"] for fact in matrix["facts"]})
    selection = llama_select_rows(text, matrix, allowed_rows=present_rows)
    facts_by_row = {}
    for row in selection["rows"]:
        facts = matrix_mod.facts_for_rows(matrix, [row], column_rule="all")
        if facts:
            facts_by_row[row] = facts

    answers = []
    for idx, row in enumerate(selection["rows"], start=1):
        facts = facts_by_row.get(row, [])
        if not facts:
            answers.append(
                {
                    "id": f"free.{idx}",
                    "question": row,
                    "answer": "Not documented.",
                    "status": "not_documented",
                    "sources": [],
                }
            )
            continue
        answers.append(
            {
                "id": f"free.{idx}",
                "question": row.replace("_", " "),
                "answer": "; ".join(dict.fromkeys(fact["display"] for fact in facts)),
                "status": "documented",
                "sources": sources_from(facts),
            }
        )

    note = selection.get("note")
    if not answers and not note:
        answers.append(
            {
                "id": "free.1",
                "question": text,
                "answer": "not documented",
                "status": "not_documented",
                "sources": [],
            }
        )

    selected_rows = set(selection["rows"])
    contradictions = contradictions_for_card(
        matrix, [item for item in matrix["contradictions"] if item.get("row") in selected_rows]
    )
    return {
        "situation_id": "free",
        "title": "Custom situation",
        "role": selection.get("role") or "general",
        "description": text,
        "answers": answers,
        "extra_facts": [],
        "not_documented": selection.get("not_documented") or [],
        "contradictions": contradictions,
        "as_of": matrix.get("as_of"),
        "note": note,
        "input": text,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[http] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            html_path = APP_DIR / "index.html"
            self._send(200, html_path.read_bytes(), "text/html; charset=utf-8")
            return

        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            file_path = APP_DIR / rel
            if not file_path.resolve().is_relative_to(APP_DIR.resolve()) or not file_path.is_file():
                self._json(404, {"error": "not found"})
                return
            ctype = "text/plain; charset=utf-8"
            if file_path.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif file_path.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            self._send(200, file_path.read_bytes(), ctype)
            return

        if path == "/api/patients":
            self._json(
                200,
                {"patients": [patients.public_patient(pid) for pid in patients.PATIENTS]},
            )
            return

        if path == "/api/status":
            patient_id = resolve_patient_id(parsed)
            if patient_id is None:
                self._json(404, {"error": "unknown patient"})
                return
            matrix = ensure_matrix(patient_id)
            ready = matrix is not None and matrix.get("status") == "ready"
            self._json(
                200,
                {
                    "ready": ready,
                    "building": bool(STATE["building"].get(patient_id)),
                    "error": STATE["error"].get(patient_id),
                    "llama_status": (matrix or {}).get("llama_status"),
                    "model": (matrix or {}).get("model"),
                    "fact_count": len((matrix or {}).get("facts") or []),
                    "contradiction_count": len((matrix or {}).get("contradictions") or []),
                    "patient": patients.public_patient(patient_id),
                },
            )
            return

        if path == "/api/situations":
            items = [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "role": s["role"],
                    "description": s["description"],
                }
                for s in catalogue.SITUATIONS.values()
                if s["id"] != "6" or True
            ]
            # Keep situation 6 as extra test button
            self._json(200, {"situations": items})
            return

        if path.startswith("/api/situation/"):
            patient_id = resolve_patient_id(parsed)
            if patient_id is None:
                self._json(404, {"error": "unknown patient"})
                return
            matrix = ensure_matrix(patient_id)
            if matrix is None:
                self._json(
                    503,
                    {
                        "error": "matrix_not_ready",
                        "building": bool(STATE["building"].get(patient_id)),
                    },
                )
                return
            sit_id = path.rsplit("/", 1)[-1]
            sit = catalogue.SITUATIONS.get(sit_id)
            if not sit:
                self._json(404, {"error": "unknown situation"})
                return
            if patient_id == patients.DEFAULT_PATIENT_ID:
                self._json(200, render_situation(sit, matrix))
            else:
                self._json(200, render_patient_situation(sit_id, matrix))
            return

        if path.startswith("/api/document/"):
            patient_id = resolve_patient_id(parsed)
            if patient_id is None:
                self._json(404, {"error": "unknown patient"})
                return
            matrix = ensure_matrix(patient_id)
            if matrix is None:
                self._json(503, {"error": "matrix_not_ready"})
                return
            doc_id = path.rsplit("/", 1)[-1]
            doc = matrix["documents"].get(doc_id)
            if not doc:
                self._json(404, {"error": "unknown document"})
                return
            self._json(200, doc)
            return

        if path == "/api/rebuild":
            patient_id = resolve_patient_id(parsed)
            if patient_id is None:
                self._json(404, {"error": "unknown patient"})
                return
            build_cache_async(patient_id, force=True)
            self._json(200, {"ok": True, "building": True, "patient": patient_id})
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/free-text":
            self._json(404, {"error": "not found"})
            return
        body = self._read_json()
        patient_id = resolve_patient_id(parsed, body)
        if patient_id is None:
            self._json(404, {"error": "unknown patient"})
            return
        matrix = ensure_matrix(patient_id)
        if matrix is None:
            self._json(
                503,
                {
                    "error": "matrix_not_ready",
                    "building": bool(STATE["building"].get(patient_id)),
                },
            )
            return
        text = (body.get("text") or "").strip()
        if not text:
            self._json(400, {"error": "empty text"})
            return
        if patient_id == patients.DEFAULT_PATIENT_ID:
            self._json(200, render_free_text(text, matrix))
        else:
            self._json(200, render_free_text_patient(text, matrix))


def share_url() -> str:
    """Address other computers on this network should open."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    return f"http://{ip}:{PORT}/"


def main() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    for patient_id in patients.PATIENTS:
        load_cache(patient_id)
    if STATE["matrices"].get(patients.DEFAULT_PATIENT_ID) is None:
        build_cache_async(patients.DEFAULT_PATIENT_ID, force=False)
    else:
        print("[server] Using cached matrices. GET /api/rebuild?patient=<id> refreshes one chart.")

    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[server] Share {share_url()}")
    print(f"[server] This machine: http://127.0.0.1:{PORT}/")
    print(f"[server] Model={matrix_mod.OLLAMA_MODEL} Ollama={matrix_mod.OLLAMA_URL}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
