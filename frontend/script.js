const runButton = document.getElementById("run-btn");
const statusEl = document.getElementById("status");
const outputEl = document.getElementById("output");

const fileInputs = {
  logs_file: document.getElementById("logs-file"),
  alerts_file: document.getElementById("alerts-file"),
  deployments_file: document.getElementById("deployments-file"),
  ticket_file: document.getElementById("ticket-file"),
};

function getApiUrl(path) {
  const base = "http://192.168.1.3:5000";
  return base ? `${base}${path}` : path;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildFormData() {
  const formData = new FormData();
  Object.entries(fileInputs).forEach(([fieldName, inputEl]) => {
    const file = inputEl.files[0];
    if (file) {
      formData.append(fieldName, file);
    }
  });
  return formData;
}

function getTimelineLines(data) {
  if (Array.isArray(data.timeline) && data.timeline.length && typeof data.timeline[0] === "object") {
    return data.timeline.map((item) => `${item.timestamp} - ${item.event_type}: ${item.details}`);
  }
  if (Array.isArray(data?.report?.timeline)) {
    return data.report.timeline;
  }
  return [];
}

function renderList(items) {
  if (!items.length) {
    return "<p>No items available.</p>";
  }
  return `<ul class="list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderReport(data) {
  const understanding = data.incident_understanding || {};
  const report = data.report || {};
  const timelineLines = getTimelineLines(data);
  const hypotheses = Array.isArray(data.hypotheses)
    ? data.hypotheses.map((item, index) => {
        const timestamps = Array.isArray(item.supporting_timestamps)
          ? item.supporting_timestamps.join(", ")
          : "";
        return `#${index + 1} ${item.cause || "Unknown cause"}${timestamps ? ` (${timestamps})` : ""}`;
      })
    : [];

  const confidenceRaw = data.confidence ?? report.confidence_score ?? 0;
  const confidence = Number(confidenceRaw);
  const confidenceText = Number.isFinite(confidence) ? `${(confidence * 100).toFixed(0)}%` : "N/A";
  const impactedServices = Array.isArray(understanding.impacted_services)
    ? understanding.impacted_services.join(", ")
    : "Not specified";
  const actionItems = Array.isArray(report.action_items) ? report.action_items : [];

  outputEl.innerHTML = `
    <div class="metrics">
      <div class="metric">
        <div class="metric-label">Severity</div>
        <div class="metric-value">${escapeHtml(understanding.severity || "Unknown")}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Confidence</div>
        <div class="metric-value">${escapeHtml(confidenceText)}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Incident Start</div>
        <div class="metric-value">${escapeHtml(understanding.start_time || "Unknown")}</div>
      </div>
    </div>

    <div class="cards">
      <article class="card">
        <h3>Executive Summary</h3>
        <p>${escapeHtml(report.executive_summary || "No summary available.")}</p>
        <span class="tag">Impacted Services: ${escapeHtml(impactedServices)}</span>
      </article>

      <article class="card">
        <h3>Impact</h3>
        <p>${escapeHtml(report.impact || "No impact details available.")}</p>
      </article>

      <article class="card">
        <h3>Root Cause</h3>
        <p>${escapeHtml(data.selected_root_cause || report.root_cause || "Not determined.")}</p>
      </article>

      <article class="card">
        <h3>Timeline</h3>
        ${renderList(timelineLines)}
      </article>

      <article class="card">
        <h3>Hypotheses Considered</h3>
        ${renderList(hypotheses)}
      </article>

      <article class="card">
        <h3>Action Items</h3>
        ${renderList(actionItems)}
      </article>
    </div>
  `;
}

async function runReconstruction() {
  statusEl.textContent = "Generating incident report...";
  statusEl.className = "status";
  runButton.disabled = true;

  try {
    const response = await fetch(getApiUrl("/api/incidents/reconstruct"), {
      method: "POST",
      body: buildFormData(),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Request failed.");
    }

    renderReport(data);
    statusEl.textContent = "Report generated successfully.";
    statusEl.className = "status success";
  } catch (error) {
    outputEl.innerHTML = `
      <article class="card">
        <h3>Request Error</h3>
        <p>${escapeHtml(error.message || String(error))}</p>
      </article>
    `;
    statusEl.textContent = "Could not generate report.";
    statusEl.className = "status error";
  } finally {
    runButton.disabled = false;
  }
}

runButton.addEventListener("click", runReconstruction);
