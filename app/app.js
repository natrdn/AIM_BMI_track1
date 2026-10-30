const statusEl = document.getElementById("status");
const patientForm = document.getElementById("patient-form");
const patientText = document.getElementById("patient-text");
const patientOpen = document.getElementById("patient-open");
const patientList = document.getElementById("patient-list");
const patientError = document.getElementById("patient-error");
const roleButtonsEl = document.getElementById("role-buttons");
const buttonsEl = document.getElementById("situation-buttons");
const freeForm = document.getElementById("free-form");
const freeText = document.getElementById("free-text");
const freeSubmit = document.getElementById("free-submit");
const cardEl = document.getElementById("card");
const briefPane = document.getElementById("brief-pane");
const skeletonEl = document.getElementById("brief-skeleton");
const emptyEl = document.getElementById("brief-empty");
const emptyText = document.getElementById("brief-empty-text");
const factsWrap = document.getElementById("facts-wrap");
const answersEl = document.getElementById("answers");
const extrasWrap = document.getElementById("extras-wrap");
const extrasEl = document.getElementById("extras");
const alarmsWrap = document.getElementById("alarms-wrap");
const alarmsEl = document.getElementById("alarms");
const docEmpty = document.getElementById("doc-empty");
const docView = document.getElementById("doc-view");
const docKicker = document.getElementById("doc-kicker");
const docTitle = document.getElementById("doc-title");
const docSub = document.getElementById("doc-sub");
const docText = document.getElementById("doc-text");

const EMPTY_ROLE = "Say who you are.";
const EMPTY_CHART = "Open a chart.";
const EMPTY_READY = "Choose a task, or describe this purpose.";
const EMPTY_FAILED = "This chart could not be opened.";

let ready = false;
let activeId = null;
let selectedRole = null;
let selectedPatient = null;
let patients = [];
let situations = [];
let watchToken = 0;

function setStatus(kind, text) {
  if (kind === "ready") {
    statusEl.classList.add("hidden");
    return;
  }
  statusEl.className = `status status-${kind}`;
  statusEl.textContent = text;
}

function setBriefMode(mode) {
  skeletonEl.classList.toggle("hidden", mode !== "loading");
  skeletonEl.setAttribute("aria-hidden", mode === "loading" ? "false" : "true");
  emptyEl.classList.toggle("hidden", mode !== "empty");
  briefPane.setAttribute("aria-busy", mode === "loading" ? "true" : "false");
  if (mode !== "card") cardEl.classList.add("hidden");
  else cardEl.classList.remove("hidden");
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function patientQuery(patientId) {
  return `patient=${encodeURIComponent(patientId || selectedPatient)}`;
}

function setChartEnabled(enabled) {
  patientText.disabled = !enabled;
  patientOpen.disabled = !enabled;
}

function clearOpenedChart() {
  watchToken += 1;
  selectedPatient = null;
  ready = false;
  patientText.value = "";
  showPatientError("");
  document.getElementById("patient-name").textContent = "—";
  document.getElementById("patient-id").textContent = "";
  document.getElementById("patient-asof").textContent = "";
  freeSubmit.disabled = true;
  activeId = null;
  cardEl.classList.add("hidden");
  resetLetter();
  emptyText.textContent = selectedRole ? EMPTY_CHART : EMPTY_ROLE;
  setBriefMode("empty");
}

async function pollStatus() {
  const patientNow = selectedPatient;
  if (!patientNow) return false;
  try {
    const s = await fetchJSON(`/api/status?${patientQuery(patientNow)}`);
    if (patientNow !== selectedPatient) return false;
    if (s.patient) renderPatientHeader(s.patient);
    if (s.ready) {
      ready = true;
      freeSubmit.disabled = false;
      [...buttonsEl.querySelectorAll("button")].forEach((b) => {
        b.disabled = false;
      });
      setStatus("ready", "");
      if (cardEl.classList.contains("hidden")) {
        emptyText.textContent = EMPTY_READY;
        setBriefMode("empty");
      } else {
        setBriefMode("card");
      }
      return true;
    }
    ready = false;
    freeSubmit.disabled = true;
    [...buttonsEl.querySelectorAll("button")].forEach((b) => {
      b.disabled = true;
    });
    if (s.error) {
      setStatus("error", `Build failed: ${s.error}`);
      emptyText.textContent = EMPTY_FAILED;
      setBriefMode("empty");
      return false;
    }
    const reading = s.patient && s.patient.source === "pdf" ? "Reading the PDFs…" : "Reading the letters…";
    setStatus("wait", reading);
    setBriefMode("loading");
    return false;
  } catch (err) {
    if (patientNow !== selectedPatient) return false;
    setStatus("error", `Cannot reach server: ${err.message}`);
    emptyText.textContent = EMPTY_FAILED;
    setBriefMode("empty");
    return false;
  }
}

async function watchPatient() {
  const token = ++watchToken;
  ready = false;
  freeSubmit.disabled = true;
  for (;;) {
    if (token !== watchToken) return;
    const ok = await pollStatus();
    if (token !== watchToken) return;
    if (ok) return;
    await new Promise((r) => setTimeout(r, 1500));
  }
}

function renderPatientHeader(patient) {
  document.getElementById("patient-name").textContent = patient.name || "";
  document.getElementById("patient-id").textContent = patient.id || "";
  document.getElementById("patient-asof").textContent = patient.as_of_label
    ? `Chart as of ${patient.as_of_label}`
    : "";
}

function resetLetter() {
  docView.classList.add("hidden");
  docEmpty.classList.remove("hidden");
  docText.textContent = "";
  docKicker.textContent = "";
  docTitle.textContent = "";
  docSub.textContent = "";
}

function clearCard() {
  activeId = null;
  cardEl.classList.add("hidden");
  [...buttonsEl.querySelectorAll("button")].forEach((b) => b.classList.remove("active"));
  resetLetter();
  setBriefMode("loading");
}

function showPatientError(message) {
  if (!message) {
    patientError.textContent = "";
    patientError.classList.add("hidden");
    return;
  }
  patientError.textContent = message;
  patientError.classList.remove("hidden");
}

function matchPatient(text) {
  const query = text.trim().toLowerCase().replace(/\s+/g, " ");
  if (!query) return { error: "Type a patient name or chart id." };
  const byId = patients.filter((patient) => patient.id.toLowerCase() === query);
  if (byId.length === 1) return { patient: byId[0] };
  const byName = patients.filter((patient) => patient.name.toLowerCase() === query);
  if (byName.length === 1) return { patient: byName[0] };
  const partial = patients.filter((patient) => {
    const name = patient.name.toLowerCase();
    const id = patient.id.toLowerCase();
    return name.includes(query) || id.includes(query);
  });
  if (partial.length === 1) return { patient: partial[0] };
  if (partial.length > 1) {
    return { error: "More than one chart matches. Type the full name or id." };
  }
  return { error: "No chart matches that name or id." };
}

function selectPatient(patient) {
  if (!selectedRole) return;
  showPatientError("");
  patientText.value = patient.name;
  if (patient.id === selectedPatient) return;
  selectedPatient = patient.id;
  ready = false;
  freeSubmit.disabled = true;
  [...buttonsEl.querySelectorAll("button")].forEach((btn) => {
    btn.disabled = true;
  });
  renderPatientHeader(patient);
  clearCard();
  watchPatient();
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatIso(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!match) return iso || "";
  return `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}`;
}

function mismatchLabel(mismatch) {
  const kind = mismatch.kind === "admission"
    ? "Admission"
    : mismatch.kind === "discharge"
      ? "Discharge"
      : "Measurement";
  return `${kind} date mismatch: letter ${formatIso(mismatch.documented)}, text ${formatIso(mismatch.in_text)}`;
}

function sourceButton(src) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "source-link";
  if (src.date_mismatch) btn.classList.add("mismatch");
  btn.textContent = `${src.doc_id} · ${src.date}`;
  btn.title = src.date_mismatch
    ? `${mismatchLabel(src.date_mismatch)}. ${src.quote_de || ""}`
    : src.quote_de;
  btn.addEventListener("click", () => {
    document.querySelectorAll(".source-link.active").forEach((el) => el.classList.remove("active"));
    btn.classList.add("active");
    openDocument(src.doc_id, src.quote_de);
  });
  return btn;
}

function appendDateMismatches(parent, sources) {
  const seen = new Set();
  for (const src of sources || []) {
    const mismatch = src.date_mismatch;
    if (!mismatch) continue;
    const key = `${src.doc_id}|${mismatch.documented}|${mismatch.in_text}|${mismatch.kind}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const note = document.createElement("p");
    note.className = "date-mismatch";
    note.textContent = `${mismatchLabel(mismatch)} (${src.doc_id}).`;
    parent.appendChild(note);
  }
  return seen.size > 0;
}

function gapChip() {
  const chip = document.createElement("span");
  chip.className = "gap-chip";
  chip.textContent = "Not documented";
  return chip;
}

function gapWords(value) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9äöüß]+/g, " ")
    .split(" ")
    .filter((word) => word.length > 3);
}

function gapAlreadyOnAnswer(item, answers) {
  const words = gapWords(item);
  if (!words.length) return true;
  return (answers || []).some((answer) => {
    if (answer.status !== "not_documented") return false;
    const hay = new Set(gapWords(`${answer.question || ""} ${answer.answer || ""}`));
    const hits = words.filter((word) => hay.has(word)).length;
    return hits / words.length >= 0.5;
  });
}

function appendSources(parent, sources) {
  const wrap = document.createElement("div");
  wrap.className = "sources";
  (sources || []).forEach((src) => wrap.appendChild(sourceButton(src)));
  parent.appendChild(wrap);
  return wrap;
}

function renderCard(card) {
  setStatus("ready", "");
  setBriefMode("card");
  document.getElementById("card-role").textContent = card.role || "";
  document.getElementById("card-title").textContent = card.title || "";
  document.getElementById("card-desc").textContent = card.description || "";
  const note = document.getElementById("card-note");
  if (card.note) {
    note.textContent = card.note;
    note.classList.remove("hidden");
  } else {
    note.classList.add("hidden");
  }

  if (card.contradictions && card.contradictions.length) {
    alarmsWrap.classList.remove("hidden");
    alarmsEl.innerHTML = "";
    for (const c of card.contradictions) {
      const div = document.createElement("div");
      div.className = "alarm";
      div.innerHTML = `
        <div class="alarm-head">
          <span class="qid">${escapeHtml(c.id)}</span>
          <h4>${escapeHtml(c.title)}</h4>
        </div>
        <p>${escapeHtml(c.summary)}</p>
      `;
      const passages = (c.passages || []).map((p) => ({
        doc_id: p.doc_id,
        date: p.date,
        quote_de: p.quote_de,
        date_mismatch: p.date_mismatch,
      }));
      appendDateMismatches(div, passages);
      appendSources(div, passages);
      alarmsEl.appendChild(div);
    }
  } else {
    alarmsWrap.classList.add("hidden");
  }

  const answers = card.answers || [];
  const gaps = (card.not_documented || []).filter((item) => !gapAlreadyOnAnswer(item, answers));
  answersEl.innerHTML = "";
  if (answers.length || gaps.length) {
    factsWrap.classList.remove("hidden");
  } else {
    factsWrap.classList.add("hidden");
  }

  for (const a of answers) {
    const div = document.createElement("div");
    const missing = a.status === "not_documented";
    div.className = `row${missing ? " missing" : ""}`;
    div.innerHTML = `
      <div class="row-main">
        <p class="qid">${escapeHtml(a.id || "")}</p>
        <p class="q">${escapeHtml(a.question)}</p>
        <p class="a">${escapeHtml(a.answer)}</p>
      </div>
    `;
    if (appendDateMismatches(div.querySelector(".row-main"), a.sources)) {
      div.classList.add("date-clash");
    }
    const side = document.createElement("div");
    side.className = "row-side";
    if (missing) side.appendChild(gapChip());
    if (a.sources && a.sources.length) appendSources(side, a.sources);
    div.appendChild(side);
    answersEl.appendChild(div);
  }

  for (const item of gaps) {
    const div = document.createElement("div");
    div.className = "row missing";
    div.innerHTML = `
      <div class="row-main">
        <p class="q">${escapeHtml(item)}</p>
        <p class="a">Not documented</p>
      </div>
    `;
    const side = document.createElement("div");
    side.className = "row-side";
    side.appendChild(gapChip());
    div.appendChild(side);
    answersEl.appendChild(div);
  }

  if (card.extra_facts && card.extra_facts.length) {
    extrasWrap.classList.remove("hidden");
    extrasEl.innerHTML = "";
    for (const ex of card.extra_facts) {
      const div = document.createElement("div");
      div.className = "row";
      div.innerHTML = `
        <div class="row-main">
          <p class="q">${escapeHtml(ex.row)}</p>
          <p class="a">${escapeHtml(ex.display)}</p>
        </div>
      `;
      if (appendDateMismatches(div.querySelector(".row-main"), ex.sources)) {
        div.classList.add("date-clash");
      }
      const side = document.createElement("div");
      side.className = "row-side";
      appendSources(side, ex.sources || []);
      div.appendChild(side);
      extrasEl.appendChild(div);
    }
  } else {
    extrasWrap.classList.add("hidden");
  }

  if (window.matchMedia("(max-width: 980px)").matches) {
    cardEl.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    briefPane.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function openDocument(docId, quote) {
  const patientNow = selectedPatient;
  const doc = await fetchJSON(`/api/document/${encodeURIComponent(docId)}?${patientQuery(patientNow)}`);
  if (patientNow !== selectedPatient) return;
  docEmpty.classList.add("hidden");
  docView.classList.remove("hidden");
  const kicker = [doc.short, doc.id].filter(Boolean).join(" · ");
  docKicker.textContent = kicker;
  docTitle.textContent = doc.title || "Letter";
  docSub.textContent = doc.date || "";
  const text = doc.text || "";
  if (quote && text.includes(quote)) {
    const safeQuote = escapeHtml(quote);
    const safeText = escapeHtml(text);
    docText.innerHTML = safeText.replaceAll(safeQuote, `<mark>${safeQuote}</mark>`);
    const mark = docText.querySelector("mark");
    if (mark) mark.scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    docText.textContent = text;
  }
}

function renderTasks() {
  buttonsEl.innerHTML = "";
  const tasks = situations.filter((item) => item.role === selectedRole);
  for (const s of tasks) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.innerHTML = `<span class="task-id">${escapeHtml(s.id)}</span><span class="task-title">${escapeHtml(s.title)}</span>`;
    btn.title = `${s.role}: ${s.title}`;
    btn.disabled = !ready;
    btn.addEventListener("click", async () => {
      if (!ready || !selectedPatient) return;
      const patientNow = selectedPatient;
      activeId = s.id;
      [...buttonsEl.querySelectorAll("button")].forEach((b) =>
        b.classList.toggle("active", b === btn)
      );
      try {
        const card = await fetchJSON(`/api/situation/${s.id}?${patientQuery(patientNow)}`);
        if (patientNow !== selectedPatient) return;
        renderCard(card);
      } catch (err) {
        if (patientNow === selectedPatient) setStatus("error", err.message);
      }
    });
    buttonsEl.appendChild(btn);
  }
}

function selectRole(role) {
  if (role === selectedRole) return;
  selectedRole = role;
  [...roleButtonsEl.querySelectorAll("button")].forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.role === role);
  });
  setChartEnabled(true);
  clearOpenedChart();
  renderTasks();
}

function renderRoles() {
  roleButtonsEl.innerHTML = "";
  const roles = [];
  for (const item of situations) {
    if (item.role && !roles.includes(item.role)) roles.push(item.role);
  }
  for (const role of roles) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.role = role;
    btn.innerHTML = `<span class="task-title">${escapeHtml(role)}</span>`;
    btn.addEventListener("click", () => selectRole(role));
    roleButtonsEl.appendChild(btn);
  }
}

async function loadSituations() {
  const data = await fetchJSON("/api/situations");
  situations = data.situations || [];
  renderRoles();
  renderTasks();
}

freeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!ready || !selectedRole || !selectedPatient) return;
  const text = freeText.value.trim();
  if (!text) return;
  const patientNow = selectedPatient;
  activeId = null;
  [...buttonsEl.querySelectorAll("button")].forEach((b) => b.classList.remove("active"));
  freeSubmit.disabled = true;
  freeSubmit.textContent = "Asking Llama…";
  try {
    const card = await fetchJSON("/api/free-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, patient: patientNow }),
    });
    if (patientNow !== selectedPatient) return;
    renderCard(card);
  } catch (err) {
    if (patientNow === selectedPatient) setStatus("error", err.message);
  } finally {
    if (patientNow === selectedPatient) {
      freeSubmit.disabled = !ready;
      freeSubmit.textContent = "Open brief";
    }
  }
});

async function loadPatients() {
  const data = await fetchJSON("/api/patients");
  patients = data.patients;
  patientList.innerHTML = "";
  for (const patient of patients) {
    const option = document.createElement("option");
    option.value = patient.name;
    option.label = `${patient.name} · ${patient.id}`;
    patientList.appendChild(option);
    const byId = document.createElement("option");
    byId.value = patient.id;
    byId.label = patient.name;
    patientList.appendChild(byId);
  }
}

patientForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!selectedRole) return;
  const result = matchPatient(patientText.value);
  if (!result.patient) {
    showPatientError(result.error);
    return;
  }
  selectPatient(result.patient);
});

(async function init() {
  setChartEnabled(false);
  emptyText.textContent = EMPTY_ROLE;
  setBriefMode("empty");
  await loadPatients();
  await loadSituations();
})();
