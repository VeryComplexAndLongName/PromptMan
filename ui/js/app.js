const AUTH_TOKEN_STORAGE_KEY = "promptman.access_token";
const REFRESH_TOKEN_STORAGE_KEY = "promptman.refresh_token";

const state = {
  accessToken: localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "",
  refreshToken: localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY) || "",
  currentUser: null,
  selectedThreadId: null,
  threadMessages: [],
  threadAnalysisMessages: [],
  threadAnalysisReport: null,
  threadAnalysisLog: null,
  threadChartLabelMode: "smart",
  selectedPromptChainId: null,
  selectedPromptVersionNo: null,
  promptChainAnalysisPoints: [],
  promptOrchestratorPreview: null,
  promptTestRuns: [],
  selectedPromptTestRunId: null,
  settings: {},
  providerMeta: { providers: [], backends: [] },
  roleOptions: [],
};

const TOKEN_PLACEHOLDER = "********";

const $ = (id) => document.getElementById(id);

let refreshTokenInFlight = null;

async function refreshAccessToken() {
  if (!state.refreshToken) {
    throw new Error("Refresh token is missing");
  }

  if (!refreshTokenInFlight) {
    refreshTokenInFlight = (async () => {
      const response = await fetch("/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: state.refreshToken }),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `${response.status} ${response.statusText}`);
      }

      const payload = await response.json();
      state.accessToken = payload.access_token || "";
      state.refreshToken = payload.refresh_token || state.refreshToken;
      state.currentUser = payload.user || state.currentUser;
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, state.accessToken);
      localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, state.refreshToken);
      renderAuth();
      return payload;
    })().finally(() => {
      refreshTokenInFlight = null;
    });
  }

  return refreshTokenInFlight;
}

async function api(path, options = {}) {
  const requestOptions = { ...options };
  const skipAutoRefresh = Boolean(requestOptions.skipAutoRefresh);
  delete requestOptions.skipAutoRefresh;

  const execute = async () => {
    const headers = { "Content-Type": "application/json", ...(requestOptions.headers || {}) };
    if (state.accessToken) {
      headers.Authorization = `Bearer ${state.accessToken}`;
    }
    const response = await fetch(path, { ...requestOptions, headers });
    return response;
  };

  let response = await execute();

  const isRefreshCall = path === "/v1/auth/refresh";
  const hasRefresh = Boolean(state.refreshToken);
  if (response.status === 401 && !skipAutoRefresh && !isRefreshCall && hasRefresh) {
    try {
      await refreshAccessToken();
      response = await execute();
    } catch (_refreshError) {
      logout();
      throw new Error("Session expired. Please sign in again.");
    }
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sanitizeHtml(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div>${html}</div>`, "text/html");
  const root = doc.body.firstElementChild;
  if (!root) return "";

  root.querySelectorAll("script,style,iframe,object,embed,link").forEach((node) => node.remove());
  root.querySelectorAll("*").forEach((node) => {
    for (const attr of [...node.attributes]) {
      const name = attr.name.toLowerCase();
      const value = attr.value || "";
      if (name.startsWith("on")) {
        node.removeAttribute(attr.name);
      }
      if ((name === "href" || name === "src") && value.trim().toLowerCase().startsWith("javascript:")) {
        node.removeAttribute(attr.name);
      }
    }
  });
  return root.innerHTML;
}

function renderMarkdown(targetEl, rawText) {
  const content = String(rawText || "");
  if (!content.trim()) {
    targetEl.innerHTML = "";
    return;
  }

  if (typeof window.marked?.parse === "function") {
    const html = window.marked.parse(content);
    targetEl.innerHTML = sanitizeHtml(html);
    return;
  }

  targetEl.textContent = content;
}

function setActiveTab(targetId) {
  document.querySelectorAll(".tab").forEach((tabButton) => {
    const isActive = tabButton.dataset.target === targetId;
    tabButton.classList.toggle("is-active", isActive);
    tabButton.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== targetId;
  });
}

function toggleStatusMenu(forceOpen) {
  const menu = $("statusMenu");
  const isOpen = typeof forceOpen === "boolean" ? forceOpen : menu.hidden;
  menu.hidden = !isOpen;
  $("statusToggleBtn").setAttribute("aria-expanded", isOpen ? "true" : "false");
}

function setStatusMenuTab(targetId) {
  document.querySelectorAll(".status-tab").forEach((tabButton) => {
    const isActive = tabButton.dataset.statusTarget === targetId;
    tabButton.classList.toggle("is-active", isActive);
    tabButton.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  document.querySelectorAll(".status-panel").forEach((panel) => {
    panel.hidden = panel.id !== targetId;
  });
}

function setSettingsSubTab(targetId) {
  document.querySelectorAll(".settings-tab").forEach((tabButton) => {
    const isActive = tabButton.dataset.settingsTarget === targetId;
    tabButton.classList.toggle("is-active", isActive);
    tabButton.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  document.querySelectorAll(".settings-panel").forEach((panel) => {
    panel.hidden = panel.id !== targetId;
  });
}

function updateSettingsTabVisibility() {
  const settingsTab = $("tabSettings");
  const isAdmin = state.currentUser?.role === "admin";
  settingsTab.hidden = !isAdmin;
  if (!isAdmin && document.querySelector(".tab.is-active")?.dataset.target === "panelSettings") {
    setActiveTab("panelCreateThread");
  }
}

function renderAuth() {
  const authenticated = Boolean(state.currentUser);
  $("userStatusCompact").textContent = authenticated ? state.currentUser.username : "Guest";
  $("userStatusText").textContent = authenticated
    ? `${state.currentUser.username} (${state.currentUser.role})`
    : "Not authenticated";
  $("statusDot").classList.toggle("online", authenticated);
  updateSettingsTabVisibility();
}

async function loadAppVersion() {
  try {
    const payload = await api("/v1/version", { headers: {} });
    const version = payload?.version;
    $("productVersion").textContent = typeof version === "string" && version ? `v${version}` : "v0.0.0";
  } catch (_error) {
    $("productVersion").textContent = "vunknown";
  }
}

function renderThreads(items) {
  const list = $("threadsList");
  list.innerHTML = "";
  for (const thread of items) {
    const li = document.createElement("li");
    li.innerHTML = `
      <button class="thread-item-btn ${state.selectedThreadId === thread.id ? "is-selected" : ""}" data-id="${thread.id}">
        <strong>${escapeHtml(thread.title)}</strong>
        <span class="muted">${escapeHtml(thread.project)} · ${escapeHtml(thread.source)}</span>
      </button>
    `;
    list.appendChild(li);
  }

  list.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.selectedThreadId = Number(btn.dataset.id);
      await loadThreadDetails();
    });
  });
}

function renderMessages(items) {
  const list = $("messagesList");
  list.innerHTML = "";
  for (const message of items) {
    const li = document.createElement("li");
    li.className = "message-item";
    li.innerHTML = `
      <div class="message-head">
        <strong>${message.seq_no}. ${escapeHtml(message.role)}</strong>
        <span class="muted">${escapeHtml(message.timestamp)}</span>
      </div>
      <div class="message-content"></div>
    `;
    const contentNode = li.querySelector(".message-content");
    renderMarkdown(contentNode, message.content);
    list.appendChild(li);
  }
}

function renderPromptChains(items) {
  const list = $("promptChainsList");
  list.innerHTML = "";
  for (const chain of items) {
    const li = document.createElement("li");
    li.innerHTML = `
      <button class="thread-item-btn ${state.selectedPromptChainId === chain.id ? "is-selected" : ""}" data-id="${chain.id}">
        <strong>${escapeHtml(chain.name)}</strong>
        <span class="muted">${escapeHtml(chain.project)} · ${escapeHtml(chain.updated_at)}</span>
      </button>
    `;
    list.appendChild(li);
  }

  list.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.selectedPromptChainId = Number(btn.dataset.id);
      state.selectedPromptVersionNo = null;
      state.promptChainAnalysisPoints = [];
      await loadPromptChainDetails();
    });
  });
}

function renderPromptVersions(items) {
  const list = $("promptVersionsList");
  list.innerHTML = "";
  for (const version of items) {
    const li = document.createElement("li");
    li.innerHTML = `
      <button class="thread-item-btn ${state.selectedPromptVersionNo === version.version_no ? "is-selected" : ""}" data-version="${version.version_no}">
        <strong>v${version.version_no}</strong>
        <span class="muted">${escapeHtml(version.created_at)} · ${escapeHtml(version.created_by_username)}</span>
      </button>
    `;
    list.appendChild(li);
  }

  list.querySelectorAll("button[data-version]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.selectedPromptVersionNo = Number(btn.dataset.version);
      await analyzePromptVersion();
      await loadPromptVersionDetails();
      await refreshPromptTests();
      renderPromptVersions(items);
    });
  });
}

function renderPromptTestRuns(items) {
  const list = $("promptTestRunsList");
  list.innerHTML = "";
  for (const run of items) {
    const li = document.createElement("li");
    li.innerHTML = `
      <button class="thread-item-btn ${state.selectedPromptTestRunId === run.id ? "is-selected" : ""}" data-test-run-id="${escapeHtml(run.id)}">
        <strong>${escapeHtml(run.created_at)}</strong>
        <span class="muted">v${run.version_no} · ${escapeHtml(run.llm?.provider || "")}/${escapeHtml(run.llm?.model || "")}</span>
      </button>
    `;
    list.appendChild(li);
  }

  list.querySelectorAll("button[data-test-run-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedPromptTestRunId = btn.dataset.testRunId;
      const row = state.promptTestRuns.find((item) => item.id === state.selectedPromptTestRunId);
      if (row) {
        renderPromptTestRunDetails(row);
      }
      renderPromptTestRuns(state.promptTestRuns);
    });
  });
}

function renderPromptTestRunPlaceholder(message = "Run a test to see full prompt logs and breakdown.") {
  $("promptTestRunDetails").innerHTML = `<p class="analysis-placeholder">${escapeHtml(message)}</p>`;
}

function renderPromptTestRunDetails(run) {
  const llm = run.llm || {};
  const tokenUsage = run.token_usage || {};
  const rag = run.rag || {};
  const security = run.security || {};
  $("promptTestRunDetails").innerHTML = `
    <div class="analysis-grid">
      <article class="analysis-card">
        <p class="analysis-label">Run id</p>
        <p class="analysis-value">${escapeHtml(String(run.id || ""))}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">LLM</p>
        <p class="analysis-value">${escapeHtml(String(llm.provider || ""))}/${escapeHtml(String(llm.model || ""))}</p>
        <p class="analysis-value-small">backend: ${escapeHtml(String(llm.backend || ""))} · invoked: ${llm.llm_invoked ? "yes" : "no"}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Latency</p>
        <p class="analysis-value">${Number(run.latency_ms || 0).toFixed(2)} ms</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Token usage</p>
        <p class="analysis-value">${Number(tokenUsage.total_tokens || 0)}</p>
        <p class="analysis-value-small">prompt: ${Number(tokenUsage.prompt_tokens || 0)}, completion: ${Number(tokenUsage.completion_tokens || 0)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">RAG</p>
        <p class="analysis-value">${rag.enabled ? "enabled" : "disabled"}</p>
        <p class="analysis-value-small">top_k: ${Number(rag.top_k || 0)} · chunks: ${Array.isArray(rag.chunks) ? rag.chunks.length : 0}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Security risk</p>
        <p class="analysis-value">inj ${Number(security.injection_risk || 0).toFixed(1)} · contra ${Number(security.contradiction_risk || 0).toFixed(1)}</p>
        <p class="analysis-value-small">ambiguity: ${Number(security.ambiguity_risk || 0).toFixed(1)}</p>
      </article>
    </div>

    <article class="analysis-card">
      <p class="analysis-label">Prompt with RAG</p>
      <pre class="json-box">${escapeHtml(String(run.prompt_with_rag || ""))}</pre>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">Full prompt</p>
      <pre class="json-box">${escapeHtml(String(run.full_prompt || ""))}</pre>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">Fixed part</p>
      <pre class="json-box">${escapeHtml(String(run.fixed_part || ""))}</pre>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">Semi-fixed part</p>
      <pre class="json-box">${escapeHtml(String(run.semi_fixed_part || ""))}</pre>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">Variable part</p>
      <pre class="json-box">${escapeHtml(String(run.variable_part || ""))}</pre>
      <p class="analysis-value-small">variables: ${escapeHtml((run.variables || []).join(", "))}</p>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">LLM response</p>
      <pre class="json-box">${escapeHtml(String(run.llm_response || ""))}</pre>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">LLM error</p>
      <pre class="json-box">${escapeHtml(String(run.llm_error || ""))}</pre>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">Security markers</p>
      <pre class="json-box">${escapeHtml(Array.isArray(security.markers) ? security.markers.join(", ") : "")}</pre>
    </article>

    <article class="analysis-card">
      <p class="analysis-label">RAG chunks</p>
      <pre class="json-box">${escapeHtml(Array.isArray(rag.chunks) ? rag.chunks.join("\n\n---\n\n") : "")}</pre>
    </article>
  `;
}

function renderPromptAnalysisTable(points) {
  const tbody = $("promptChainMetricsTable").querySelector("tbody");
  tbody.innerHTML = "";
  for (const point of points) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>v${point.version_no}</td>
      <td>${point.tokens}</td>
      <td>${point.reliability.toFixed(2)}</td>
      <td>${point.cache_hit_probability.toFixed(2)}</td>
      <td>${renderRiskCell(point.injection_risk)}</td>
      <td>${renderRiskCell(point.contradiction_risk)}</td>
      <td>${renderRiskCell(point.ambiguity_risk)}</td>
      <td>${point.delta_tokens}</td>
      <td>${point.delta_reliability.toFixed(2)}</td>
      <td>${point.delta_cache_hit.toFixed(2)}</td>
      <td>${Number(point.delta_injection_risk || 0).toFixed(2)}</td>
      <td>${Number(point.delta_contradiction_risk || 0).toFixed(2)}</td>
      <td>${Number(point.delta_ambiguity_risk || 0).toFixed(2)}</td>
    `;
    tbody.appendChild(row);
  }
}

function renderPromptTrendChart(points) {
  const container = $("promptChainTrendChart");
  container.innerHTML = "";
  if (!points.length) return;

  const width = 720;
  const height = 180;
  const padding = 26;

  const tokens = points.map((p) => p.tokens);
  const reliabilities = points.map((p) => p.reliability);
  const cacheHits = points.map((p) => p.cache_hit_probability);

  const tokenMax = Math.max(...tokens, 1);
  const lineX = (i) => padding + (i * (width - padding * 2)) / Math.max(1, points.length - 1);
  const lineY = (value, max) => height - padding - (value / Math.max(1, max)) * (height - padding * 2);

  const tokenLine = points.map((p, i) => `${lineX(i)},${lineY(p.tokens, tokenMax)}`).join(" ");
  const relLine = points.map((p, i) => `${lineX(i)},${lineY(p.reliability, 100)}`).join(" ");
  const cacheLine = points.map((p, i) => `${lineX(i)},${lineY(p.cache_hit_probability, 100)}`).join(" ");
  const injectionLine = points.map((p, i) => `${lineX(i)},${lineY(Number(p.injection_risk || 0), 100)}`).join(" ");
  const contradictionLine = points.map((p, i) => `${lineX(i)},${lineY(Number(p.contradiction_risk || 0), 100)}`).join(" ");
  const ambiguityLine = points.map((p, i) => `${lineX(i)},${lineY(Number(p.ambiguity_risk || 0), 100)}`).join(" ");

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="160" aria-label="Prompt version trends chart">
      <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#cbd5e1" stroke-width="1" />
      <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${height - padding}" stroke="#cbd5e1" stroke-width="1" />
      <polyline fill="none" stroke="#2563eb" stroke-width="2.2" points="${tokenLine}" />
      <polyline fill="none" stroke="#0f766e" stroke-width="2.2" points="${relLine}" />
      <polyline fill="none" stroke="#9333ea" stroke-width="2.2" points="${cacheLine}" />
      <polyline fill="none" stroke="#ef4444" stroke-width="2" stroke-dasharray="5 4" points="${injectionLine}" />
      <polyline fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="5 4" points="${contradictionLine}" />
      <polyline fill="none" stroke="#64748b" stroke-width="2" stroke-dasharray="5 4" points="${ambiguityLine}" />
      <text x="${padding}" y="16" fill="#2563eb" font-size="12">Tokens</text>
      <text x="${padding + 70}" y="16" fill="#0f766e" font-size="12">Reliability %</text>
      <text x="${padding + 190}" y="16" fill="#9333ea" font-size="12">Cache hit %</text>
      <text x="${padding + 300}" y="16" fill="#ef4444" font-size="12">Injection</text>
      <text x="${padding + 370}" y="16" fill="#f59e0b" font-size="12">Contradiction</text>
      <text x="${padding + 480}" y="16" fill="#64748b" font-size="12">Ambiguity</text>
    </svg>
  `;
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatSigned(value, digits = 2) {
  const num = Number(value || 0);
  const fixed = num.toFixed(digits);
  return num > 0 ? `+${fixed}` : fixed;
}

function getRiskLevel(value) {
  const score = Number(value || 0);
  if (score >= 70) return "high";
  if (score >= 35) return "medium";
  return "low";
}

function renderRiskCell(value) {
  const score = Number(value || 0);
  const level = getRiskLevel(score);
  const alpha = (0.12 + (Math.min(100, Math.max(0, score)) / 100) * 0.42).toFixed(2);
  return `<span class="risk-chip risk-${level}" style="--risk-alpha:${alpha}">${score.toFixed(2)}</span>`;
}

function estimateTokensFromText(content) {
  const text = String(content || "").trim();
  if (!text) return 0;
  const words = text.match(/[A-Za-z0-9_\u00C0-\u024F\u0400-\u04FF]+/g) || [];
  const punctuation = text.match(/[.,!?;:()[\]{}<>"'`~@#$%^&*+=\\/|-]/g) || [];
  const nonAscii = text.match(/[^\x00-\x7F]/g) || [];
  const estimate = words.length + punctuation.length * 0.35 + nonAscii.length * 0.25;
  return Math.max(1, Math.round(estimate));
}

function computeSecurityMetrics(text) {
  const value = String(text || "").trim().toLowerCase();
  const injectionMarkers = [
    "ignore previous",
    "disregard above",
    "ignore all previous",
    "ignore prior",
    "system prompt",
    "hidden prompt",
    "developer mode",
    "reveal hidden",
    "reveal prompt",
    "jailbreak",
    "bypass",
    "do anything now",
    "игнорируй предыдущ",
    "проигнорируй предыдущ",
    "не следуй предыдущ",
    "системный промпт",
    "скрытый промпт",
    "раскрой систем",
    "режим разработчика",
    "джейлбрейк",
    "обойди ограничени",
  ];
  const contradictionPairs = [
    ["always", "never"],
    ["must", "optional"],
    ["strict", "flexible"],
    ["only", "any"],
    ["всегда", "никогда"],
    ["должен", "необязательно"],
    ["обязательно", "опционально"],
    ["только", "любой"],
    ["строго", "гибко"],
  ];
  const ambiguityMarkers = [
    "maybe",
    "possibly",
    "etc",
    "somehow",
    "approximately",
    "around",
    "perhaps",
    "kind of",
    "more or less",
    "может",
    "возможно",
    "как-нибудь",
    "примерно",
    "около",
    "и т.д",
    "и тп",
    "по возможности",
  ];

  let injectionHits = 0;
  const markers = [];
  for (const marker of injectionMarkers) {
    if (value.includes(marker)) {
      injectionHits += 1;
      markers.push(marker);
    }
  }

  let contradictionHits = 0;
  for (const [left, right] of contradictionPairs) {
    if (value.includes(left) && value.includes(right)) {
      contradictionHits += 1;
      markers.push(`${left}<->${right}`);
    }
  }

  let ambiguityHits = 0;
  for (const marker of ambiguityMarkers) {
    ambiguityHits += Math.max(0, value.split(marker).length - 1);
  }

  return {
    injection_risk: injectionHits ? Math.min(100, Number((20 + injectionHits * 18).toFixed(2))) : 0,
    contradiction_risk: contradictionHits ? Math.min(100, Number((15 + contradictionHits * 22).toFixed(2))) : 0,
    ambiguity_risk: ambiguityHits ? Math.min(100, Number((10 + ambiguityHits * 9).toFixed(2))) : 0,
    markers,
  };
}

const THREAD_CHART_LABEL_MODE_OPTIONS = [
  { key: "all", title: "Labels: All" },
  { key: "smart", title: "Labels: Smart" },
  { key: "off", title: "Labels: Off" },
];

function updateThreadChartLabelModeButton() {
  const button = $("threadChartLabelModeBtn");
  if (!button) return;
  const option = THREAD_CHART_LABEL_MODE_OPTIONS.find((item) => item.key === state.threadChartLabelMode);
  button.textContent = option?.title || "Labels: Smart";
}

function cycleThreadChartLabelMode() {
  const currentIndex = THREAD_CHART_LABEL_MODE_OPTIONS.findIndex((item) => item.key === state.threadChartLabelMode);
  const next = THREAD_CHART_LABEL_MODE_OPTIONS[(currentIndex + 1) % THREAD_CHART_LABEL_MODE_OPTIONS.length];
  state.threadChartLabelMode = next.key;
  updateThreadChartLabelModeButton();
  if (state.threadAnalysisReport && state.threadAnalysisMessages.length) {
    renderThreadAnalysis(state.threadAnalysisReport, state.threadAnalysisMessages);
  }
}

function renderThreadTrendChart(messages, securityTrend = []) {
  const chartEl = $("threadTrendChart");
  if (!chartEl) return;

  chartEl.innerHTML = "";
  if (!messages.length) return;

  const width = 760;
  const height = 190;
  const padding = 26;

  let userCumulative = 0;
  let toolCumulative = 0;
  const points = messages.map((msg, index) => {
    const role = String(msg.role || "").toLowerCase();
    if (role === "user") userCumulative += 1;
    if (role === "tool") toolCumulative += 1;

    const chars = String(msg.content || "").length;
    const tokens = estimateTokensFromText(msg.content || "");
    return {
      index,
      chars,
      tokens,
      userCumulative,
      toolCumulative,
    };
  });

  const charsMax = Math.max(...points.map((p) => p.chars), 1);
  const tokensMax = Math.max(...points.map((p) => p.tokens), 1);
  const turnMax = Math.max(...points.map((p) => Math.max(p.userCumulative, p.toolCumulative)), 1);
  const securityMax = Math.max(
    1,
    ...securityTrend.map((p) => Math.max(Number(p.injection_risk || 0), Number(p.contradiction_risk || 0), Number(p.ambiguity_risk || 0))),
  );
  const x = (i) => padding + (i * (width - padding * 2)) / Math.max(1, points.length - 1);
  const y = (value, max) => height - padding - (value / Math.max(1, max)) * (height - padding * 2);

  const charsLine = points.map((p, i) => `${x(i)},${y(p.chars, charsMax)}`).join(" ");
  const tokensLine = points.map((p, i) => `${x(i)},${y(p.tokens, tokensMax)}`).join(" ");
  const userLine = points.map((p, i) => `${x(i)},${y(p.userCumulative, turnMax)}`).join(" ");
  const toolLine = points.map((p, i) => `${x(i)},${y(p.toolCumulative, turnMax)}`).join(" ");
  const injectionLine = securityTrend.map((p, i) => `${x(i)},${y(Number(p.injection_risk || 0), securityMax)}`).join(" ");
  const contradictionLine = securityTrend.map((p, i) => `${x(i)},${y(Number(p.contradiction_risk || 0), securityMax)}`).join(" ");
  const ambiguityLine = securityTrend.map((p, i) => `${x(i)},${y(Number(p.ambiguity_risk || 0), securityMax)}`).join(" ");

  const labelMode = state.threadChartLabelMode;
  const labelStep = labelMode === "all" ? 1 : Math.max(1, Math.ceil(points.length / 14));
  const charsLabels = points
    .map((p, i) => {
      const shouldLabel = labelMode !== "off" && (i === points.length - 1 || i % labelStep === 0);
      if (!shouldLabel) return "";
      const px = x(i);
      const py = y(p.chars, charsMax);
      return `<text x="${px + 4}" y="${py - 6}" fill="#1d4ed8" font-size="10">${p.chars}</text>`;
    })
    .join("");

  const tokensLabels = points
    .map((p, i) => {
      const shouldLabel = labelMode !== "off" && (i === points.length - 1 || i % labelStep === 0);
      if (!shouldLabel) return "";
      const px = x(i);
      const py = y(p.tokens, tokensMax);
      return `<text x="${px + 4}" y="${py + 12}" fill="#0f766e" font-size="10">${p.tokens}</text>`;
    })
    .join("");

  chartEl.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="170" aria-label="Thread trend chart">
      <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#cbd5e1" stroke-width="1" />
      <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${height - padding}" stroke="#cbd5e1" stroke-width="1" />
      <polyline fill="none" stroke="#2563eb" stroke-width="2.2" points="${charsLine}" />
      <polyline fill="none" stroke="#0f766e" stroke-width="2.2" points="${tokensLine}" />
      <polyline fill="none" stroke="#d97706" stroke-width="2.2" points="${userLine}" />
      <polyline fill="none" stroke="#7c3aed" stroke-width="2.2" points="${toolLine}" />
      <polyline fill="none" stroke="#ef4444" stroke-width="2" stroke-dasharray="5 4" points="${injectionLine}" />
      <polyline fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="5 4" points="${contradictionLine}" />
      <polyline fill="none" stroke="#64748b" stroke-width="2" stroke-dasharray="5 4" points="${ambiguityLine}" />
      ${charsLabels}
      ${tokensLabels}
      <text x="${padding}" y="16" fill="#2563eb" font-size="12">Chars / message</text>
      <text x="${padding + 120}" y="16" fill="#0f766e" font-size="12">Tokens / message</text>
      <text x="${padding + 250}" y="16" fill="#d97706" font-size="12">User turns (cumulative)</text>
      <text x="${padding + 440}" y="16" fill="#7c3aed" font-size="12">Tool turns (cumulative)</text>
      <text x="${padding + 620}" y="16" fill="#ef4444" font-size="12">Inj/Contra/Amb</text>
    </svg>
  `;
}

function renderThreadAnalysisPlaceholder(message = "Click Analyze to build a report for this thread.") {
  state.threadAnalysisReport = null;
  state.threadAnalysisMessages = [];
  $("analyzeOutput").innerHTML = `<p class="analysis-placeholder">${escapeHtml(message)}</p>`;
}

function renderThreadAnalysisLogPlaceholder(message = "Run Prompt Orchestrator improve + analyze to inspect the improvement log.") {
  state.threadAnalysisLog = null;
  $("threadAnalysisLog").innerHTML = `<p class="analysis-placeholder">${escapeHtml(message)}</p>`;
}

function renderThreadAnalysisLog(logPayload) {
  state.threadAnalysisLog = logPayload;
  const generatedAt = logPayload.generated_at ? new Date(logPayload.generated_at) : null;
  const analysis = logPayload.analysis || {};
  const logText = String(logPayload.log_text || "");

  $("threadAnalysisLog").innerHTML = `
    <div class="analysis-grid">
      <article class="analysis-card">
        <p class="analysis-label">Generated at</p>
        <p class="analysis-value">${generatedAt && Number.isFinite(generatedAt.getTime()) ? escapeHtml(generatedAt.toLocaleString()) : escapeHtml(String(logPayload.generated_at || ""))}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Log path</p>
        <p class="analysis-value-small">${escapeHtml(logPayload.log_path || "")}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Turns</p>
        <p class="analysis-value">${Number(analysis.turns || 0)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Total chars</p>
        <p class="analysis-value">${Number(analysis.total_chars || 0)}</p>
      </article>
    </div>
    <div class="table-wrap">
      <pre class="log-output">${escapeHtml(logText)}</pre>
    </div>
  `;
}

function renderThreadAnalysis(report, messages = []) {
  const turns = Number(report.turns || 0);
  const totalChars = Number(report.total_chars || 0);
  const avgChars = turns ? (totalChars / turns).toFixed(1) : "0.0";
  const totalTokens = messages.reduce((sum, msg) => sum + estimateTokensFromText(msg.content), 0);

  const userChars = messages
    .filter((msg) => String(msg.role || "").toLowerCase() === "user")
    .reduce((sum, msg) => sum + String(msg.content || "").length, 0);
  const toolChars = messages
    .filter((msg) => String(msg.role || "").toLowerCase() === "tool")
    .reduce((sum, msg) => sum + String(msg.content || "").length, 0);
  const userTokens = Math.max(0, Math.round(userChars / 4));
  const toolTokens = Math.max(0, Math.round(toolChars / 4));
  const securityByMessage = messages.map((msg, index) => ({
    seq_no: Number(msg.seq_no || index + 1),
    ...computeSecurityMetrics(msg.content || ""),
  }));
  const totalSecurity = computeSecurityMetrics(messages.map((msg) => String(msg.content || "")).join("\n"));

  const roleRows = [
    { role: "user", count: Number(report.user_turns || 0) },
    { role: "assistant", count: Number(report.assistant_turns || 0) },
    { role: "system", count: Number(report.system_turns || 0) },
    { role: "tool", count: Number(report.tool_turns || 0) },
  ];

  const startedAt = report.started_at ? new Date(report.started_at) : null;
  const endedAt = report.ended_at ? new Date(report.ended_at) : null;
  const durationSeconds =
    startedAt && endedAt && Number.isFinite(startedAt.getTime()) && Number.isFinite(endedAt.getTime())
      ? Math.max(0, (endedAt.getTime() - startedAt.getTime()) / 1000)
      : null;

  const bars = roleRows
    .map((row) => {
      const share = turns ? (row.count / turns) * 100 : 0;
      return `
        <div class="role-bar-row">
          <strong>${escapeHtml(row.role)}</strong>
          <div class="role-bar-track"><div class="role-bar-fill" style="width:${share.toFixed(2)}%"></div></div>
          <span>${row.count} (${share.toFixed(1)}%)</span>
        </div>
      `;
    })
    .join("");

  const tableRows = roleRows
    .map((row) => {
      const share = turns ? (row.count / turns) * 100 : 0;
      return `<tr><td>${escapeHtml(row.role)}</td><td>${row.count}</td><td>${share.toFixed(2)}%</td></tr>`;
    })
    .join("");

  $("analyzeOutput").innerHTML = `
    <div class="analysis-grid">
      <article class="analysis-card">
        <p class="analysis-label">Turns</p>
        <p class="analysis-value">${turns}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Total chars</p>
        <p class="analysis-value">${totalChars}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Avg chars / turn</p>
        <p class="analysis-value">${avgChars}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Estimated tokens (thread)</p>
        <p class="analysis-value">${totalTokens}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Duration</p>
        <p class="analysis-value">${durationSeconds === null ? "n/a" : `${durationSeconds.toFixed(1)}s`}</p>
        <p class="analysis-value-small">${escapeHtml(report.started_at || "")}${report.started_at && report.ended_at ? " -> " : ""}${escapeHtml(report.ended_at || "")}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">User content</p>
        <p class="analysis-value">${userChars} chars</p>
        <p class="analysis-value-small">~${userTokens} tokens</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Tool content</p>
        <p class="analysis-value">${toolChars} chars</p>
        <p class="analysis-value-small">~${toolTokens} tokens</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Injection risk</p>
        <p class="analysis-value">${Number(totalSecurity.injection_risk || 0).toFixed(2)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Contradiction risk</p>
        <p class="analysis-value">${Number(totalSecurity.contradiction_risk || 0).toFixed(2)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Ambiguity risk</p>
        <p class="analysis-value">${Number(totalSecurity.ambiguity_risk || 0).toFixed(2)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Security markers (thread)</p>
        <p class="analysis-value-small">${escapeHtml((totalSecurity.markers || []).join(", ") || "-")}</p>
      </article>
    </div>

    <div id="threadTrendChart" class="trend-chart"></div>
    <p class="chart-caption">Trend by message position: chars/tokens per message, plus cumulative user/tool turns.</p>

    <article class="analysis-card">
      <p class="analysis-label">Role distribution</p>
      <div class="role-bars">${bars}</div>
    </article>

    <div class="table-wrap">
      <table class="metrics-table">
        <thead>
          <tr>
            <th>Role</th>
            <th>Turns</th>
            <th>Share</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>

    <div class="table-wrap">
      <table class="metrics-table">
        <thead>
          <tr>
            <th>Message #</th>
            <th>Injection risk</th>
            <th>Contradiction risk</th>
            <th>Ambiguity risk</th>
            <th>Markers</th>
          </tr>
        </thead>
        <tbody>
          ${securityByMessage
            .map(
              (item) => `<tr><td>${item.seq_no}</td><td>${renderRiskCell(item.injection_risk)}</td><td>${renderRiskCell(item.contradiction_risk)}</td><td>${renderRiskCell(item.ambiguity_risk)}</td><td>${escapeHtml((item.markers || []).join(", ") || "-")}</td></tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>

    <p class="analysis-note">Thread security metrics are computed heuristically from message content (injection/contradiction/ambiguity).</p>
  `;

  renderThreadTrendChart(messages, securityByMessage);
}

function renderPromptVersionAnalysis(report, point = null) {
  const tokens = Number(report.tokens || 0);
  const reliability = Number(report.reliability || 0);
  const cacheHit = Number(report.cache_hit_probability || 0);
  const deltaTokensText = point ? formatSigned(point.delta_tokens, 0) : "-";
  const deltaReliabilityText = point ? formatSigned(point.delta_reliability, 2) : "-";
  const deltaCacheHitText = point ? formatSigned(point.delta_cache_hit, 2) : "-";

  $("promptVersionAnalysis").innerHTML = `
    <div class="analysis-grid">
      <article class="analysis-card">
        <p class="analysis-label">Version</p>
        <p class="analysis-value">v${Number(report.version_no || 0)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Tokens</p>
        <p class="analysis-value">${tokens}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Reliability</p>
        <p class="analysis-value">${formatPercent(reliability)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Cache hit probability</p>
        <p class="analysis-value">${formatPercent(cacheHit)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Injection risk</p>
        <p class="analysis-value">${Number(report.injection_risk || 0).toFixed(2)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Contradiction risk</p>
        <p class="analysis-value">${Number(report.contradiction_risk || 0).toFixed(2)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Ambiguity risk</p>
        <p class="analysis-value">${Number(report.ambiguity_risk || 0).toFixed(2)}</p>
      </article>
    </div>

    <div class="table-wrap">
      <table class="metrics-table">
        <thead>
          <tr>
            <th>Tokens</th>
            <th>Reliability</th>
            <th>Cache hit %</th>
            <th>Delta tokens</th>
            <th>Delta reliability</th>
            <th>Delta cache %</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>${tokens}</td>
            <td>${reliability.toFixed(2)}</td>
            <td>${cacheHit.toFixed(2)}</td>
            <td>${deltaTokensText}</td>
            <td>${deltaReliabilityText}</td>
            <td>${deltaCacheHitText}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="analysis-note">Delta values are relative to the previous version in the same chain.</p>
    <p class="analysis-note">Security markers: ${escapeHtml((report.security_markers || []).join(", ")) || "-"}</p>
  `;
}

function renderPromptOrchestratorPreviewPlaceholder(message = "Select an action from Analyze to inspect an orchestrated prompt preview.") {
  state.promptOrchestratorPreview = null;
  $("promptOrchestratorPreview").innerHTML = `<p class="analysis-placeholder">${escapeHtml(message)}</p>`;
  $("promptOrchestratorLog").innerHTML = `<p class="analysis-placeholder">The backend preview log will appear here.</p>`;
}

function renderPromptOrchestratorPreview(report) {
  state.promptOrchestratorPreview = report;
  const analysis = report.analysis || {};
  const retrievedContext = Array.isArray(report.retrieved_context) ? report.retrieved_context : [];
  const recommendations = Array.isArray(report.recommendations) ? report.recommendations : [];

  $("promptOrchestratorPreview").innerHTML = `
    <div class="analysis-grid">
      <article class="analysis-card">
        <p class="analysis-label">Chain</p>
        <p class="analysis-value">${escapeHtml(report.chain_name || "")}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Version</p>
        <p class="analysis-value">v${Number(report.version_no || 0)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Tokens</p>
        <p class="analysis-value">${Number(analysis.tokens || 0)}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Reliability</p>
        <p class="analysis-value">${formatPercent(Number(analysis.reliability || 0))}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Cache hit</p>
        <p class="analysis-value">${formatPercent(Number(analysis.cache_hit_probability || 0))}</p>
      </article>
      <article class="analysis-card">
        <p class="analysis-label">Security</p>
        <p class="analysis-value">${renderRiskCell(Number(analysis.injection_risk || 0))} / ${renderRiskCell(Number(analysis.contradiction_risk || 0))} / ${renderRiskCell(Number(analysis.ambiguity_risk || 0))}</p>
      </article>
    </div>

    <div class="table-wrap">
      <table class="metrics-table">
        <thead>
          <tr>
            <th>Retrieved context</th>
          </tr>
        </thead>
        <tbody>
          ${retrievedContext.length ? retrievedContext.map((chunk) => `<tr><td>${escapeHtml(chunk)}</td></tr>`).join("") : `<tr><td class="muted">(none)</td></tr>`}
        </tbody>
      </table>
    </div>

    <div class="table-wrap">
      <table class="metrics-table">
        <thead>
          <tr><th>Recommendations</th></tr>
        </thead>
        <tbody>
          ${recommendations.length ? recommendations.map((item) => `<tr><td>${escapeHtml(item)}</td></tr>`).join("") : `<tr><td class="muted">(none)</td></tr>`}
        </tbody>
      </table>
    </div>

    <div class="table-wrap">
      <table class="metrics-table">
        <thead>
          <tr><th>Improved prompt</th></tr>
        </thead>
        <tbody><tr><td><pre class="log-output">${escapeHtml(String(report.improved_prompt || ""))}</pre></td></tr></tbody>
      </table>
    </div>
  `;

  $("promptOrchestratorLog").innerHTML = `
    <div class="analysis-card">
      <p class="analysis-label">Log path</p>
      <p class="analysis-value-small">${escapeHtml(report.log_path || "")}</p>
    </div>
    <div class="table-wrap">
      <pre class="log-output">${escapeHtml(String(report.log_text || ""))}</pre>
    </div>
  `;
}

async function previewPromptOrchestrator() {
  if (!state.selectedPromptChainId || !state.selectedPromptVersionNo) {
    return;
  }
  try {
    const report = await api(
      `/v1/prompt-versions/chains/${state.selectedPromptChainId}/versions/${state.selectedPromptVersionNo}/orchestrate`,
      { method: "POST" },
    );
    renderPromptOrchestratorPreview(report);
  } catch (error) {
    $("promptOrchestratorPreview").innerHTML = `<p class="analysis-placeholder">Orchestrator preview failed: ${escapeHtml(error.message)}</p>`;
    $("promptOrchestratorLog").innerHTML = `<p class="analysis-placeholder">The backend preview log could not be loaded.</p>`;
  }
}

function renderSettingsTable() {
  const tbody = $("settingsTable").querySelector("tbody");
  tbody.innerHTML = "";
  const runtimeCacheBackendOptions = ["memory", "redis", "garnet", "none"];

  const isBooleanLike = (raw) => {
    const normalized = String(raw ?? "").trim().toLowerCase();
    return normalized === "true" || normalized === "false";
  };

  const hiddenInRawTable = new Set([
    "OPTIMIZER_PROVIDER",
    "OPTIMIZER_MODEL",
    "OPTIMIZER_BASE_URL",
    "OPTIMIZER_BACKEND",
    "OPTIMIZER_API_TOKEN",
    "PROMPT_COMPRESSION_PROVIDER",
    "PROMPT_COMPRESSION_MODEL",
    "PROMPT_COMPRESSION_BASE_URL",
    "PROMPT_COMPRESSION_BACKEND",
    "PROMPT_COMPRESSION_API_TOKEN",
    "TEST_LLM_PROVIDER",
    "TEST_LLM_MODEL",
    "TEST_LLM_BASE_URL",
    "TEST_LLM_API_TOKEN",
    "TEST_LLM_TIMEOUT_SECONDS",
    "TEST_LLM_USE_OPTIMIZER_FALLBACK",
    "TEST_RAG_ENABLED",
    "TEST_RAG_SOURCE_PATH",
    "TEST_RAG_TOP_K",
  ]);

  const keys = Object.keys(state.settings)
    .filter((key) => !hiddenInRawTable.has(key))
    .sort((a, b) => a.localeCompare(b));
  for (const key of keys) {
    const value = state.settings[key] ?? "";
    const row = document.createElement("tr");
    const keyEscaped = escapeHtml(key);
    const valueEscaped = escapeHtml(value);

    if (key === "PROMPTMAN_RUNTIME_CACHE_BACKEND") {
      const optionsHtml = runtimeCacheBackendOptions
        .map((option) => `<option value="${option}" ${option === value ? "selected" : ""}>${option}</option>`)
        .join("");
      row.innerHTML = `
        <td>${keyEscaped}</td>
        <td>
          <select class="settings-row-input" data-key="${keyEscaped}" data-input-kind="select">
            ${optionsHtml}
          </select>
        </td>
        <td><button class="secondary" data-save-key="${keyEscaped}">Save</button></td>
      `;
    } else if (isBooleanLike(value)) {
      const checkedAttr = String(value).trim().toLowerCase() === "true" ? "checked" : "";
      row.innerHTML = `
        <td>${keyEscaped}</td>
        <td>
          <label class="switch" aria-label="${keyEscaped}">
            <input type="checkbox" data-key="${keyEscaped}" data-input-kind="boolean" ${checkedAttr} />
            <span class="slider"></span>
          </label>
        </td>
        <td><button class="secondary" data-save-key="${keyEscaped}">Save</button></td>
      `;
    } else {
      row.innerHTML = `
        <td>${keyEscaped}</td>
        <td><input class="settings-row-input" data-key="${keyEscaped}" data-input-kind="text" value="${valueEscaped}" /></td>
        <td><button class="secondary" data-save-key="${keyEscaped}">Save</button></td>
      `;
    }

    tbody.appendChild(row);
  }

  tbody.querySelectorAll("button[data-save-key]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.saveKey;
      const input = tbody.querySelector(`[data-key='${CSS.escape(key)}']`);
      if (!input) return;

      let value;
      const kind = input.dataset.inputKind;
      if (kind === "boolean") {
        value = input.checked ? "true" : "false";
      } else {
        value = input.value;
      }
      await saveSetting(key, value);
    });
  });
}

function getDefaultProviderBaseUrl(providerName) {
  const provider = state.providerMeta.providers.find((p) => p.name === providerName);
  return provider?.default_base_url || "";
}

function renderProviderSelectOptions(selectEl, selected) {
  selectEl.innerHTML = "";
  for (const provider of state.providerMeta.providers) {
    const option = document.createElement("option");
    option.value = provider.name;
    option.textContent = provider.name;
    option.selected = provider.name === selected;
    selectEl.appendChild(option);
  }
}

function renderBackendSelectOptions(selectEl, selected) {
  selectEl.innerHTML = "";
  for (const backendName of state.providerMeta.backends) {
    const option = document.createElement("option");
    option.value = backendName;
    option.textContent = backendName;
    option.selected = backendName === selected;
    selectEl.appendChild(option);
  }
}

function renderModelSelectOptions(selectEl, models) {
  selectEl.innerHTML = "";
  if (!models.length) {
    return;
  }

  for (const modelName of models) {
    const option = document.createElement("option");
    option.value = modelName;
    option.textContent = modelName;
    selectEl.appendChild(option);
  }
}

function updateLlmSaveButtonsState() {
  const pairs = [
    { modelId: "optimizerModel", buttonId: "saveOptimizerSettingsBtn", label: "optimizer" },
    { modelId: "compressionModel", buttonId: "saveCompressionSettingsBtn", label: "compression" },
    { modelId: "testLlmModel", buttonId: "saveTestLlmSettingsBtn", label: "test" },
  ];

  for (const pair of pairs) {
    const modelSelect = $(pair.modelId);
    const saveButton = $(pair.buttonId);
    if (!modelSelect || !saveButton) continue;
    const hasModel = Boolean(String(modelSelect.value || "").trim());
    saveButton.disabled = !hasModel;
    saveButton.title = hasModel ? "" : `Reload ${pair.label} models and select one before saving`;
  }
}

async function loadProviderMeta() {
  const payload = await api("/v1/admin/config/meta/providers");
  state.providerMeta = {
    providers: Array.isArray(payload.providers) ? payload.providers : [],
    backends: Array.isArray(payload.backends) ? payload.backends : [],
  };
}

function roleLabel(roleName) {
  if (roleName === "admin") return "administrator";
  return roleName;
}

function roleValueFromLabel(labelOrValue) {
  if (labelOrValue === "administrator") return "admin";
  return labelOrValue;
}

async function loadRoles() {
  const rows = await api("/v1/roles");
  state.roleOptions = Array.isArray(rows) ? rows.map((r) => r.name) : [];
}

function renderUserRoleOptions() {
  const selectEl = $("newUserRole");
  selectEl.innerHTML = "";
  const allowedOrder = ["admin", "developer", "viewer"];
  const available = allowedOrder.filter((role) => state.roleOptions.includes(role));

  for (const roleName of available) {
    const option = document.createElement("option");
    option.value = roleName;
    option.textContent = roleLabel(roleName);
    selectEl.appendChild(option);
  }

  if (!available.length) {
    const fallback = document.createElement("option");
    fallback.value = "developer";
    fallback.textContent = "developer";
    selectEl.appendChild(fallback);
  }
}

function renderUsersTable(items) {
  const tbody = $("usersTable").querySelector("tbody");
  tbody.innerHTML = "";

  const availableRoles = ["admin", "developer", "viewer"].filter((roleName) => state.roleOptions.includes(roleName));

  for (const user of items) {
    const userRole = user.role || "developer";
    const roleChoices = availableRoles.includes(userRole) ? availableRoles : [userRole, ...availableRoles];
    const roleOptionsHtml = roleChoices
      .map(
        (roleName) =>
          `<option value="${escapeHtml(roleName)}" ${roleName === userRole ? "selected" : ""}>${escapeHtml(roleLabel(roleName))}</option>`,
      )
      .join("");
    const activeChecked = user.is_active ? "checked" : "";

    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(user.username)}</td>
      <td>
        <select class="settings-row-input" data-user-id="${user.id}" data-user-field="role">
          ${roleOptionsHtml}
        </select>
      </td>
      <td>
        <label class="switch switch-sm" aria-label="${escapeHtml(user.username)} active">
          <input type="checkbox" data-user-id="${user.id}" data-user-field="is_active" ${activeChecked} />
          <span class="slider"></span>
        </label>
      </td>
      <td><button class="secondary" data-save-user-id="${user.id}">Save</button></td>
    `;
    tbody.appendChild(row);
  }

  tbody.querySelectorAll("button[data-save-user-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const userId = Number(btn.dataset.saveUserId);
      if (!Number.isFinite(userId)) return;

      const roleInput = tbody.querySelector(`select[data-user-id='${userId}'][data-user-field='role']`);
      const activeInput = tbody.querySelector(`input[data-user-id='${userId}'][data-user-field='is_active']`);
      if (!roleInput || !activeInput) return;

      btn.disabled = true;
      try {
        await api(`/v1/users/${userId}`, {
          method: "PUT",
          body: JSON.stringify({
            role: roleValueFromLabel(roleInput.value),
            is_active: activeInput.checked,
          }),
        });
        $("settingsStatus").textContent = "User updated";
        await refreshUsers();
      } catch (error) {
        $("settingsStatus").textContent = `User update failed: ${error.message}`;
      } finally {
        btn.disabled = false;
      }
    });
  });
}

async function refreshUsers() {
  try {
    const users = await api("/v1/users");
    renderUsersTable(Array.isArray(users) ? users : []);
  } catch (error) {
    $("settingsStatus").textContent = `Users load failed: ${error.message}`;
  }
}

async function createUserFromSettings() {
  const username = $("newUserUsername").value.trim();
  const password = $("newUserPassword").value;
  const role = roleValueFromLabel($("newUserRole").value);

  if (!username || !password) {
    $("settingsStatus").textContent = "Username and password are required";
    return;
  }

  try {
    await api("/v1/users", {
      method: "POST",
      body: JSON.stringify({
        username,
        password,
        role,
        is_active: true,
        projects: [],
      }),
    });
    $("newUserPassword").value = "";
    $("settingsStatus").textContent = `User '${username}' created`;
    await refreshUsers();
  } catch (error) {
    $("settingsStatus").textContent = `User create failed: ${error.message}`;
  }
}

async function fetchProviderModels(provider, baseUrl, apiToken = "") {
  const query = new URLSearchParams();
  if (baseUrl) query.set("base_url", baseUrl);
  if (apiToken) query.set("api_token", apiToken);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const payload = await api(`/v1/admin/config/meta/providers/${encodeURIComponent(provider)}/models${suffix}`);
  return Array.isArray(payload.models) ? payload.models : [];
}

async function syncProviderModels(
  providerSelectId,
  baseUrlInputId,
  tokenInputId,
  modelSelectId,
  modelSettingKey,
  statusPrefix,
) {
  const provider = $(providerSelectId).value;
  const baseUrl = $(baseUrlInputId).value.trim();
  const tokenDraft = $(tokenInputId).value.trim();
  const modelSelect = $(modelSelectId);
  const preferred = modelSelect.value || state.settings[modelSettingKey] || "";

  try {
    const models = await fetchProviderModels(provider, baseUrl, tokenDraft);
    renderModelSelectOptions(modelSelect, models);

    if (!models.length) {
      state.settings[modelSettingKey] = "";
      $("settingsStatus").textContent = `${statusPrefix}: provider returned no models`;
      updateLlmSaveButtonsState();
      return;
    }

    if (preferred && models.includes(preferred)) {
      modelSelect.value = preferred;
      state.settings[modelSettingKey] = preferred;
      $("settingsStatus").textContent = `${statusPrefix}: ${models.length} model(s) loaded`;
      updateLlmSaveButtonsState();
      return;
    }

    const firstModel = models[0];
    modelSelect.value = firstModel;
    state.settings[modelSettingKey] = firstModel;

    if (preferred) {
      $("settingsStatus").textContent = `${statusPrefix}: saved model '${preferred}' is unavailable, switched to '${firstModel}'`;
    } else {
      $("settingsStatus").textContent = `${statusPrefix}: ${models.length} model(s) loaded, selected '${firstModel}'`;
    }
    updateLlmSaveButtonsState();
  } catch (error) {
    state.settings[modelSettingKey] = "";
    renderModelSelectOptions(modelSelect, []);
    $("settingsStatus").textContent = `${statusPrefix} load failed: ${error.message}`;
    updateLlmSaveButtonsState();
  }
}

async function syncOptimizerModels() {
  await syncProviderModels(
    "optimizerProvider",
    "optimizerBaseUrl",
    "optimizerApiToken",
    "optimizerModel",
    "OPTIMIZER_MODEL",
    "Optimizer models",
  );
}

async function syncCompressionModels() {
  await syncProviderModels(
    "compressionProvider",
    "compressionBaseUrl",
    "compressionApiToken",
    "compressionModel",
    "PROMPT_COMPRESSION_MODEL",
    "Compression models",
  );
}

async function syncTestLlmModels() {
  await syncProviderModels(
    "testLlmProvider",
    "testLlmBaseUrl",
    "testLlmApiToken",
    "testLlmModel",
    "TEST_LLM_MODEL",
    "Test LLM models",
  );
}

function renderOptimizerSettings() {
  const optimizerProvider = state.settings.OPTIMIZER_PROVIDER || "openai";
  const optimizerBaseUrl = state.settings.OPTIMIZER_BASE_URL || getDefaultProviderBaseUrl(optimizerProvider);
  const optimizerBackend = state.settings.OPTIMIZER_BACKEND || "leo";

  const compressionProvider = state.settings.PROMPT_COMPRESSION_PROVIDER || optimizerProvider;
  const compressionBaseUrl = state.settings.PROMPT_COMPRESSION_BASE_URL || getDefaultProviderBaseUrl(compressionProvider);
  const compressionBackend = state.settings.PROMPT_COMPRESSION_BACKEND || optimizerBackend;

  const testProvider = state.settings.TEST_LLM_PROVIDER || "ollama";
  const testBaseUrl = state.settings.TEST_LLM_BASE_URL || getDefaultProviderBaseUrl(testProvider) || "http://127.0.0.1:11434";
  const testTimeout = Number(state.settings.TEST_LLM_TIMEOUT_SECONDS || 45);
  const testFallback = String(state.settings.TEST_LLM_USE_OPTIMIZER_FALLBACK || "false").toLowerCase() === "true";
  const testRagEnabled = String(state.settings.TEST_RAG_ENABLED || "false").toLowerCase() === "true";
  const testRagTopK = Number(state.settings.TEST_RAG_TOP_K || 3);
  const testRagSourcePath = state.settings.TEST_RAG_SOURCE_PATH || "simulations/rag_knowledge.md";

  renderProviderSelectOptions($("optimizerProvider"), optimizerProvider);
  renderBackendSelectOptions($("optimizerBackend"), optimizerBackend);
  $("optimizerBaseUrl").value = optimizerBaseUrl;
  $("optimizerApiToken").value = "";
  $("optimizerApiToken").placeholder = TOKEN_PLACEHOLDER;

  renderProviderSelectOptions($("compressionProvider"), compressionProvider);
  renderBackendSelectOptions($("compressionBackend"), compressionBackend);
  $("compressionBaseUrl").value = compressionBaseUrl;
  $("compressionApiToken").value = "";
  $("compressionApiToken").placeholder = TOKEN_PLACEHOLDER;

  renderProviderSelectOptions($("testLlmProvider"), testProvider);
  $("testLlmBaseUrl").value = testBaseUrl;
  $("testLlmTimeoutSeconds").value = Number.isFinite(testTimeout) ? String(Math.max(3, testTimeout)) : "45";
  $("testLlmUseOptimizerFallback").value = testFallback ? "true" : "false";
  $("testLlmApiToken").value = "";
  $("testLlmApiToken").placeholder = TOKEN_PLACEHOLDER;
  $("testRagEnabled").value = testRagEnabled ? "true" : "false";
  $("testRagTopK").value = Number.isFinite(testRagTopK) ? String(Math.max(1, testRagTopK)) : "3";
  $("testRagSourcePath").value = testRagSourcePath;

  const autoProvider = state.settings.TEST_LLM_PROVIDER || state.settings.OPTIMIZER_PROVIDER || "ollama";
  renderProviderSelectOptions($("llmAutoProvider"), autoProvider);
  $("llmAutoBaseUrl").value = state.settings.TEST_LLM_BASE_URL || getDefaultProviderBaseUrl(autoProvider) || "";
  if (!$("llmAutoMode").value) {
    $("llmAutoMode").value = "intelligent";
  }
}

async function saveOptimizerSettings() {
  const provider = $("optimizerProvider").value;
  const model = $("optimizerModel").value;
  const baseUrl = $("optimizerBaseUrl").value.trim();
  const backend = $("optimizerBackend").value;
  const apiToken = $("optimizerApiToken").value.trim();

  if (!model) {
    $("settingsStatus").textContent = "Optimizer model is not selected. Reload models first.";
    return;
  }

  await saveSetting("OPTIMIZER_PROVIDER", provider);
  await saveSetting("OPTIMIZER_MODEL", model);
  await saveSetting("OPTIMIZER_BASE_URL", baseUrl);
  await saveSetting("OPTIMIZER_BACKEND", backend);
  if (apiToken) {
    await saveSetting("OPTIMIZER_API_TOKEN", apiToken);
    $("optimizerApiToken").value = "";
  }

  await loadSettings();
}

async function saveCompressionSettings() {
  const provider = $("compressionProvider").value;
  const model = $("compressionModel").value;
  const baseUrl = $("compressionBaseUrl").value.trim();
  const backend = $("compressionBackend").value;
  const apiToken = $("compressionApiToken").value.trim();

  if (!model) {
    $("settingsStatus").textContent = "Compression model is not selected. Reload models first.";
    return;
  }

  await saveSetting("PROMPT_COMPRESSION_PROVIDER", provider);
  await saveSetting("PROMPT_COMPRESSION_MODEL", model);
  await saveSetting("PROMPT_COMPRESSION_BASE_URL", baseUrl);
  await saveSetting("PROMPT_COMPRESSION_BACKEND", backend);
  if (apiToken) {
    await saveSetting("PROMPT_COMPRESSION_API_TOKEN", apiToken);
    $("compressionApiToken").value = "";
  }

  await loadSettings();
}

async function saveTestLlmSettings() {
  const provider = $("testLlmProvider").value;
  const model = $("testLlmModel").value;
  const baseUrl = $("testLlmBaseUrl").value.trim();
  const timeoutSeconds = String(Math.max(3, Number($("testLlmTimeoutSeconds").value || 45)));
  const useFallback = $("testLlmUseOptimizerFallback").value;
  const apiToken = $("testLlmApiToken").value.trim();
  const ragEnabled = $("testRagEnabled").value;
  const ragTopK = String(Math.max(1, Number($("testRagTopK").value || 3)));
  const ragSourcePath = $("testRagSourcePath").value.trim() || "simulations/rag_knowledge.md";

  if (!model) {
    $("settingsStatus").textContent = "Test LLM model is not selected. Reload test models first.";
    return;
  }

  await saveSetting("TEST_LLM_PROVIDER", provider);
  await saveSetting("TEST_LLM_MODEL", model);
  await saveSetting("TEST_LLM_BASE_URL", baseUrl);
  await saveSetting("TEST_LLM_TIMEOUT_SECONDS", timeoutSeconds);
  await saveSetting("TEST_LLM_USE_OPTIMIZER_FALLBACK", useFallback);
  if (apiToken) {
    await saveSetting("TEST_LLM_API_TOKEN", apiToken);
    $("testLlmApiToken").value = "";
  }
  await saveSetting("TEST_RAG_ENABLED", ragEnabled);
  await saveSetting("TEST_RAG_TOP_K", ragTopK);
  await saveSetting("TEST_RAG_SOURCE_PATH", ragSourcePath);

  await loadSettings();
}

function buildLlmAutoPayload() {
  return {
    provider: $("llmAutoProvider").value,
    strategy: $("llmAutoMode").value,
    base_url: $("llmAutoBaseUrl").value.trim() || null,
    api_token: $("llmAutoApiToken").value.trim() || null,
    preferred_model: $("llmAutoPreferredModel").value.trim() || null,
  };
}

async function previewLlmAutoSetup() {
  try {
    const result = await api("/v1/admin/config/llm/autoconfigure/preview", {
      method: "POST",
      body: JSON.stringify(buildLlmAutoPayload()),
    });
    $("llmAutoResult").textContent = JSON.stringify(result, null, 2);
    $("settingsStatus").textContent = "LLM auto setup preview ready";
  } catch (error) {
    $("llmAutoResult").textContent = String(error.message || error);
    $("settingsStatus").textContent = `LLM auto setup preview failed: ${error.message}`;
  }
}

async function applyLlmAutoSetup() {
  try {
    const result = await api("/v1/admin/config/llm/autoconfigure/apply", {
      method: "POST",
      body: JSON.stringify(buildLlmAutoPayload()),
    });
    $("llmAutoResult").textContent = JSON.stringify(result, null, 2);
    $("settingsStatus").textContent = "LLM auto setup applied";
    $("llmAutoApiToken").value = "";
    await loadSettings();
  } catch (error) {
    $("llmAutoResult").textContent = String(error.message || error);
    $("settingsStatus").textContent = `LLM auto setup apply failed: ${error.message}`;
  }
}

async function login(endpoint) {
  const username = $("menuUsername").value.trim();
  const password = $("menuPassword").value;
  if (!username || !password) {
    $("authMenuStatus").textContent = "Username and password are required";
    return;
  }

  try {
    const payload = await api(endpoint, {
      method: "POST",
      body: JSON.stringify({ username, password }),
      headers: {},
    });
    state.accessToken = payload.access_token;
    state.refreshToken = payload.refresh_token;
    state.currentUser = payload.user;
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, state.accessToken);
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, state.refreshToken);
    $("authMenuStatus").textContent = "Authenticated";
    renderAuth();
    toggleStatusMenu(false);
    await refreshThreads();
    await refreshPromptChains();
    if (state.currentUser?.role === "admin") {
      await loadSettings();
    }
  } catch (error) {
    $("authMenuStatus").textContent = `Auth failed: ${error.message}`;
  }
}

async function changePassword() {
  const currentPassword = $("pwdCurrent").value;
  const newPassword = $("pwdNew").value;
  if (!currentPassword || !newPassword) {
    $("changePasswordStatus").textContent = "Current and new passwords are required";
    return;
  }

  try {
    await api("/v1/auth/me/password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    $("changePasswordStatus").textContent = "Password changed successfully";
    $("pwdCurrent").value = "";
    $("pwdNew").value = "";
  } catch (error) {
    $("changePasswordStatus").textContent = `Password change failed: ${error.message}`;
  }
}

async function refreshThreads() {
  if (!state.accessToken) return;
  const project = $("threadFilterProject").value.trim();
  const query = project ? `?project=${encodeURIComponent(project)}` : "";
  try {
    const items = await api(`/v1/conversations/threads${query}`);
    renderThreads(items);
  } catch (error) {
    $("threadCreateStatus").textContent = `Thread load failed: ${error.message}`;
  }
}

async function loadThreadDetails() {
  if (!state.selectedThreadId) return;
  const thread = await api(`/v1/conversations/threads/${state.selectedThreadId}`);
  $("threadDetailsTitle").textContent = `Thread #${thread.id}: ${thread.title}`;
  $("threadDetailsHint").textContent = `${thread.project} · ${thread.source}`;
  renderThreadAnalysisPlaceholder();
  renderThreadAnalysisLogPlaceholder();
  const messages = await api(`/v1/conversations/threads/${state.selectedThreadId}/messages`);
  state.threadMessages = messages;
  state.threadAnalysisMessages = messages;
  renderMessages(messages);
  await refreshThreads();
}

async function createThread() {
  try {
    const payload = await api("/v1/conversations/threads", {
      method: "POST",
      body: JSON.stringify({
        project: $("threadProject").value.trim(),
        title: $("threadTitle").value.trim(),
        source: $("threadSource").value.trim() || "manual",
      }),
    });
    $("threadCreateStatus").textContent = `Created thread #${payload.id}`;
    state.selectedThreadId = payload.id;
    await refreshThreads();
    await loadThreadDetails();
    setActiveTab("panelThreads");
  } catch (error) {
    $("threadCreateStatus").textContent = `Create failed: ${error.message}`;
  }
}

async function appendMessage() {
  if (!state.selectedThreadId) {
    $("threadCreateStatus").textContent = "Select a thread first";
    return;
  }
  const role = $("newMessageRole").value;
  const content = $("newMessageContent").value.trim();
  if (!content) return;

  try {
    await api(`/v1/conversations/threads/${state.selectedThreadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ messages: [{ role, content }] }),
    });
    $("newMessageContent").value = "";
    await loadThreadDetails();
  } catch (error) {
    $("threadCreateStatus").textContent = `Append failed: ${error.message}`;
  }
}

async function importJson() {
  try {
    const raw = $("jsonPayload").value.trim();
    const payload = JSON.parse(raw);
    const result = await api("/v1/conversations/import/json", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("importStatus").textContent = `JSON import status: ${result.status}, thread #${result.thread_id}`;
    await refreshThreads();
  } catch (error) {
    $("importStatus").textContent = `JSON import failed: ${error.message}`;
  }
}

async function importText() {
  try {
    const payload = {
      project: $("textProject").value.trim(),
      title: $("textTitle").value.trim(),
      delimiter: $("textDelimiter").value,
      text: $("textPayload").value,
    };
    const result = await api("/v1/conversations/import/text", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("importStatus").textContent = `Text import status: ${result.status}, thread #${result.thread_id}`;
    await refreshThreads();
  } catch (error) {
    $("importStatus").textContent = `Text import failed: ${error.message}`;
  }
}

async function analyzeThread() {
  if (!state.selectedThreadId) return;
  try {
    const result = await api(`/v1/conversations/analyze/${state.selectedThreadId}`, { method: "POST" });
    if (!state.threadMessages.length) {
      state.threadMessages = await api(`/v1/conversations/threads/${state.selectedThreadId}/messages`);
      renderMessages(state.threadMessages);
    }
    state.threadAnalysisMessages = state.threadMessages;
    state.threadAnalysisReport = result;
    renderThreadAnalysis(result, state.threadAnalysisMessages);
    await loadThreadAnalysisLog();
  } catch (error) {
    $("analyzeOutput").innerHTML = `<p class="analysis-placeholder">Analyze failed: ${escapeHtml(error.message)}</p>`;
  }
}

function buildThreadReportFromMessages(threadId, messages) {
  const counters = { user: 0, assistant: 0, system: 0, tool: 0 };
  let totalChars = 0;
  let startedAt = null;
  let endedAt = null;

  for (const msg of messages) {
    const role = String(msg.role || "").trim().toLowerCase();
    if (Object.prototype.hasOwnProperty.call(counters, role)) {
      counters[role] += 1;
    }
    const content = String(msg.content || "");
    totalChars += content.length;

    const dt = msg.timestamp ? new Date(msg.timestamp) : null;
    if (dt && Number.isFinite(dt.getTime())) {
      if (!startedAt || dt < startedAt) startedAt = dt;
      if (!endedAt || dt > endedAt) endedAt = dt;
    }
  }

  return {
    thread_id: Number(threadId || 0),
    turns: messages.length,
    user_turns: counters.user,
    assistant_turns: counters.assistant,
    system_turns: counters.system,
    tool_turns: counters.tool,
    total_chars: totalChars,
    started_at: startedAt ? startedAt.toISOString() : null,
    ended_at: endedAt ? endedAt.toISOString() : null,
  };
}

function buildPromptOrchestratorRecommendations(content) {
  const metrics = computeSecurityMetrics(content);
  const recommendations = [];
  if (Number(metrics.injection_risk || 0) >= 20) {
    recommendations.push("Harden instruction hierarchy and remove conflicting directives.");
  }
  if (Number(metrics.contradiction_risk || 0) >= 10) {
    recommendations.push("Resolve contradictory constraints and make precedence explicit.");
  }
  if (Number(metrics.ambiguity_risk || 0) >= 10) {
    recommendations.push("Replace vague phrasing with concrete thresholds and expected outputs.");
  }
  if (!recommendations.length) {
    recommendations.push("Prompt is stable; preserve structure and trim redundant text.");
  }
  return { metrics, recommendations };
}

function orchestratePromptText(content) {
  const source = String(content || "").trim();
  const { recommendations } = buildPromptOrchestratorRecommendations(source);
  const improved = [
    "You are a prompt orchestration assistant.",
    "Keep instruction hierarchy explicit: system > task > constraints > examples > context.",
    "Return concise, structured output and avoid unsupported claims.",
    "",
    "Source prompt:",
    source,
    "",
    "Suggested improvements:",
    ...recommendations.map((item) => `- ${item}`),
  ].join("\n");
  return { improved_prompt: improved, recommendations };
}

async function orchestrateAndAnalyzeThreadChain() {
  if (!state.selectedThreadId) {
    $("analyzeOutput").innerHTML = '<p class="analysis-placeholder">Select a thread first.</p>';
    return;
  }

  try {
    if (!state.threadMessages.length) {
      state.threadMessages = await api(`/v1/conversations/threads/${state.selectedThreadId}/messages`);
      renderMessages(state.threadMessages);
    }

    const improvedMessages = state.threadMessages.map((msg, index) => {
      const sourceContent = String(msg.content || "");
      const orchestrated = orchestratePromptText(sourceContent);
      return {
        ...msg,
        seq_no: Number(msg.seq_no || index + 1),
        content: orchestrated.improved_prompt,
        _orchestrator_recommendations: orchestrated.recommendations,
        _original_content: sourceContent,
      };
    });

    state.threadAnalysisMessages = improvedMessages;
    const syntheticReport = buildThreadReportFromMessages(state.selectedThreadId, improvedMessages);
    state.threadAnalysisReport = syntheticReport;
    renderThreadAnalysis(syntheticReport, improvedMessages);

    const logRows = improvedMessages
      .map((msg) => {
        const seqNo = Number(msg.seq_no || 0);
        const rec = Array.isArray(msg._orchestrator_recommendations) ? msg._orchestrator_recommendations : [];
        const original = String(msg._original_content || "");
        const improved = String(msg.content || "");
        return [
          `[${seqNo}] role=${msg.role}`,
          "Original:",
          original,
          "",
          "Recommendations:",
          ...(rec.length ? rec.map((item) => `- ${item}`) : ["- (none)"]),
          "",
          "Improved:",
          improved,
          "",
        ].join("\n");
      })
      .join("\n------------------------------\n\n");

    $("threadAnalysisLog").innerHTML = `
      <div class="analysis-card">
        <p class="analysis-label">Prompt Orchestrator pass</p>
        <p class="analysis-value-small">Improved messages: ${improvedMessages.length}</p>
      </div>
      <div class="table-wrap">
        <pre class="log-output">${escapeHtml(logRows)}</pre>
      </div>
    `;
  } catch (error) {
    $("analyzeOutput").innerHTML = `<p class="analysis-placeholder">Orchestrate + analyze failed: ${escapeHtml(error.message)}</p>`;
  }
}

async function loadThreadAnalysisLog() {
  if (!state.selectedThreadId) return;
  try {
    const result = await api(`/v1/conversations/threads/${state.selectedThreadId}/analysis-log`);
    renderThreadAnalysisLog(result);
  } catch (error) {
    $("threadAnalysisLog").innerHTML = `<p class="analysis-placeholder">Full log failed: ${escapeHtml(error.message)}</p>`;
  }
}

async function exportElementToPdf(element, fileName, titleText) {
  const html2canvasLib = window.html2canvas;
  const jsPdfCtor = window.jspdf?.jsPDF;

  if (!html2canvasLib || !jsPdfCtor) {
    const exportWindow = window.open("", "_blank", "noopener,noreferrer,width=1200,height=900");
    if (!exportWindow) {
      throw new Error("Popup blocked: allow popups to export PDF");
    }
    exportWindow.document.write(`
      <html>
        <head><title>${escapeHtml(titleText)}</title><style>body{font-family:Arial,sans-serif;padding:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d1d5db;padding:6px;text-align:left}.trend-chart,.analysis-report,.table-wrap{overflow:visible !important}</style></head>
        <body>
          <h1>${escapeHtml(titleText)}</h1>
          ${element.outerHTML}
        </body>
      </html>
    `);
    exportWindow.document.close();
    exportWindow.focus();
    exportWindow.print();
    return;
  }

  const canvas = await html2canvasLib(element, {
    scale: 2,
    backgroundColor: "#ffffff",
    useCORS: true,
    logging: false,
  });

  const imageData = canvas.toDataURL("image/png");
  const pdf = new jsPdfCtor("p", "pt", "a4");
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = 24;
  const contentWidth = pageWidth - margin * 2;
  const contentHeight = (canvas.height * contentWidth) / canvas.width;
  let yOffset = margin;

  pdf.setFontSize(14);
  pdf.text(titleText, margin, 16);
  pdf.addImage(imageData, "PNG", margin, yOffset, contentWidth, contentHeight);

  let remaining = contentHeight - (pageHeight - margin * 2);
  let sourceYOffset = pageHeight - margin * 2;

  while (remaining > 0) {
    pdf.addPage();
    pdf.addImage(imageData, "PNG", margin, margin - sourceYOffset, contentWidth, contentHeight);
    remaining -= pageHeight - margin * 2;
    sourceYOffset += pageHeight - margin * 2;
  }

  pdf.save(fileName);
}

function buildPromptAnalysisExportNode() {
  const wrapper = document.createElement("section");
  wrapper.style.background = "#ffffff";
  wrapper.style.padding = "14px";
  wrapper.style.fontFamily = '"Space Grotesk", Arial, sans-serif';
  wrapper.style.width = "1020px";

  const title = document.createElement("h2");
  title.textContent = $("promptChainDetailsTitle").textContent || "Prompt chain analysis";
  wrapper.appendChild(title);

  const hint = document.createElement("p");
  hint.textContent = $("promptChainDetailsHint").textContent || "";
  hint.style.color = "#64748b";
  wrapper.appendChild(hint);

  const appendBlock = (headingText, node) => {
    const heading = document.createElement("h3");
    heading.textContent = headingText;
    wrapper.appendChild(heading);
    wrapper.appendChild(node.cloneNode(true));
  };

  appendBlock("Summary", $("promptChainAnalysisSummary"));
  appendBlock("Trend chart", $("promptChainTrendChart"));
  appendBlock("Metrics table", $("promptChainMetricsTable"));
  appendBlock("Selected version analysis", $("promptVersionAnalysis"));

  return wrapper;
}

async function exportThreadAnalysisPdf() {
  if (!state.selectedThreadId) {
    $("threadCreateStatus").textContent = "Select a thread first";
    return;
  }
  const section = document.createElement("section");
  section.style.background = "#ffffff";
  section.style.padding = "14px";
  section.style.fontFamily = '"Space Grotesk", Arial, sans-serif';
  section.style.width = "1020px";

  const title = document.createElement("h2");
  title.textContent = $("threadDetailsTitle").textContent || `Thread #${state.selectedThreadId} analysis`;
  section.appendChild(title);
  section.appendChild($("analyzeOutput").cloneNode(true));
  if (state.threadAnalysisLog) {
    const logTitle = document.createElement("h3");
    logTitle.textContent = "Full log";
    section.appendChild(logTitle);
    section.appendChild($("threadAnalysisLog").cloneNode(true));
  }

  document.body.appendChild(section);
  try {
    await exportElementToPdf(section, `thread-analysis-${state.selectedThreadId}.pdf`, title.textContent);
  } catch (error) {
    $("threadCreateStatus").textContent = `Export failed: ${error.message}`;
  } finally {
    section.remove();
  }
}

async function exportPromptAnalysisPdf() {
  if (!state.selectedPromptChainId) {
    $("promptChainCreateStatus").textContent = "Select a prompt chain first";
    return;
  }
  const section = buildPromptAnalysisExportNode();
  document.body.appendChild(section);
  try {
    await exportElementToPdf(
      section,
      `prompt-chain-analysis-${state.selectedPromptChainId}.pdf`,
      `Prompt chain #${state.selectedPromptChainId} analysis`,
    );
  } catch (error) {
    $("promptChainCreateStatus").textContent = `Export failed: ${error.message}`;
  } finally {
    section.remove();
  }
}

async function refreshPromptChains() {
  if (!state.accessToken) return;
  const project = $("promptChainProjectFilter").value.trim();
  const query = project ? `?project=${encodeURIComponent(project)}` : "";
  try {
    const rows = await api(`/v1/prompt-versions/chains${query}`);
    renderPromptChains(rows);
  } catch (error) {
    $("promptChainCreateStatus").textContent = `Chain load failed: ${error.message}`;
  }
}

async function loadPromptChainDetails() {
  if (!state.selectedPromptChainId) return;
  try {
    const chain = await api(`/v1/prompt-versions/chains/${state.selectedPromptChainId}`);
    $("promptChainDetailsTitle").textContent = `Prompt chain #${chain.id}: ${chain.name}`;
    $("promptChainDetailsHint").textContent = `${chain.project} · updated ${chain.updated_at}`;

    const versions = await api(`/v1/prompt-versions/chains/${state.selectedPromptChainId}/versions`);
    renderPromptVersions(versions);

    if (versions.length && !state.selectedPromptVersionNo) {
      state.selectedPromptVersionNo = versions[versions.length - 1].version_no;
      await analyzePromptVersion();
      await loadPromptVersionDetails();
      renderPromptVersions(versions);
    }

    if (state.selectedPromptVersionNo) {
      await loadPromptVersionDetails();
      await refreshPromptTests();
      renderPromptOrchestratorPreviewPlaceholder("Choose Analyze -> Prompt Orchestrator preview to inspect improved prompt output.");
    }

    await analyzePromptChain();
    await refreshPromptChains();
  } catch (error) {
    $("promptChainCreateStatus").textContent = `Load failed: ${error.message}`;
  }
}

async function createPromptChain() {
  try {
    const payload = {
      project: $("promptChainProject").value.trim(),
      name: $("promptChainName").value.trim(),
      description: $("promptChainDescription").value.trim() || null,
      content: $("promptChainInitialContent").value.trim(),
      notes: $("promptChainInitialNotes").value.trim() || null,
    };
    const created = await api("/v1/prompt-versions/chains", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("promptChainCreateStatus").textContent = `Created prompt chain #${created.id}`;
    state.selectedPromptChainId = created.id;
    state.selectedPromptVersionNo = 1;
    await refreshPromptChains();
    await loadPromptChainDetails();
    setActiveTab("panelPromptVersions");
  } catch (error) {
    $("promptChainCreateStatus").textContent = `Create failed: ${error.message}`;
  }
}

async function createPromptVersion() {
  if (!state.selectedPromptChainId) {
    $("promptVersionCreateStatus").textContent = "Select a prompt chain first";
    return;
  }

  const content = $("promptVersionContent").value.trim();
  if (!content) {
    $("promptVersionCreateStatus").textContent = "Content is required";
    return;
  }

  try {
    const payload = {
      content,
      notes: $("promptVersionNotes").value.trim() || null,
    };
    const created = await api(`/v1/prompt-versions/chains/${state.selectedPromptChainId}/versions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("promptVersionCreateStatus").textContent = `Created v${created.version_no}`;
    $("promptVersionContent").value = "";
    $("promptVersionNotes").value = "";
    state.selectedPromptVersionNo = created.version_no;
    await loadPromptChainDetails();
  } catch (error) {
    $("promptVersionCreateStatus").textContent = `Create version failed: ${error.message}`;
  }
}

async function analyzePromptChain() {
  if (!state.selectedPromptChainId) {
    $("promptChainAnalysisSummary").textContent = "Select a prompt chain first.";
    return;
  }
  try {
    const report = await api(`/v1/prompt-versions/chains/${state.selectedPromptChainId}/analyze`, { method: "POST" });
    state.promptChainAnalysisPoints = report.points || [];
    $("promptChainAnalysisSummary").textContent = JSON.stringify(report.summary, null, 2);
    renderPromptAnalysisTable(state.promptChainAnalysisPoints);
    renderPromptTrendChart(state.promptChainAnalysisPoints);
  } catch (error) {
    state.promptChainAnalysisPoints = [];
    $("promptChainAnalysisSummary").textContent = `Analyze chain failed: ${error.message}`;
  }
}

function closeDetailsMenu(menuId) {
  const menu = $(menuId);
  if (menu) {
    menu.open = false;
  }
}

async function handlePromptChainAnalyzeChoice(choice, menuId = "promptChainAnalyzeMenu") {
  closeDetailsMenu(menuId);
  if (choice === "chain") {
    await analyzePromptChain();
    return;
  }
  if (choice === "orchestrator") {
    if (!state.selectedPromptChainId || !state.selectedPromptVersionNo) {
      $("promptOrchestratorPreview").innerHTML = '<p class="analysis-placeholder">Select a chain and version first.</p>';
      return;
    }
    await previewPromptOrchestrator();
  }
}

async function analyzePromptVersion() {
  if (!state.selectedPromptChainId || !state.selectedPromptVersionNo) return;
  try {
    const report = await api(
      `/v1/prompt-versions/chains/${state.selectedPromptChainId}/versions/${state.selectedPromptVersionNo}/analyze`,
      { method: "POST" },
    );

    let point = state.promptChainAnalysisPoints.find((item) => item.version_no === state.selectedPromptVersionNo);
    if (!point) {
      const chainReport = await api(`/v1/prompt-versions/chains/${state.selectedPromptChainId}/analyze`, { method: "POST" });
      state.promptChainAnalysisPoints = chainReport.points || [];
      point = state.promptChainAnalysisPoints.find((item) => item.version_no === state.selectedPromptVersionNo);
    }

    renderPromptVersionAnalysis(report, point || null);
  } catch (error) {
    $("promptVersionAnalysis").innerHTML = `<p class="analysis-placeholder">Analyze version failed: ${escapeHtml(error.message)}</p>`;
  }
}

async function runPromptTest() {
  if (!state.selectedPromptChainId || !state.selectedPromptVersionNo) {
    $("promptTestRunStatus").textContent = "Select a chain and version first";
    return;
  }
  try {
    const run = await api(
      `/v1/prompt-versions/chains/${state.selectedPromptChainId}/versions/${state.selectedPromptVersionNo}/test-runs`,
      { method: "POST" },
    );
    $("promptTestRunStatus").textContent = `Test run created: ${run.id}`;
    await refreshPromptTests(run.id);
  } catch (error) {
    $("promptTestRunStatus").textContent = `Run test failed: ${error.message}`;
  }
}

async function refreshPromptTests(preferredRunId = null) {
  if (!state.selectedPromptChainId || !state.selectedPromptVersionNo) {
    state.promptTestRuns = [];
    state.selectedPromptTestRunId = null;
    renderPromptTestRuns([]);
    renderPromptTestRunPlaceholder("Select a prompt version to view test runs.");
    return;
  }
  try {
    const rows = await api(
      `/v1/prompt-versions/chains/${state.selectedPromptChainId}/versions/${state.selectedPromptVersionNo}/test-runs?limit=50`,
    );
    state.promptTestRuns = Array.isArray(rows) ? rows : [];
    renderPromptTestRuns(state.promptTestRuns);

    const selectedId = preferredRunId || state.selectedPromptTestRunId || state.promptTestRuns[0]?.id || null;
    state.selectedPromptTestRunId = selectedId;
    const selected = state.promptTestRuns.find((item) => item.id === selectedId);
    if (selected) {
      renderPromptTestRunDetails(selected);
    } else {
      renderPromptTestRunPlaceholder();
    }
    renderPromptTestRuns(state.promptTestRuns);
  } catch (error) {
    $("promptTestRunStatus").textContent = `Load test runs failed: ${error.message}`;
    renderPromptTestRunPlaceholder(`Load test runs failed: ${error.message}`);
  }
}

function getSelectedPromptTestRun() {
  return state.promptTestRuns.find((item) => item.id === state.selectedPromptTestRunId) || null;
}

function exportPromptTestRunJson() {
  const run = getSelectedPromptTestRun();
  if (!run) {
    $("promptTestRunStatus").textContent = "Select a test run first";
    return;
  }
  const blob = new Blob([JSON.stringify(run, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `prompt-test-run-${run.id}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function exportPromptTestRunPdf() {
  const run = getSelectedPromptTestRun();
  if (!run) {
    $("promptTestRunStatus").textContent = "Select a test run first";
    return;
  }
  const section = document.createElement("section");
  section.style.background = "#ffffff";
  section.style.padding = "14px";
  section.style.fontFamily = '"Space Grotesk", Arial, sans-serif';
  section.style.width = "1020px";

  const heading = document.createElement("h2");
  heading.textContent = `Prompt test run ${run.id}`;
  section.appendChild(heading);

  const details = $("promptTestRunDetails").cloneNode(true);
  section.appendChild(details);
  document.body.appendChild(section);

  try {
    await exportElementToPdf(section, `prompt-test-run-${run.id}.pdf`, heading.textContent);
  } catch (error) {
    $("promptTestRunStatus").textContent = `Export failed: ${error.message}`;
  } finally {
    section.remove();
  }
}

async function loadPromptVersionDetails() {
  if (!state.selectedPromptChainId || !state.selectedPromptVersionNo) {
    $("promptVersionMarkdown").innerHTML = "";
    return;
  }
  try {
    const version = await api(
      `/v1/prompt-versions/chains/${state.selectedPromptChainId}/versions/${state.selectedPromptVersionNo}`,
    );
    renderMarkdown($("promptVersionMarkdown"), version.content || "");
  } catch (error) {
    $("promptVersionMarkdown").textContent = `Load version content failed: ${error.message}`;
  }
}

async function loadSettings() {
  if (state.currentUser?.role !== "admin") return;
  try {
    $("settingsStatus").textContent = "";
    await loadProviderMeta();
    await loadRoles();
    state.settings = await api("/v1/admin/config/");
    renderOptimizerSettings();
    renderUserRoleOptions();
    await syncOptimizerModels();
    await syncCompressionModels();
    await syncTestLlmModels();
    updateLlmSaveButtonsState();
    renderSettingsTable();
    await refreshUsers();
  } catch (error) {
    $("settingsStatus").textContent = `Settings load failed: ${error.message}`;
  }
}

async function saveSetting(key, value) {
  try {
    await api(`/v1/admin/config/${encodeURIComponent(key)}?value=${encodeURIComponent(value)}`, {
      method: "PUT",
    });
    state.settings[key] = value;
    $("settingsStatus").textContent = `Saved ${key}`;
  } catch (error) {
    $("settingsStatus").textContent = `Save failed for ${key}: ${error.message}`;
  }
}

function logout() {
  state.accessToken = "";
  state.refreshToken = "";
  state.currentUser = null;
  state.selectedThreadId = null;
  state.threadMessages = [];
  state.threadAnalysisReport = null;
  state.threadAnalysisLog = null;
  state.threadChartLabelMode = "smart";
  state.selectedPromptChainId = null;
  state.selectedPromptVersionNo = null;
  state.promptChainAnalysisPoints = [];
  state.promptTestRuns = [];
  state.selectedPromptTestRunId = null;
  state.settings = {};

  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);

  $("threadsList").innerHTML = "";
  $("messagesList").innerHTML = "";
  renderThreadAnalysisPlaceholder("Select a thread and click Analyze.");
  $("threadDetailsTitle").textContent = "Thread details";
  $("threadDetailsHint").textContent = "Select a thread to view messages and analysis.";

  $("promptChainsList").innerHTML = "";
  $("promptVersionsList").innerHTML = "";
  $("promptChainDetailsTitle").textContent = "Prompt chain details";
  $("promptChainDetailsHint").textContent = "Select a chain to inspect versions and analysis.";
  $("promptChainAnalysisSummary").textContent = "";
  $("promptVersionAnalysis").innerHTML = '<p class="analysis-placeholder">Select a version to view analysis.</p>';
  $("promptTestRunStatus").textContent = "";
  $("promptTestRunsList").innerHTML = "";
  renderPromptTestRunPlaceholder("Select a version and run a test.");
  $("promptVersionMarkdown").innerHTML = "";
  $("promptChainTrendChart").innerHTML = "";
  $("promptChainMetricsTable").querySelector("tbody").innerHTML = "";
  $("settingsTable").querySelector("tbody").innerHTML = "";
  $("usersTable").querySelector("tbody").innerHTML = "";

  $("changePasswordStatus").textContent = "";
  $("pwdCurrent").value = "";
  $("pwdNew").value = "";
  $("menuPassword").value = "";
  $("authMenuStatus").textContent = "";

  toggleStatusMenu(false);
  renderAuth();
  updateThreadChartLabelModeButton();
  setActiveTab("panelCreateThread");
}

function bindEvents() {
  $("loginBtn").addEventListener("click", () => login("/v1/auth/login"));
  $("bootstrapBtn").addEventListener("click", () => login("/v1/auth/bootstrap-admin"));
  $("logoutBtn").addEventListener("click", logout);

  $("statusToggleBtn").addEventListener("click", () => toggleStatusMenu());
  document.addEventListener("click", (event) => {
    const popover = $("statusPopover");
    if (!popover.contains(event.target)) {
      toggleStatusMenu(false);
    }
  });

  $("changePasswordBtn").addEventListener("click", changePassword);

  document.querySelectorAll(".status-tab").forEach((tabButton) => {
    tabButton.addEventListener("click", () => {
      setStatusMenuTab(tabButton.dataset.statusTarget);
    });
  });

  document.querySelectorAll(".settings-tab").forEach((tabButton) => {
    tabButton.addEventListener("click", () => {
      setSettingsSubTab(tabButton.dataset.settingsTarget);
    });
  });

  $("createThreadBtn").addEventListener("click", createThread);
  $("appendMessageBtn").addEventListener("click", appendMessage);
  $("refreshThreadsBtn").addEventListener("click", refreshThreads);
  $("refreshMessagesBtn").addEventListener("click", loadThreadDetails);
  $("importJsonBtn").addEventListener("click", importJson);
  $("importTextBtn").addEventListener("click", importText);
  $("analyzeThreadChainBtn").addEventListener("click", (event) => {
    event.preventDefault();
    closeDetailsMenu("threadAnalyzeMenu");
    analyzeThread();
  });
  $("orchestrateAnalyzeThreadChainBtn").addEventListener("click", (event) => {
    event.preventDefault();
    closeDetailsMenu("threadAnalyzeMenu");
    orchestrateAndAnalyzeThreadChain();
  });
  $("threadChartLabelModeBtn").addEventListener("click", cycleThreadChartLabelMode);
  $("exportThreadAnalysisPdfBtn").addEventListener("click", exportThreadAnalysisPdf);

  $("refreshPromptChainsBtn").addEventListener("click", refreshPromptChains);
  $("createPromptChainBtn").addEventListener("click", createPromptChain);
  $("refreshPromptVersionsBtn").addEventListener("click", loadPromptChainDetails);
  $("createPromptVersionBtn").addEventListener("click", createPromptVersion);
  $("analyzePromptChainBtn").addEventListener("click", (event) => {
    event.preventDefault();
    handlePromptChainAnalyzeChoice("chain");
  });
  $("previewPromptOrchestratorBtn").addEventListener("click", (event) => {
    event.preventDefault();
    handlePromptChainAnalyzeChoice("orchestrator");
  });
  $("exportPromptAnalysisPdfBtn").addEventListener("click", exportPromptAnalysisPdf);
  $("runPromptTestBtn").addEventListener("click", runPromptTest);
  $("refreshPromptTestsBtn").addEventListener("click", () => refreshPromptTests());
  $("exportPromptTestRunJsonBtn").addEventListener("click", exportPromptTestRunJson);
  $("exportPromptTestRunPdfBtn").addEventListener("click", exportPromptTestRunPdf);

  $("refreshSettingsBtn").addEventListener("click", loadSettings);
  $("createUserBtn").addEventListener("click", createUserFromSettings);
  $("refreshUsersBtn").addEventListener("click", refreshUsers);

  $("optimizerProvider").addEventListener("change", async () => {
    const provider = $("optimizerProvider").value;
    $("optimizerBaseUrl").value = getDefaultProviderBaseUrl(provider);
    await syncOptimizerModels();
  });
  $("reloadOptimizerModelsBtn").addEventListener("click", syncOptimizerModels);
  $("saveOptimizerSettingsBtn").addEventListener("click", saveOptimizerSettings);
  $("optimizerModel").addEventListener("change", updateLlmSaveButtonsState);

  $("compressionProvider").addEventListener("change", async () => {
    const provider = $("compressionProvider").value;
    $("compressionBaseUrl").value = getDefaultProviderBaseUrl(provider);
    await syncCompressionModels();
  });
  $("reloadCompressionModelsBtn").addEventListener("click", syncCompressionModels);
  $("saveCompressionSettingsBtn").addEventListener("click", saveCompressionSettings);
  $("compressionModel").addEventListener("change", updateLlmSaveButtonsState);

  $("testLlmProvider").addEventListener("change", async () => {
    const provider = $("testLlmProvider").value;
    $("testLlmBaseUrl").value = getDefaultProviderBaseUrl(provider) || "http://127.0.0.1:11434";
    await syncTestLlmModels();
  });
  $("reloadTestLlmModelsBtn").addEventListener("click", syncTestLlmModels);
  $("saveTestLlmSettingsBtn").addEventListener("click", saveTestLlmSettings);
  $("testLlmModel").addEventListener("change", updateLlmSaveButtonsState);

  $("llmAutoProvider").addEventListener("change", () => {
    const provider = $("llmAutoProvider").value;
    $("llmAutoBaseUrl").value = getDefaultProviderBaseUrl(provider) || "";
  });
  $("previewLlmAutoBtn").addEventListener("click", previewLlmAutoSetup);
  $("applyLlmAutoBtn").addEventListener("click", applyLlmAutoSetup);

  document.querySelectorAll(".tab").forEach((tabButton) => {
    tabButton.addEventListener("click", async () => {
      const targetId = tabButton.dataset.target;
      setActiveTab(targetId);
      if (targetId === "panelPromptVersions") {
        await refreshPromptChains();
      }
      if (targetId === "panelSettings") {
        await loadSettings();
        setSettingsSubTab("settingsPanelLlm");
      }
    });
  });
}

(async function init() {
  bindEvents();
  renderAuth();
  await loadAppVersion();
  setActiveTab("panelCreateThread");
  toggleStatusMenu(false);
  setStatusMenuTab("statusPanelAuth");
  setSettingsSubTab("settingsPanelLlm");
  updateThreadChartLabelModeButton();
  renderThreadAnalysisPlaceholder("Select a thread and click Analyze.");
  $("promptVersionAnalysis").innerHTML = '<p class="analysis-placeholder">Select a version to view analysis.</p>';
  renderPromptTestRunPlaceholder("Select a version and run a test.");
  updateLlmSaveButtonsState();

  if (!state.accessToken) return;

  try {
    state.currentUser = await api("/v1/auth/me");
    renderAuth();
    await refreshThreads();
    await refreshPromptChains();
    if (state.currentUser?.role === "admin") {
      await loadSettings();
    }
  } catch (_error) {
    logout();
  }
})();
