const state = {
  cases: [],
  currentCaseId: null,
  bundle: null,
  analysis: null,
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === "string" ? payload : payload.message || payload.error || "Request failed";
    throw new Error(message);
  }
  return payload;
}

function showNotice(message, type = "info") {
  const notice = $("#notice");
  notice.textContent = message;
  notice.className = `notice ${type}`;
  notice.hidden = false;
}

function hideNotice() {
  $("#notice").hidden = true;
}

async function runSafely(action, successMessage = "") {
  try {
    hideNotice();
    const result = await action();
    if (successMessage) showNotice(successMessage, "success");
    return result;
  } catch (error) {
    showNotice(error.message || "Request failed", "error");
    return null;
  }
}

function formData(form) {
  const data = {};
  const fd = new FormData(form);
  for (const [key, value] of fd.entries()) {
    data[key] = value;
  }
  for (const element of form.querySelectorAll("input[type='checkbox']")) {
    data[element.name] = element.checked;
  }
  for (const key of ["quantity_value", "target_package_weight_value", "unit_price", "package_weight_value", "amount_per_unit"]) {
    if (key in data && data[key] !== "") data[key] = Number(data[key]);
  }
  return data;
}

function money(value, unit = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const suffix = unit ? `/${unit}` : "";
  return `$${Number(value).toFixed(4)}${suffix}`;
}

async function loadCases() {
  state.cases = await api("/api/cases");
  renderCases();
  if (!state.currentCaseId && state.cases.length) {
    await selectCase(state.cases[0].id);
  } else if (state.currentCaseId) {
    await selectCase(state.currentCaseId);
  }
}

function renderCases() {
  const list = $("#caseList");
  list.innerHTML = "";
  for (const item of state.cases) {
    const node = document.createElement("div");
    node.className = `case-item ${item.id === state.currentCaseId ? "active" : ""}`;
    node.innerHTML = `<strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.commodity)} | ${escapeHtml(item.pack)}</span>`;
    node.addEventListener("click", () => selectCase(item.id));
    list.appendChild(node);
  }
}

async function selectCase(caseId) {
  state.currentCaseId = caseId;
  state.bundle = await api(`/api/cases/${caseId}`);
  state.analysis = await api(`/api/cases/${caseId}/analysis`);
  renderCases();
  renderCaseHeader();
  renderEvidenceRecord();
  renderAdjustmentEvidenceOptions();
  renderAnalysis();
}

function renderCaseHeader() {
  const c = state.bundle.case;
  $("#caseTitle").textContent = c.title;
  $("#caseMeta").textContent = `${c.commodity} | ${c.form} | ${c.pack} | ${c.quantity_value} ${c.quantity_unit} | ${c.destination || "destination not specified"}`;
  $("#memoDownload").href = `/api/cases/${c.id}/memo.txt`;
  $("#igceDownload").href = `/api/cases/${c.id}/igce.csv`;
  $("#exportDownload").href = `/api/cases/${c.id}/export.json`;
}

function renderAnalysis() {
  const analysis = state.analysis;
  const stats = analysis.statistics;
  $("#metricEligible").textContent = analysis.eligible_count;
  $("#metricMedian").textContent = money(stats.median, analysis.target_unit);
  $("#metricRange").textContent =
    stats.reasonableness_low === null ? "n/a" : `${money(stats.reasonableness_low)} to ${money(stats.reasonableness_high)}`;
  $("#metricFlags").textContent = analysis.risk_flags.length;

  const rows = $("#analysisRows");
  rows.innerHTML = "";
  for (const row of analysis.evidence) {
    const tr = document.createElement("tr");
    const issues = [...row.critical_issues, ...row.warnings];
    tr.innerHTML = `
      <td>${escapeHtml(row.source_name)}</td>
      <td><span class="status ${row.status === "unit_price_eligible" ? "ok" : "context"}">${row.status.replaceAll("_", " ")}</span></td>
      <td>${money(row.normalized_unit_price, row.target_unit)}</td>
      <td>${money(row.adjusted_unit_price, row.target_unit)}</td>
      <td>${issues.length ? `<ul class="issue-list">${issues.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : "Clear"}</td>
    `;
    rows.appendChild(tr);
  }

  const flags = $("#riskFlags");
  flags.innerHTML = analysis.risk_flags.length
    ? analysis.risk_flags.map((flag) => `<li>${escapeHtml(flag)}</li>`).join("")
    : "<li>No automated risk flags.</li>";
}

function renderEvidenceRecord() {
  const target = $("#evidenceRecord");
  target.innerHTML = "";
  for (const item of state.bundle.evidence) {
    const record = document.createElement("div");
    record.className = "record";
    record.innerHTML = `
      <strong>${escapeHtml(item.source_name)}</strong>
      <small>${escapeHtml(item.source_type)} | ${escapeHtml(item.raw_description || "no description")}</small>
      <div>${escapeHtml(item.commodity)} | ${escapeHtml(item.form)} | ${escapeHtml(item.pack)} | ${item.unit_price ?? "no unit price"} ${escapeHtml(item.price_basis_unit || "")}</div>
      <div><a href="${escapeAttr(item.source_url || "#")}" target="_blank">${escapeHtml(item.source_url || "no source URL")}</a></div>
    `;
    target.appendChild(record);
  }
}

function renderAdjustmentEvidenceOptions() {
  const select = $("#adjustmentEvidence");
  select.innerHTML = "<option value=''>Apply to all evidence</option>";
  for (const item of state.bundle.evidence) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.source_name;
    select.appendChild(option);
  }
}

async function loadMemo() {
  if (!state.currentCaseId) return;
  const response = await fetch(`/api/cases/${state.currentCaseId}/memo.txt`);
  $("#memoText").value = await response.text();
}

async function addContextEvidenceFromUsa(record) {
  const c = state.bundle.case;
  await api(`/api/cases/${state.currentCaseId}/evidence`, {
    method: "POST",
    body: JSON.stringify({
      source_type: "usaspending_award",
      source_name: `USAspending ${record["Award ID"] || "award"}`,
      source_url: record.generated_internal_id ? `https://www.usaspending.gov/award/${record.generated_internal_id}` : "https://www.usaspending.gov/",
      citation: "USAspending discovery record; award amount is not CLIN-level unit-price evidence.",
      raw_description: record.Description || "",
      commodity: c.commodity,
      form: c.form,
      pack: c.pack,
      grade: "",
      location: record["Primary Place of Performance"]?.state_name || "",
      price_date: record["Start Date"] || "",
      freight_included: false,
      delivery_terms: "unknown",
      metadata: record,
    }),
  });
  await selectCase(state.currentCaseId);
}

function renderUsaResults(payload) {
  const target = $("#usaResults");
  target.innerHTML = "";
  if (payload.error) {
    target.innerHTML = `<div class="record"><strong>${escapeHtml(payload.error)}</strong><small>${escapeHtml(payload.message || "")}</small></div>`;
    return;
  }
  const warning = document.createElement("div");
  warning.className = "record";
  warning.innerHTML = `<strong>Use Warning</strong><small>${escapeHtml(payload.unit_price_warning || "")}</small>`;
  target.appendChild(warning);
  for (const record of payload.results || []) {
    const node = document.createElement("div");
    node.className = "record";
    node.innerHTML = `
      <strong>${escapeHtml(record["Award ID"] || "award")} | ${escapeHtml(record["Recipient Name"] || "unknown recipient")}</strong>
      <small>${escapeHtml(record["Start Date"] || "")} | ${escapeHtml(record.PSC?.code || "")} ${escapeHtml(record.PSC?.description || "")}</small>
      <div>${escapeHtml(record.Description || "")}</div>
      <div>Award amount: ${money(record["Award Amount"])}</div>
      <button type="button">Add As Context Evidence</button>
    `;
    node.querySelector("button").addEventListener("click", () => addContextEvidenceFromUsa(record));
    target.appendChild(node);
  }
}

async function loadOperatorStatus() {
  const status = await api("/api/operator/status");
  const target = $("#operatorStatus");
  target.innerHTML = `
    <div class="record">
      <strong>Server</strong>
      <small>${escapeHtml(status.host)}:${escapeHtml(status.port)} | uptime ${escapeHtml(status.uptime_seconds)} seconds</small>
      <pre>${escapeHtml(JSON.stringify({
        schema_version: status.schema_version,
        journal_mode: status.journal_mode,
        database_path: status.database_path,
        backup_dir: status.backup_dir,
        counts: status.counts
      }, null, 2))}</pre>
    </div>
  `;
}

async function createBackup() {
  const result = await api("/api/operator/backup", { method: "POST", body: JSON.stringify({}) });
  $("#backupResult").innerHTML = `
    <div class="record">
      <strong>Backup Created</strong>
      <small>${escapeHtml(result.backup_path)}</small>
    </div>
  `;
}

function renderSamResults(payload) {
  const target = $("#samResults");
  target.innerHTML = "";
  if (payload.error) {
    target.innerHTML = `<div class="record"><strong>${escapeHtml(payload.error)}</strong><small>${escapeHtml(payload.message)}</small></div>`;
    return;
  }
  const warning = document.createElement("div");
  warning.className = "record";
  warning.innerHTML = `<strong>Use Warning</strong><small>${escapeHtml(payload.unit_price_warning || "")}</small>`;
  target.appendChild(warning);
  for (const record of payload.results || []) {
    const node = document.createElement("div");
    node.className = "record";
    node.innerHTML = `
      <strong>${escapeHtml(record.solicitationNumber || "notice")} | ${escapeHtml(record.title || "")}</strong>
      <small>${escapeHtml(record.postedDate || "")} | ${escapeHtml(record.type || "")} | ${escapeHtml(record.naicsCode || "")}</small>
      <div>${escapeHtml(record.fullParentPathName || "")}</div>
      <div><a href="${escapeAttr(record.uiLink || "#")}" target="_blank">${escapeHtml(record.uiLink || "no UI link")}</a></div>
    `;
    target.appendChild(node);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function bindEvents() {
  $("#refreshCases").addEventListener("click", () => runSafely(loadCases, "Cases refreshed."));
  $("#runAnalysis").addEventListener("click", async () => {
    await runSafely(async () => {
      if (!state.currentCaseId) return;
      state.analysis = await api(`/api/cases/${state.currentCaseId}/analysis`);
      renderAnalysis();
    }, "Analysis refreshed.");
  });
  $("#loadMemo").addEventListener("click", () => runSafely(loadMemo, "Memo loaded."));
  $("#loadStatus").addEventListener("click", () => runSafely(loadOperatorStatus, "Operator status refreshed."));
  $("#backupNow").addEventListener("click", () => runSafely(createBackup, "Backup created."));

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active");
      $(`#${tab.dataset.tab}Tab`).classList.add("active");
    });
  });

  $("#caseForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runSafely(async () => {
      const created = await api("/api/cases", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
      await loadCases();
      await selectCase(created.id);
    }, "Case created.");
  });

  $("#evidenceForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runSafely(async () => {
      if (!state.currentCaseId) return;
      await api(`/api/cases/${state.currentCaseId}/evidence`, { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
      event.currentTarget.reset();
      await selectCase(state.currentCaseId);
    }, "Evidence added.");
  });

  $("#adjustmentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runSafely(async () => {
      if (!state.currentCaseId) return;
      await api(`/api/cases/${state.currentCaseId}/adjustments`, { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
      event.currentTarget.reset();
      await selectCase(state.currentCaseId);
    }, "Adjustment added.");
  });

  $("#usaForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runSafely(async () => {
      const data = formData(event.currentTarget);
      const payload = await api(`/api/search/usaspending?keywords=${encodeURIComponent(data.keywords || "")}`);
      renderUsaResults(payload);
    }, "USAspending search complete.");
  });

  $("#samForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runSafely(async () => {
      const data = formData(event.currentTarget);
      const params = new URLSearchParams(data);
      const payload = await api(`/api/search/sam?${params.toString()}`);
      renderSamResults(payload);
    }, "SAM.gov search complete.");
  });
}

bindEvents();
loadCases().then(loadOperatorStatus).catch((error) => {
  $("#caseTitle").textContent = "Startup error";
  $("#caseMeta").textContent = error.message;
  showNotice(error.message, "error");
});
