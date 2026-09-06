const state = {
  apiBase: localStorage.getItem("checkpointCopilotApiBase") || defaultApiBase(),
  dashboard: null,
  checkpoints: [],
  riskFilter: "all",
};

const elements = {
  apiBase: document.querySelector("#apiBase"),
  refreshButton: document.querySelector("#refreshButton"),
  riskFilter: document.querySelector("#riskFilter"),
  statusDot: document.querySelector("#statusDot"),
  connectionStatus: document.querySelector("#connectionStatus"),
  repoPath: document.querySelector("#repoPath"),
  metricsGrid: document.querySelector("#metricsGrid"),
  sessionList: document.querySelector("#sessionList"),
  checkpointList: document.querySelector("#checkpointList"),
  metricTemplate: document.querySelector("#metricTemplate"),
  sessionTemplate: document.querySelector("#sessionTemplate"),
  checkpointTemplate: document.querySelector("#checkpointTemplate"),
};

elements.apiBase.value = state.apiBase;
elements.refreshButton.addEventListener("click", loadDashboard);
elements.apiBase.addEventListener("change", () => {
  state.apiBase = normalizeApiBase(elements.apiBase.value);
  elements.apiBase.value = state.apiBase;
  localStorage.setItem("checkpointCopilotApiBase", state.apiBase);
  loadDashboard();
});
elements.riskFilter.addEventListener("change", () => {
  state.riskFilter = elements.riskFilter.value;
  renderSessions();
});

loadDashboard();

async function loadDashboard() {
  setStatus("loading", "Checking API", "");
  elements.refreshButton.disabled = true;

  try {
    const [health, dashboard, checkpoints] = await Promise.all([
      fetchJson("/api/health"),
      fetchJson("/api/dashboard"),
      fetchJson("/api/checkpoints"),
    ]);

    state.dashboard = dashboard;
    state.checkpoints = checkpoints;

    setStatus(
      "ok",
      health.status === "ok" ? "Connected" : "API responded",
      health.repo_path || "",
    );
    render();
  } catch (error) {
    state.dashboard = null;
    state.checkpoints = [];
    setStatus("error", "API unavailable", String(error.message || error));
    render();
  } finally {
    elements.refreshButton.disabled = false;
  }
}

async function fetchJson(path) {
  const response = await fetch(`${state.apiBase}${path}`);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function render() {
  renderMetrics();
  renderSessions();
  renderCheckpoints();
}

function renderMetrics() {
  elements.metricsGrid.textContent = "";

  if (!state.dashboard) {
    renderMetric("Total sessions", "-");
    renderMetric("Active", "-");
    renderMetric("Ready", "-");
    renderMetric("Needs review", "-");
    renderMetric("Checkpoints", "-");
    return;
  }

  renderMetric("Total sessions", state.dashboard.total_sessions);
  renderMetric("Active", state.dashboard.active_sessions);
  renderMetric("Ready", state.dashboard.ready_for_handoff);
  renderMetric("Needs review", state.dashboard.needs_review);
  renderMetric("Checkpoints", state.checkpoints.length);
}

function renderMetric(label, value) {
  const item = elements.metricTemplate.content.cloneNode(true);
  item.querySelector(".metric-label").textContent = label;
  item.querySelector(".metric-value").textContent = value;
  elements.metricsGrid.append(item);
}

function renderSessions() {
  elements.sessionList.textContent = "";

  const sessions = state.dashboard?.sessions || [];
  const filtered = sessions.filter(
    (session) => state.riskFilter === "all" || session.risk_level === state.riskFilter,
  );

  if (!state.dashboard) {
    renderMessage(elements.sessionList, "error-state", "Start the FastAPI backend on port 8000 to load sessions.");
    return;
  }

  if (!filtered.length) {
    renderMessage(elements.sessionList, "empty-state", "No sessions match this filter.");
    return;
  }

  filtered.forEach((session) => {
    const item = elements.sessionTemplate.content.cloneNode(true);
    const title = item.querySelector("h3");
    const badge = item.querySelector(".badge");
    const description = item.querySelector(".session-description");
    const facts = item.querySelector(".session-facts");
    const analysis = item.querySelector(".analysis-row");

    title.textContent = compactId(session.session_id);
    badge.textContent = session.status;
    badge.classList.add(session.status);
    description.textContent = session.description || session.first_prompt || "No session prompt captured.";

    appendFact(facts, "Risk", `${session.risk_level} (${formatScore(session.risk_score)})`, session.risk_level);
    appendFact(facts, "Alignment", formatScore(session.intent_alignment));
    appendFact(facts, "Checkpoints", session.checkpoint_count);
    appendFact(facts, "Files", session.files_changed.length);

    appendPill(analysis, session.handoff_summary);
    if (session.handoff_blockers.length) {
      appendPill(analysis, `Blockers: ${session.handoff_blockers.slice(0, 2).join(", ")}`);
    }
    if (session.unfinished_work.length) {
      appendPill(analysis, session.unfinished_work.slice(0, 2).join(", "));
    }

    elements.sessionList.append(item);
  });
}

function renderCheckpoints() {
  elements.checkpointList.textContent = "";

  if (!state.dashboard) {
    renderMessage(elements.checkpointList, "error-state", "Checkpoint data will appear when the API is reachable.");
    return;
  }

  if (!state.checkpoints.length) {
    renderMessage(elements.checkpointList, "empty-state", "No committed checkpoints returned.");
    return;
  }

  state.checkpoints.slice(0, 12).forEach((checkpoint) => {
    const item = elements.checkpointTemplate.content.cloneNode(true);
    item.querySelector("h3").textContent = compactId(checkpoint.id);
    item.querySelector("p").textContent = checkpoint.message || "No checkpoint message.";
    item.querySelector("span").textContent = formatDate(checkpoint.timestamp);
    elements.checkpointList.append(item);
  });
}

function appendFact(container, label, value, tone) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value;
  if (tone) {
    detail.className = tone;
  }
  wrapper.append(term, detail);
  container.append(wrapper);
}

function appendPill(container, value) {
  if (!value) {
    return;
  }
  const pill = document.createElement("span");
  pill.className = "analysis-pill";
  pill.textContent = value;
  container.append(pill);
}

function renderMessage(container, className, message) {
  const node = document.createElement("p");
  node.className = className;
  node.textContent = message;
  container.append(node);
}

function setStatus(kind, message, repoPath) {
  elements.statusDot.className = `status-dot ${kind === "ok" || kind === "error" ? kind : ""}`;
  elements.connectionStatus.textContent = message;
  elements.repoPath.textContent = repoPath;
}

function compactId(value) {
  if (!value) {
    return "unknown";
  }
  if (value.length <= 16) {
    return value;
  }
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function normalizeApiBase(value) {
  return (value || "http://localhost:8000").replace(/\/+$/, "");
}

function defaultApiBase() {
  const hostname = window.location.hostname || "localhost";
  return `${window.location.protocol}//${hostname}:8000`;
}

function formatScore(value) {
  if (typeof value !== "number") {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

function formatDate(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
