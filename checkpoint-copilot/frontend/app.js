const state = {
  apiBase: localStorage.getItem("checkpointCopilotApiBase") || defaultApiBase(),
  dashboard: null,
  checkpoints: [],
  handoffs: {},
  selectedSessionId: null,
  statusFilter: "all",
  riskFilter: "all",
};

const elements = {
  apiBase: document.querySelector("#apiBase"),
  repoPath: document.querySelector("#repoPath"),
  connectRepo: document.querySelector("#connectRepo"),
  refresh: document.querySelector("#refresh"),
  status: document.querySelector("#status"),
  statusFilter: document.querySelector("#statusFilter"),
  riskFilter: document.querySelector("#riskFilter"),
  totalSessions: document.querySelector("#totalSessions"),
  activeSessions: document.querySelector("#activeSessions"),
  readySessions: document.querySelector("#readySessions"),
  needsReview: document.querySelector("#needsReview"),
  sessionList: document.querySelector("#sessionList"),
  emptyState: document.querySelector("#emptyState"),
  sessionDetail: document.querySelector("#sessionDetail"),
  sessionMeta: document.querySelector("#sessionMeta"),
  sessionTitle: document.querySelector("#sessionTitle"),
  contextBadge: document.querySelector("#contextBadge"),
  contextPanel: document.querySelector("#contextPanel"),
  contextSummary: document.querySelector("#contextSummary"),
  contextWarnings: document.querySelector("#contextWarnings"),
  riskBadge: document.querySelector("#riskBadge"),
  riskMeter: document.querySelector("#riskMeter"),
  intentMeter: document.querySelector("#intentMeter"),
  handoffSummary: document.querySelector("#handoffSummary"),
  blockers: document.querySelector("#blockers"),
  suggestions: document.querySelector("#suggestions"),
  generateHandoff: document.querySelector("#generateHandoff"),
  copyHandoff: document.querySelector("#copyHandoff"),
  handoffOutput: document.querySelector("#handoffOutput"),
  checkpointCount: document.querySelector("#checkpointCount"),
  fileCount: document.querySelector("#fileCount"),
  todoCount: document.querySelector("#todoCount"),
  intentSummary: document.querySelector("#intentSummary"),
  checkpointList: document.querySelector("#checkpointList"),
};

elements.apiBase.value = state.apiBase;
elements.connectRepo.addEventListener("click", connectRepo);
elements.refresh.addEventListener("click", loadDashboard);
elements.apiBase.addEventListener("change", () => {
  state.apiBase = normalizeApiBase(elements.apiBase.value);
  elements.apiBase.value = state.apiBase;
  localStorage.setItem("checkpointCopilotApiBase", state.apiBase);
  loadDashboard();
});
elements.statusFilter.addEventListener("change", () => {
  state.statusFilter = elements.statusFilter.value;
  renderSessions();
});
elements.riskFilter.addEventListener("change", () => {
  state.riskFilter = elements.riskFilter.value;
  renderSessions();
});
elements.generateHandoff.addEventListener("click", generateSelectedHandoff);
elements.copyHandoff.addEventListener("click", copySelectedHandoff);

loadDashboard();

async function loadDashboard() {
  setStatus("Loading dashboard...");
  elements.refresh.disabled = true;

  try {
    const dashboard = await fetchJson("/api/dashboard");
    state.dashboard = dashboard;

    const [healthResult, checkpointsResult] = await Promise.allSettled([
      fetchJson("/api/health"),
      fetchJson("/api/checkpoints"),
    ]);

    state.checkpoints = checkpointsResult.status === "fulfilled" ? checkpointsResult.value : [];

    const repoPath =
      healthResult.status === "fulfilled" && healthResult.value.repo_path
        ? ` from ${healthResult.value.repo_path}`
        : "";
    if (healthResult.status === "fulfilled" && healthResult.value.repo_path) {
      elements.repoPath.value = healthResult.value.repo_path;
    }
    setStatus(`Connected${repoPath}`);

    const sessions = state.dashboard.sessions || [];
    if (!sessions.some((session) => session.session_id === state.selectedSessionId)) {
      state.selectedSessionId = sessions[0]?.session_id || null;
    }

    render();
  } catch (error) {
    state.dashboard = null;
    state.checkpoints = [];
    state.selectedSessionId = null;
    setStatus(`Could not load /api/dashboard: ${error.message || error}`, true);
    render();
  } finally {
    elements.refresh.disabled = false;
  }
}

async function connectRepo() {
  const repoPath = elements.repoPath.value.trim();
  if (!repoPath) {
    setStatus("Enter a repo path before connecting.", true);
    return;
  }

  elements.connectRepo.disabled = true;
  elements.connectRepo.textContent = "Connecting...";

  try {
    const health = await fetchJson("/api/repo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_path: repoPath }),
    });
    elements.repoPath.value = health.repo_path;
    state.selectedSessionId = null;
    state.handoffs = {};
    await loadDashboard();
  } catch (error) {
    setStatus(`Could not connect repo: ${error.message || error}`, true);
  } finally {
    elements.connectRepo.disabled = false;
    elements.connectRepo.textContent = "Connect";
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${state.apiBase}${path}`, options);
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = body.detail ? `: ${body.detail}` : "";
    } catch {
      detail = "";
    }
    throw new Error(`${path} returned ${response.status}${detail}`);
  }
  return response.json();
}

function render() {
  renderMetrics();
  renderSessions();
  renderDetail();
}

function renderMetrics() {
  const dashboard = state.dashboard;
  setText(elements.totalSessions, dashboard?.total_sessions ?? 0);
  setText(elements.activeSessions, dashboard?.active_sessions ?? 0);
  setText(elements.readySessions, dashboard?.ready_for_handoff ?? 0);
  setText(elements.needsReview, dashboard?.needs_review ?? 0);
}

function renderSessions() {
  elements.sessionList.textContent = "";

  const sessions = filteredSessions();
  if (!state.dashboard) {
    elements.sessionList.append(message("Start the FastAPI backend on port 8000 to load sessions."));
    return;
  }

  if (!sessions.length) {
    elements.sessionList.append(message("No sessions match the selected filters."));
    return;
  }

  sessions.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-button";
    if (session.session_id === state.selectedSessionId) {
      button.classList.add("selected");
    }

    const row = document.createElement("div");
    row.className = "session-row";
    const title = document.createElement("span");
    title.className = "session-title";
    title.textContent = session.description || session.first_prompt || compactId(session.session_id);
    const badge = document.createElement("span");
    badge.className = `badge risk-${session.risk_level}`;
    badge.textContent = session.risk_level;
    const contextBadge = document.createElement("span");
    contextBadge.className = `badge context-${session.context_status || "complete"}`;
    contextBadge.textContent = contextLabel(session);
    const badges = document.createElement("span");
    badges.className = "session-badges";
    badges.append(contextBadge, badge);
    row.append(title, badges);

    const subtitle = document.createElement("div");
    subtitle.className = "session-subtitle";
    subtitle.textContent = `${session.status} · ${session.checkpoint_count} checkpoint(s) · ${session.agent_type || "unknown agent"}`;

    button.append(row, subtitle);
    button.addEventListener("click", () => {
      state.selectedSessionId = session.session_id;
      renderSessions();
      renderDetail();
    });

    elements.sessionList.append(button);
  });
}

function renderDetail() {
  const session = selectedSession();

  elements.emptyState.classList.toggle("hidden", Boolean(session));
  elements.sessionDetail.classList.toggle("hidden", !session);

  if (!session) {
    return;
  }

  elements.sessionMeta.textContent = `${session.status} · ${session.agent_type || "unknown agent"} · ${formatDate(session.start_time)}`;
  elements.sessionTitle.textContent = session.description || session.first_prompt || compactId(session.session_id);
  elements.contextBadge.className = `badge context-badge context-${session.context_status || "complete"}`;
  elements.contextBadge.textContent = contextLabel(session);
  elements.riskBadge.className = `badge risk-${session.risk_level}`;
  elements.riskBadge.textContent = session.risk_level;
  elements.riskMeter.value = clampScore(session.risk_score);
  elements.intentMeter.value = clampScore(session.intent_alignment);
  elements.handoffSummary.textContent = session.handoff_summary || "No handoff summary available.";
  renderContext(session);

  renderList(elements.blockers, session.handoff_blockers, "No blockers detected.");
  renderList(elements.suggestions, session.handoff_suggestions, "No suggestions.");
  renderGeneratedHandoff(session);

  elements.checkpointCount.textContent = `${session.checkpoint_count} checkpoint(s)`;
  elements.fileCount.textContent = `${session.files_changed.length} file(s)`;
  elements.todoCount.textContent = `${session.todos_count} TODO(s)`;
  elements.intentSummary.textContent = session.intent_summary || "No intent summary available.";

  renderCheckpointList(session);
}

async function generateSelectedHandoff() {
  const session = selectedSession();
  if (!session) {
    return;
  }

  elements.generateHandoff.disabled = true;
  elements.generateHandoff.textContent = "Generating...";

  try {
    const handoff = await fetchJson(`/api/handoff/${encodeURIComponent(session.session_id)}`, {
      method: "POST",
    });
    state.handoffs[session.session_id] = formatGeneratedHandoff(handoff);
    renderGeneratedHandoff(session);
  } catch (error) {
    state.handoffs[session.session_id] = `Could not generate handoff: ${error.message || error}`;
    renderGeneratedHandoff(session);
  } finally {
    elements.generateHandoff.disabled = false;
    elements.generateHandoff.textContent = "Generate Handoff";
  }
}

async function copySelectedHandoff() {
  const session = selectedSession();
  const text = session ? state.handoffs[session.session_id] : "";
  if (!text) {
    return;
  }

  await navigator.clipboard.writeText(text);
  elements.copyHandoff.textContent = "Copied";
  setTimeout(() => {
    elements.copyHandoff.textContent = "Copy";
  }, 1200);
}

function renderGeneratedHandoff(session) {
  const text = state.handoffs[session.session_id] || "";
  elements.handoffOutput.textContent = text;
  elements.handoffOutput.classList.toggle("hidden", !text);
  elements.copyHandoff.classList.toggle("hidden", !text);
}

function formatGeneratedHandoff(handoff) {
  return `${handoff.handoff_summary}\n\n--- Resume Prompt ---\n\n${handoff.resume_prompt}`;
}

function renderCheckpointList(session) {
  elements.checkpointList.textContent = "";
  elements.checkpointList.classList.remove("timeline");

  const checkpoints = state.checkpoints.filter((checkpoint) => checkpoint.session_id === session.session_id);
  if (!checkpoints.length) {
    const text =
      session.checkpoint_count > 0
        ? "Checkpoint summary is available, but detailed checkpoint rows were not returned for this session."
        : "No checkpoints recorded for this session.";
    elements.checkpointList.append(message(text));
    return;
  }

  elements.checkpointList.classList.add("timeline");
  checkpoints.forEach((checkpoint) => {
    const item = document.createElement("article");
    item.className = "checkpoint timeline-item";

    const title = document.createElement("h4");
    title.textContent = checkpoint.message || "No checkpoint message.";
    const meta = document.createElement("span");
    meta.className = "checkpoint-meta";
    meta.textContent = formatDate(checkpoint.timestamp);
    const context = document.createElement("span");
    context.className = `badge context-${checkpoint.context_status || "complete"}`;
    context.textContent = contextLabel(checkpoint);
    const metaRow = document.createElement("div");
    metaRow.className = "checkpoint-meta-row";
    metaRow.append(meta, context);
    const commit = document.createElement("p");
    commit.textContent = compactId(checkpoint.id);

    item.append(metaRow, title, commit);
    elements.checkpointList.append(item);
  });
}

function renderContext(session) {
  const status = session.context_status || "complete";
  const complete = Boolean(session.context_complete);
  const warnings = session.context_warnings || [];
  elements.contextSummary.textContent = complete
    ? "Complete checkpoint context is available for this session."
    : `Context is ${status}; analysis uses available checkpoint fields and may miss redacted or unavailable details.`;
  renderList(
    elements.contextWarnings,
    warnings,
    complete ? "No context warnings." : "No additional context warnings returned."
  );
}

function filteredSessions() {
  const sessions = state.dashboard?.sessions || [];
  return sessions.filter((session) => {
    const statusMatches = state.statusFilter === "all" || session.status === state.statusFilter;
    const riskMatches = state.riskFilter === "all" || session.risk_level === state.riskFilter;
    return statusMatches && riskMatches;
  });
}

function selectedSession() {
  const sessions = state.dashboard?.sessions || [];
  return sessions.find((session) => session.session_id === state.selectedSessionId) || null;
}

function renderList(container, items, emptyText) {
  container.textContent = "";
  const values = items?.length ? items : [emptyText];
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    container.append(item);
  });
}

function message(text) {
  const node = document.createElement("p");
  node.className = "summary-text";
  node.textContent = text;
  return node;
}

function setStatus(text, isError = false) {
  elements.status.textContent = text;
  elements.status.classList.toggle("error", isError);
}

function setText(element, value) {
  element.textContent = String(value);
}

function contextLabel(item) {
  const status = item.context_status || "complete";
  if (item.context_complete || status === "complete") {
    return "Complete";
  }
  if (status === "redacted") {
    return "Limited/redacted";
  }
  if (status === "unavailable") {
    return "Unavailable";
  }
  return "Limited";
}

function normalizeApiBase(value) {
  return (value || defaultApiBase()).replace(/\/+$/, "");
}

function defaultApiBase() {
  const hostname = window.location.hostname || "localhost";
  return `${window.location.protocol}//${hostname}:8000`;
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

function clampScore(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}

function formatDate(value) {
  if (!value) {
    return "unknown time";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "unknown time";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
