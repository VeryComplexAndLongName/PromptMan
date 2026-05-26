const { createApp, ref, computed, onMounted, onBeforeUnmount } = Vue;

marked.setOptions({ breaks: true, gfm: true });
const md        = (text) => marked.parse(text || "");
const parseTags = (raw)  => raw.split(",").map((t) => t.trim()).filter(Boolean);
const tagsToStr = (tags) => tags.join(", ");
const key       = (p)   => p.project + "/" + p.name;
const AUTH_TOKEN_STORAGE_KEY = "promptman.access_token";
const REFRESH_TOKEN_STORAGE_KEY = "promptman.refresh_token";
const ACCESS_TOKEN_EXPIRES_AT_STORAGE_KEY = "promptman.access_token_expires_at";
const NEXT_REFRESH_AT_STORAGE_KEY = "promptman.next_refresh_at";
const PLUGIN_TAG_MATCH_MODE_STORAGE_KEY = "promptman.plugin_tag_match_mode";
const PLUGIN_ROUTES_OPEN_STORAGE_KEY = "promptman.plugin_routes_open";
const PLUGIN_FILTER_BAR_OPEN_STORAGE_KEY = "promptman.plugin_filter_bar_open";
const emptyPromptData = () => ({
  role: "",
  task: "",
  context: "",
  constraints: "",
  output_format: "",
  examples: "",
});
const defaultOptimizeConfig = () => ({
  llm_provider: "ollama",
  llm_model: "qwen2.5:0.5b",
  llm_base_url: "http://127.0.0.1:11434",
  llm_timeout_seconds: 300,
  llm_api_token: "",
  effective_llm_provider: "ollama",
  effective_llm_model: "qwen2.5:0.5b",
  effective_llm_base_url: "http://127.0.0.1:11434",
  effective_llm_timeout_seconds: 300,
  effective_has_llm_api_token: false,
});
const emptyUserForm = () => ({
  username: "",
  password: "",
  role: "developer",
  projects: [],
  is_active: true,
});
const emptyProjectForm = () => ({
  name: "",
});
const defaultUserRoleOptions = ["admin", "developer"];
const initialLlmProviderConfigs = {
  ollama: {
    label: "Ollama (Local)",
    baseUrl: "http://127.0.0.1:11434",
    requiresApiToken: false,
    models: [
      "qwen2.5:3b-instruct-q4_K_M",
      "qwen2.5:0.5b",
      "qwen3:4b",
      "llama3.2:1b",
      "llama3.2:latest",
      "llama3.1:latest",
      "deepseek-r1:latest",
      "codellama:latest",
    ],
  },
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    requiresApiToken: true,
    models: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
  },
  anthropic: {
    label: "Anthropic Claude",
    baseUrl: "https://api.anthropic.com",
    requiresApiToken: true,
    models: ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
  },
};

// Build markdown from decomposed fields
const buildPromptMarkdown = (fields) => {
  const parts = [];
  if (fields.role?.trim())           parts.push(`**Role:** ${fields.role}`);
  if (fields.task?.trim())           parts.push(`**Task:** ${fields.task}`);
  if (fields.constraints?.trim())    parts.push(`**Constraints:** ${fields.constraints}`);
  if (fields.output_format?.trim())  parts.push(`**Output format:** ${fields.output_format}`);
  if (fields.examples?.trim())       parts.push(`**Examples:** ${fields.examples}`);
  if (fields.context?.trim())        parts.push(`**Context:** ${fields.context}`);
  return parts.join("\n\n");
};

const readJsonStorage = (storageKey, fallback) => {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : fallback;
  } catch (_err) {
    return fallback;
  }
};

const normalizePluginTagMatchMode = (value) => (String(value || "").toLowerCase() === "and" ? "and" : "or");

createApp({
  setup() {
    /* app meta */
    const appVersion = ref("");

    /* auth */
    const authReady = ref(false);
    const authToken = ref(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "");
    const refreshToken = ref(window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY) || "");
    const accessTokenExpiresAt = ref(Number(window.localStorage.getItem(ACCESS_TOKEN_EXPIRES_AT_STORAGE_KEY) || 0));
    const nextRefreshAt = ref(Number(window.localStorage.getItem(NEXT_REFRESH_AT_STORAGE_KEY) || 0));
    const clockNow = ref(Date.now());
    const currentUser = ref(null);
    const authMode = ref("login");
    const authForm = ref({ username: "", password: "" });
    const authError = ref("");
    const authStatus = ref("");
    const authBusy = ref(false);
    const authBootstrapRequired = ref(false);

    /* tabs */
    const activeTab = ref("browse");

    /* create form */
    const form         = ref({ name: "", project: "", tags: "", role: "", task: "", context: "", constraints: "", output_format: "", examples: "" });
    const createStatus = ref("");

    /* browse */
    const items         = ref([]);
    const filterProject = ref("");
    const filterTag     = ref("");
    const browsePage    = ref(1);
    const browsePageSize = ref(10);
    const browseTotalItems = ref(0);
    const browseSortBy = ref("updated_at");
    const browseSortOrder = ref("desc");

    /* expanded prompt state */
    const expandedKey       = ref(null);
    const expandedVersions  = ref([]);
    const openVersionKey    = ref(null);
    const editTagsMode      = ref(false);
    const editTagsStr       = ref("");
    const newVersionRole    = ref("");
    const newVersionTask    = ref("");
    const newVersionContext = ref("");
    const newVersionConstraints = ref("");
    const newVersionOutputFormat = ref("");
    const newVersionExamples = ref("");
    const saveStatus        = ref("");
    const deleteStatus      = ref("");
    const newVersionEditorOpen = ref(false);

    /* optimizer */
    const createOptimizeMenuOpen = ref(false);
    const browseOptimizeMenuKey = ref(null);
    const optimizerModalOpen = ref(false);
    const optimizerLoading = ref(false);
    const optimizerError = ref("");
    const optimizerStatus = ref("");
    const optimizerMode = ref("optimizer");
    const optimizerLogs = ref([]);
    const optimizerEngine = ref("");
    const optimizerNotes = ref([]);
    const optimizerElapsedSeconds = ref(null);
    const optimizedMarkdown = ref("");
    const optimizedDraft = ref(emptyPromptData());
    const optimizeInputSource = ref("create");
    const optimizeTargetPrompt = ref(null);
    const optimizeEndpoint = ref("/v1/optimize");
    const optimizeConfig = ref(defaultOptimizeConfig());
    const optimizeConfigStatus = ref("");
    const llmProviderConfigs = ref(structuredClone(initialLlmProviderConfigs));
    const llmProviderOptions = computed(() => Object.keys(llmProviderConfigs.value));
    const defaultLlmModelsByProvider = computed(() =>
      Object.fromEntries(Object.entries(llmProviderConfigs.value).map(([key, config]) => [key, config.models]))
    );
    const availableLlmModels = ref([...(initialLlmProviderConfigs.ollama?.models || [])]);
    const llmModelsLoading = ref(false);
    const llmModelsLoadError = ref("");
    const activeOptimizationJobId = ref("");
    let optimizerPollTimerId = null;

    /* admin */
    const roleOptions = ref([...defaultUserRoleOptions, "viewer"]);
    const projects = ref([]);
    const projectsLoading = ref(false);
    const projectsStatus = ref("");
    const newProjectForm = ref(emptyProjectForm());
    const editingProjectId = ref(null);
    const editProjectForm = ref(emptyProjectForm());
    const users = ref([]);
    const usersLoading = ref(false);
    const usersStatus = ref("");
    const newUserForm = ref(emptyUserForm());
    const editingUserId = ref(null);
    const editUserForm = ref(emptyUserForm());
    const globalConfigEntries = ref([]);
    const globalConfigLoading = ref(false);
    const globalConfigStatus = ref("");

    /* plugins */
    const plugins = ref([]);
    const pluginsLoading = ref(false);
    const pluginsStatus = ref("");
    const pluginControlValues = ref({});
    const pluginResponses = ref({});
    const pluginDiagnostics = ref({});
    const pluginDiagnosticsLoading = ref({});
    const pluginDiagnosticsOpen = ref({});
    const pluginModalOpen = ref(false);
    const pluginModalLoading = ref(false);
    const pluginModalError = ref("");
    const pluginModalStatus = ref("");
    const pluginModalSession = ref(null);
    const pluginModalPluginName = ref("");
    const pluginModalEndpointName = ref("");
    const pluginModalBackdropArmed = ref(false);
    const pluginNameFilter = ref("");
    const pluginTagFilters = ref([]);
    const pluginTagMatchMode = ref(normalizePluginTagMatchMode(window.localStorage.getItem(PLUGIN_TAG_MATCH_MODE_STORAGE_KEY)));
    const pluginRoutesOpen = ref(readJsonStorage(PLUGIN_ROUTES_OPEN_STORAGE_KEY, {}));
    const pluginFilterBarOpen = ref(window.localStorage.getItem(PLUGIN_FILTER_BAR_OPEN_STORAGE_KEY) === "true");

    /* change password */
    const changePasswordForm = ref({ current_password: "", new_password: "", confirm_password: "" });
    const changePasswordStatus = ref("");
    const changePasswordBusy = ref(false);

    const isAuthenticated = computed(() => !!currentUser.value);
    const isAdmin = computed(() => currentUser.value?.role === "admin");
    const isViewer = computed(() => currentUser.value?.role === "viewer");
    const canViewAdmin = computed(() => currentUser.value?.role === "admin");
    const canWrite = computed(() => !!currentUser.value && currentUser.value.role !== "viewer");
    const optimizerTimeoutSeconds = computed(() =>
      Number(optimizeConfig.value.effective_llm_timeout_seconds || optimizeConfig.value.llm_timeout_seconds || 0)
    );
    const optimizerElapsedPercent = computed(() => {
      if (optimizerElapsedSeconds.value === null || optimizerTimeoutSeconds.value <= 0) {
        return null;
      }
      return (optimizerElapsedSeconds.value / optimizerTimeoutSeconds.value) * 100;
    });
    const optimizerElapsedSeverity = computed(() => {
      if (optimizerElapsedPercent.value === null) return "ok";
      if (optimizerElapsedPercent.value >= 100) return "error";
      if (optimizerElapsedPercent.value >= 80) return "warn";
      return "ok";
    });
    const availableProjectNames = computed(() => projects.value.map((project) => project.name));
    const currentUserProjectsLabel = computed(() => {
      if (!currentUser.value) return "";
      if (["admin", "viewer"].includes(currentUser.value.role)) return "All projects";
      return (currentUser.value.projects || []).length ? currentUser.value.projects.join(", ") : "No assigned projects";
    });

    const getPluginTags = (plugin) => {
      const tags = [];
      const state = String(plugin?.state || "").trim().toLowerCase();
      if (state) tags.push(state);
      if (plugin?.available) tags.push("available");
      if (!plugin?.compatible) tags.push("incompatible");
      if (plugin?.signature_status) tags.push(String(plugin.signature_status).toLowerCase());
      if ((plugin?.health_failures || 0) > 0) tags.push("health-failed");
      if (plugin?.runtime_failures && Object.keys(plugin.runtime_failures).length) tags.push("runtime-failed");
      if ((plugin?.active_routes || []).length) tags.push("running");
      if ((plugin?.ui_controls || []).length) tags.push("ui");
      if ((plugin?.hooks || []).length) tags.push("hooks");
      if ((plugin?.endpoints || []).some((endpoint) => !!endpoint.launches_modal)) tags.push("modal");
      return [...new Set(tags)];
    };

    const availablePluginTags = computed(() => {
      const tags = new Set();
      plugins.value.forEach((plugin) => {
        getPluginTags(plugin).forEach((tag) => tags.add(tag));
      });
      return Array.from(tags).sort((left, right) => left.localeCompare(right));
    });

    const pluginTagFilterGroups = computed(() => {
      const available = availablePluginTags.value;
      const assigned = new Set();
      const groupDefinitions = [
        { key: "status", label: "Status", tags: ["running", "available", "incompatible", "health-failed", "runtime-failed"] },
        { key: "signature", label: "Signature", tags: ["verified", "unsigned", "invalid"] },
        { key: "capabilities", label: "Capabilities", tags: ["ui", "hooks", "modal"] },
      ];

      const groups = groupDefinitions.map((group) => {
        const tags = group.tags.filter((tag) => available.includes(tag));
        tags.forEach((tag) => assigned.add(tag));
        return { ...group, tags };
      }).filter((group) => group.tags.length);

      const otherTags = available.filter((tag) => !assigned.has(tag));
      if (otherTags.length) {
        groups.push({ key: "other", label: "Other", tags: otherTags });
      }
      return groups;
    });

    const filteredPlugins = computed(() => {
      const nameNeedle = String(pluginNameFilter.value || "").trim().toLowerCase();
      const selectedTags = new Set((pluginTagFilters.value || []).map((tag) => String(tag || "").trim().toLowerCase()).filter(Boolean));
      return plugins.value.filter((plugin) => {
        const nameMatches = !nameNeedle || String(plugin?.name || "").toLowerCase().includes(nameNeedle);
        if (!nameMatches) return false;
        if (!selectedTags.size) return true;
        const pluginTags = new Set(getPluginTags(plugin));
        if (pluginTagMatchMode.value === "and") {
          for (const tag of selectedTags) {
            if (!pluginTags.has(tag)) {
              return false;
            }
          }
          return true;
        }
        for (const tag of selectedTags) {
          if (pluginTags.has(tag)) {
            return true;
          }
        }
        return false;
      });
    });

    const togglePluginTagFilter = (tag) => {
      const normalized = String(tag || "").trim().toLowerCase();
      if (!normalized) return;
      const next = new Set(pluginTagFilters.value);
      if (next.has(normalized)) {
        next.delete(normalized);
      } else {
        next.add(normalized);
      }
      pluginTagFilters.value = [...next].sort((left, right) => left.localeCompare(right));
    };

    const clearPluginFilters = () => {
      pluginNameFilter.value = "";
      pluginTagFilters.value = [];
    };

    const togglePluginFilterBar = () => {
      pluginFilterBarOpen.value = !pluginFilterBarOpen.value;
      window.localStorage.setItem(PLUGIN_FILTER_BAR_OPEN_STORAGE_KEY, pluginFilterBarOpen.value ? "true" : "false");
    };

    const isPluginTagActive = (tag) => pluginTagFilters.value.includes(String(tag || "").trim().toLowerCase());

    const setPluginTagMatchMode = (mode) => {
      pluginTagMatchMode.value = normalizePluginTagMatchMode(mode);
      window.localStorage.setItem(PLUGIN_TAG_MATCH_MODE_STORAGE_KEY, pluginTagMatchMode.value);
    };

    const isPluginRoutesOpen = (pluginName) => !!pluginRoutesOpen.value?.[pluginName];

    const savePluginRoutesOpen = () => {
      window.localStorage.setItem(PLUGIN_ROUTES_OPEN_STORAGE_KEY, JSON.stringify(pluginRoutesOpen.value));
    };

    const togglePluginRoutes = (pluginName) => {
      if (!pluginName) return;
      const next = { ...pluginRoutesOpen.value };
      if (isPluginRoutesOpen(pluginName)) {
        delete next[pluginName];
      } else {
        next[pluginName] = true;
      }
      pluginRoutesOpen.value = next;
      savePluginRoutesOpen();
    };

    const nowTime = () => new Date(Date.now()).toISOString().replace("T", " ").replace("Z", " UTC");
    let tokenRefreshPromise = null;
    let proactiveRefreshTimerId = null;
    let countdownTimerId = null;

    const formatUtcDateTime = (value) => {
      if (!value) return "unknown UTC";
      const parsed = new Date(value);
      if (Number.isNaN(parsed.getTime())) return `${String(value)} UTC`;
      return parsed.toISOString().replace("T", " ").replace("Z", " UTC");
    };

    const formatAuditLine = (label, timestamp, username) => {
      return `${label}: ${formatUtcDateTime(timestamp)}${username ? ` by ${username}` : ""}`;
    };

    const MAX_HEADER_TAGS = 3;
    const visibleHeaderTags = (tags) => {
      if (!Array.isArray(tags)) return [];
      return tags.slice(0, MAX_HEADER_TAGS);
    };
    const hiddenHeaderTagCount = (tags) => {
      if (!Array.isArray(tags)) return 0;
      return Math.max(0, tags.length - MAX_HEADER_TAGS);
    };

    const formatCountdown = (targetTsSeconds) => {
      if (!targetTsSeconds) return "not scheduled";
      const remainingMs = Math.max(0, targetTsSeconds * 1000 - clockNow.value);
      const totalSeconds = Math.floor(remainingMs / 1000);
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    };

    const accessTokenCountdown = computed(() => formatCountdown(accessTokenExpiresAt.value));
    const nextRefreshCountdown = computed(() => formatCountdown(nextRefreshAt.value));

    const setDefaultActiveTab = () => {
      activeTab.value = currentUser.value?.role === "admin" ? "admin" : "browse";
    };

    const normalizeProjects = (raw) => {
      if (Array.isArray(raw)) {
        return raw.map((item) => String(item || "").trim()).filter(Boolean);
      }
      return String(raw || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    };

    const clearProactiveRefresh = () => {
      if (proactiveRefreshTimerId !== null) {
        window.clearTimeout(proactiveRefreshTimerId);
        proactiveRefreshTimerId = null;
      }
      nextRefreshAt.value = 0;
      window.localStorage.removeItem(NEXT_REFRESH_AT_STORAGE_KEY);
    };

    const scheduleProactiveRefresh = () => {
      clearProactiveRefresh();
      if (!refreshToken.value || !accessTokenExpiresAt.value) {
        return;
      }

      const leadTimeMs = 60_000 + Math.floor(Math.random() * 120_000);
      const delayMs = Math.max(5_000, (accessTokenExpiresAt.value * 1000) - Date.now() - leadTimeMs);
      nextRefreshAt.value = Math.floor((Date.now() + delayMs) / 1000);
      window.localStorage.setItem(NEXT_REFRESH_AT_STORAGE_KEY, String(nextRefreshAt.value));
      proactiveRefreshTimerId = window.setTimeout(async () => {
        const refreshed = await refreshSession(false);
        if (!refreshed) {
          clearSession("Session expired. Please sign in again.");
        }
      }, delayMs);
    };

    const saveTokens = (accessToken, nextRefreshToken = refreshToken.value, nextAccessTokenExpiresAt = accessTokenExpiresAt.value) => {
      authToken.value = accessToken || "";
      refreshToken.value = nextRefreshToken || "";
      accessTokenExpiresAt.value = Number(nextAccessTokenExpiresAt || 0);
      if (authToken.value) {
        window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, authToken.value);
      } else {
        window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      }
      if (refreshToken.value) {
        window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken.value);
      } else {
        window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
      }
      if (accessTokenExpiresAt.value) {
        window.localStorage.setItem(ACCESS_TOKEN_EXPIRES_AT_STORAGE_KEY, String(accessTokenExpiresAt.value));
      } else {
        window.localStorage.removeItem(ACCESS_TOKEN_EXPIRES_AT_STORAGE_KEY);
      }
      scheduleProactiveRefresh();
    };

    const clearSession = (reason = "") => {
      saveTokens("", "");
      clearProactiveRefresh();
      currentUser.value = null;
      activeTab.value = "browse";
      items.value = [];
      browseTotalItems.value = 0;
      expandedKey.value = null;
      expandedVersions.value = [];
      optimizerModalOpen.value = false;
      activeOptimizationJobId.value = "";
      if (optimizerPollTimerId !== null) {
        window.clearTimeout(optimizerPollTimerId);
        optimizerPollTimerId = null;
      }
      users.value = [];
      projects.value = [];
      plugins.value = [];
      pluginControlValues.value = {};
      pluginResponses.value = {};
      pluginsStatus.value = "";
      optimizeConfig.value = defaultOptimizeConfig();
      globalConfigEntries.value = [];
      globalConfigStatus.value = "";
      if (reason) {
        authError.value = reason;
      }
    };

    const authHeaders = (headers = {}) => {
      const merged = { ...headers };
      if (authToken.value) {
        merged.Authorization = `Bearer ${authToken.value}`;
      }
      return merged;
    };

    const consumeAuthPayload = (payload) => {
      saveTokens(payload.access_token || "", payload.refresh_token || "", payload.access_token_expires_at || 0);
      if (payload.user) {
        currentUser.value = payload.user;
      }
    };

    const refreshSession = async (showStatusMessage = true) => {
      if (!refreshToken.value) {
        return false;
      }
      if (tokenRefreshPromise) {
        return tokenRefreshPromise;
      }

      tokenRefreshPromise = (async () => {
        try {
          const res = await fetch("/v1/auth/refresh", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken.value }),
          });
          if (!res.ok) {
            return false;
          }
          const payload = await res.json();
          consumeAuthPayload(payload);
          if (showStatusMessage) {
            authStatus.value = "Session refreshed.";
          }
          authError.value = "";
          return true;
        } catch (err) {
          return false;
        } finally {
          tokenRefreshPromise = null;
        }
      })();

      return tokenRefreshPromise;
    };

    const apiFetch = async (url, options = {}, retryOn401 = true) => {
      const requestOptions = {
        ...options,
        headers: authHeaders(options.headers || {}),
      };
      let response = await fetch(url, requestOptions);
      if (response.status === 401 && retryOn401 && refreshToken.value && !String(url).startsWith("/v1/auth/refresh")) {
        const refreshed = await refreshSession();
        if (refreshed) {
          response = await fetch(url, {
            ...options,
            headers: authHeaders(options.headers || {}),
          });
          if (response.status !== 401) {
            return response;
          }
        }
      }
      if (response.status === 401) {
        clearSession("Session expired. Please sign in again.");
      }
      return response;
    };

    const fetchAuthStatus = async () => {
      try {
        const res = await fetch("/v1/auth/status");
        if (!res.ok) {
          authBootstrapRequired.value = false;
          authMode.value = "login";
          return;
        }
        const payload = await res.json();
        authBootstrapRequired.value = !!payload.bootstrap_required;
        authMode.value = payload.bootstrap_required ? "bootstrap" : "login";
      } catch (err) {
        authBootstrapRequired.value = false;
        authMode.value = "login";
      }
    };

    const loadUsers = async () => {
      if (!canViewAdmin.value) {
        users.value = [];
        return;
      }
      usersLoading.value = true;
      usersStatus.value = "";
      const res = await apiFetch("/v1/users");
      if (!res.ok) {
        usersLoading.value = false;
        usersStatus.value = `Failed to load users (${res.status})`;
        return;
      }
      users.value = await res.json();
      usersLoading.value = false;
    };

    const loadProjects = async () => {
      if (!canViewAdmin.value) {
        projects.value = [];
        return;
      }
      projectsLoading.value = true;
      projectsStatus.value = "";
      const res = await apiFetch("/v1/projects");
      if (!res.ok) {
        projectsLoading.value = false;
        projectsStatus.value = `Failed to load projects (${res.status})`;
        return;
      }
      projects.value = await res.json();
      projectsLoading.value = false;
    };

    const loadRoles = async () => {
      if (!canViewAdmin.value) {
        roleOptions.value = [...defaultUserRoleOptions, "viewer"];
        return;
      }
      const res = await apiFetch("/v1/roles");
      if (!res.ok) {
        roleOptions.value = [...defaultUserRoleOptions, "viewer"];
        return;
      }
      const roles = await res.json();
      roleOptions.value = Array.isArray(roles) && roles.length
        ? roles.map((item) => item.name)
        : [...defaultUserRoleOptions];
    };

    const loadGlobalConfig = async () => {
      if (!isAdmin.value) {
        globalConfigEntries.value = [];
        globalConfigStatus.value = "";
        return;
      }
      globalConfigLoading.value = true;
      globalConfigStatus.value = "";
      try {
        const res = await apiFetch("/v1/admin/config/");
        if (!res.ok) {
          globalConfigStatus.value = `Failed to load global config (${res.status})`;
          return;
        }
        const payload = await res.json();
        const entries = Object.entries(payload || {})
          .map(([key, value]) => ({
            key,
            value: String(value ?? ""),
            draft: String(value ?? ""),
            saving: false,
          }))
          .sort((a, b) => a.key.localeCompare(b.key));
        globalConfigEntries.value = entries;
      } catch (_err) {
        globalConfigStatus.value = "Failed to load global config (network error)";
      } finally {
        globalConfigLoading.value = false;
      }
    };

    const globalConfigBooleanKeys = new Set([
      "PROMPTMAN_CACHE_ENABLED",
      "PROMPTMAN_CACHE_PERSISTENCE_ENABLED",
      "PROMPTMAN_PLUGINS_SIGNED_ONLY",
    ]);

    const globalConfigIntegerKeys = new Set([
      "OPTIMIZER_TIMEOUT_SECONDS",
      "PROMPTMAN_CACHE_MAX_ENTRIES",
      "PROMPTMAN_CACHE_PERSISTENCE_LIMIT",
    ]);

    const globalConfigSelectKeys = new Set([
      "OPTIMIZER_BACKEND",
      "OPTIMIZER_PROVIDER",
    ]);

    const getGlobalConfigControlType = (entry) => {
      const key = String(entry?.key || "");
      if (globalConfigBooleanKeys.has(key)) return "boolean";
      if (globalConfigIntegerKeys.has(key)) return "integer";
      if (globalConfigSelectKeys.has(key)) return "select";
      return "text";
    };

    const getGlobalConfigOptions = (entry) => {
      const key = String(entry?.key || "");
      if (key === "OPTIMIZER_BACKEND") {
        return ["leo"];
      }
      if (key === "OPTIMIZER_PROVIDER") {
        const providers = llmProviderOptions.value || [];
        return providers.length ? providers : ["ollama", "openai", "anthropic"];
      }
      return [];
    };

    const setGlobalConfigBooleanDraft = (entry, checked) => {
      entry.draft = checked ? "true" : "false";
    };

    const normalizeGlobalConfigDraftForSave = (entry) => {
      const controlType = getGlobalConfigControlType(entry);
      if (controlType === "boolean") {
        const normalized = String(entry.draft || "").trim().toLowerCase();
        entry.draft = ["true", "1", "yes", "on"].includes(normalized) ? "true" : "false";
        return;
      }
      if (controlType === "integer") {
        const raw = String(entry.draft ?? "").trim();
        if (!/^-?\d+$/.test(raw)) {
          throw new Error("Value must be an integer");
        }
        entry.draft = String(parseInt(raw, 10));
      }
    };

    const resetGlobalConfigDraft = (entry) => {
      entry.draft = entry.value;
    };

    const saveGlobalConfigEntry = async (entry) => {
      if (!isAdmin.value) {
        return;
      }
      entry.saving = true;
      globalConfigStatus.value = "";
      try {
        normalizeGlobalConfigDraftForSave(entry);
        const params = new URLSearchParams({ value: String(entry.draft ?? "") });
        const res = await apiFetch(`/v1/admin/config/${encodeURIComponent(entry.key)}?${params.toString()}`, {
          method: "PUT",
        });
        if (!res.ok) {
          let detail = "";
          try {
            const body = await res.json();
            detail = body?.detail || "";
          } catch (_err) {
            detail = "";
          }
          globalConfigStatus.value = `Failed to save ${entry.key} (${res.status})${detail ? `: ${detail}` : ""}`;
          return;
        }

        entry.value = String(entry.draft ?? "");
        globalConfigStatus.value = `Saved ${entry.key}`;

        if (entry.key.startsWith("OPTIMIZER_") || entry.key === "OLLAMA_BASE_URL") {
          await loadOptimizeConfig();
        }
        if (entry.key === "PROMPTMAN_PLUGINS_SIGNED_ONLY") {
          await loadPlugins();
        }
      } catch (_err) {
        const details = _err?.message || "network error";
        globalConfigStatus.value = `Failed to save ${entry.key} (${details})`;
      } finally {
        entry.saving = false;
      }
    };

    const pluginHasImageIcon = (icon) => typeof icon === "string" && /^(\/|https?:)/i.test(icon);

    const pluginIconFallback = (plugin) => String(plugin?.name || "P").slice(0, 1).toUpperCase();

    const getPluginEndpointConfig = (plugin, endpointName) => {
      const endpoints = Array.isArray(plugin?.endpoints) ? plugin.endpoints : [];
      const baseName = String(endpointName || "").replace(/_init$/, "");
      return endpoints.find((item) => item.name === baseName) || null;
    };

    const getPluginInitValue = (plugin, control) => {
      const initKey = control.init_endpoint_name || `${control.endpoint_name}_init`;
      const initResult = plugin?.init_results?.[initKey];
      if (initResult && Object.prototype.hasOwnProperty.call(initResult, "value")) {
        return initResult.value;
      }
      return control.default_value ?? (control.control_type === "checkbox" ? false : "");
    };

    const ensurePluginControlBucket = (plugin) => {
      if (!plugin || !plugin.name) return;
      if (!pluginControlValues.value[plugin.name]) {
        pluginControlValues.value[plugin.name] = {};
      }
      (plugin.ui_controls || []).forEach((control) => {
        if (!(control.name in pluginControlValues.value[plugin.name])) {
          pluginControlValues.value[plugin.name][control.name] = getPluginInitValue(plugin, control);
        }
      });
    };

    const loadPlugins = async () => {
      if (!currentUser.value) {
        plugins.value = [];
        pluginControlValues.value = {};
        pluginResponses.value = {};
        pluginDiagnostics.value = {};
        pluginDiagnosticsLoading.value = {};
        pluginDiagnosticsOpen.value = {};
        pluginRoutesOpen.value = {};
        return;
      }
      pluginsLoading.value = true;
      pluginsStatus.value = "";
      const res = await apiFetch("/v1/plugins");
      if (!res.ok) {
        pluginsLoading.value = false;
        pluginsStatus.value = `Failed to load plugins (${res.status})`;
        return;
      }
      plugins.value = await res.json();
      plugins.value.forEach((plugin) => ensurePluginControlBucket(plugin));
      const names = new Set(plugins.value.map((plugin) => plugin.name));
      pluginDiagnostics.value = Object.fromEntries(
        Object.entries(pluginDiagnostics.value).filter(([name]) => names.has(name))
      );
      pluginDiagnosticsLoading.value = Object.fromEntries(
        Object.entries(pluginDiagnosticsLoading.value).filter(([name]) => names.has(name))
      );
      pluginDiagnosticsOpen.value = Object.fromEntries(
        Object.entries(pluginDiagnosticsOpen.value).filter(([name]) => names.has(name))
      );
      pluginRoutesOpen.value = Object.fromEntries(
        Object.entries(pluginRoutesOpen.value).filter(([name, isOpen]) => names.has(name) && !!isOpen)
      );
      savePluginRoutesOpen();
      if (isAdmin.value) {
        await Promise.all(plugins.value.map((plugin) => loadPluginDiagnostics(plugin.name, false)));
      }
      if (pluginModalOpen.value && pluginModalPluginName.value) {
        const modalPluginStillExists = plugins.value.some((plugin) => plugin.name === pluginModalPluginName.value);
        if (!modalPluginStillExists) {
          await closePluginModal(false);
        }
      }
      pluginsLoading.value = false;
    };

    const getPluginDiagnostics = (pluginName) => pluginDiagnostics.value?.[pluginName] || null;

    const isPluginDiagnosticsLoading = (pluginName) => !!pluginDiagnosticsLoading.value?.[pluginName];

    const isPluginDiagnosticsOpen = (pluginName) => !!pluginDiagnosticsOpen.value?.[pluginName];

    const loadPluginDiagnostics = async (pluginName, force = false) => {
      if (!isAdmin.value || !pluginName) {
        return;
      }
      if (!force && pluginDiagnostics.value?.[pluginName]) {
        return;
      }
      if (pluginDiagnosticsLoading.value?.[pluginName]) {
        return;
      }
      pluginDiagnosticsLoading.value[pluginName] = true;
      const res = await apiFetch(`/v1/plugins/${encodeURIComponent(pluginName)}/_diagnostics`);
      if (!res.ok) {
        pluginDiagnostics.value[pluginName] = {
          error: `Failed to load diagnostics (${res.status})`,
        };
        pluginDiagnosticsLoading.value[pluginName] = false;
        return;
      }
      let payload = {};
      try {
        payload = await res.json();
      } catch (_) {
        payload = { error: "Diagnostics response is invalid" };
      }
      pluginDiagnostics.value[pluginName] = payload;
      pluginDiagnosticsLoading.value[pluginName] = false;
    };

    const togglePluginDiagnostics = async (pluginName) => {
      const nextState = !isPluginDiagnosticsOpen(pluginName);
      pluginDiagnosticsOpen.value[pluginName] = nextState;
      if (nextState) {
        await loadPluginDiagnostics(pluginName, false);
      }
    };

    const getPluginModalLaunchers = (plugin) => {
      const endpoints = Array.isArray(plugin?.endpoints) ? plugin.endpoints : [];
      return endpoints.filter((endpoint) => !!endpoint.launches_modal);
    };

    const pluginModalControls = computed(() => pluginModalSession.value?.modal?.controls || []);

    const getPluginModalControlValue = (controlName) => {
      return pluginModalSession.value?.control_values?.[controlName];
    };

    const setPluginModalControlValue = (controlName, value) => {
      if (!pluginModalSession.value) return;
      if (!pluginModalSession.value.control_values) {
        pluginModalSession.value.control_values = {};
      }
      pluginModalSession.value.control_values[controlName] = value;
    };

    const openPluginModal = async (plugin, endpointName) => {
      if (!plugin?.name || !endpointName) return;
      pluginModalBackdropArmed.value = false;
      pluginModalLoading.value = true;
      pluginModalError.value = "";
      pluginModalStatus.value = "Opening modal...";
      try {
        const res = await apiFetch(`/v1/plugins/${encodeURIComponent(plugin.name)}/modals`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint_name: endpointName, payload: {}, controls: {} }),
        });
        if (!res.ok) {
          let detail = "";
          try {
            const body = await res.json();
            detail = body?.detail || "";
          } catch (_err) {
            detail = "";
          }
          pluginModalError.value = `Failed to open modal (${res.status})${detail ? `: ${detail}` : ""}`;
          return;
        }
        const session = await res.json();
        pluginModalSession.value = session;
        pluginModalPluginName.value = plugin.name;
        pluginModalEndpointName.value = endpointName;
        pluginModalOpen.value = true;
        pluginModalStatus.value = session?.modal?.status || "Modal opened";
      } catch (_err) {
        pluginModalError.value = "Failed to open modal (network error)";
      } finally {
        pluginModalLoading.value = false;
      }
    };

    const refreshPluginModal = async () => {
      if (!pluginModalSession.value?.session_id || !pluginModalPluginName.value) return;
      const res = await apiFetch(`/v1/plugins/${encodeURIComponent(pluginModalPluginName.value)}/modals/${encodeURIComponent(pluginModalSession.value.session_id)}`);
      if (!res.ok) {
        pluginModalError.value = `Failed to refresh modal (${res.status})`;
        return;
      }
      pluginModalSession.value = await res.json();
    };

    const invokePluginModalControl = async (control, overrideValue = undefined) => {
      if (!pluginModalSession.value?.session_id || !pluginModalPluginName.value) return;
      const value = overrideValue !== undefined ? overrideValue : getPluginModalControlValue(control.name);
      const currentControls = { ...(pluginModalSession.value.control_values || {}) };
      currentControls[control.name] = value;
      setPluginModalControlValue(control.name, value);

      const res = await apiFetch(
        `/v1/plugins/${encodeURIComponent(pluginModalPluginName.value)}/modals/${encodeURIComponent(pluginModalSession.value.session_id)}/controls/${encodeURIComponent(control.name)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ control_name: control.name, value, controls: currentControls }),
        }
      );
      if (!res.ok) {
        let detail = "";
        try {
          const body = await res.json();
          detail = body?.detail || "";
        } catch (_err) {
          detail = "";
        }
        pluginModalError.value = `Modal control failed (${res.status})${detail ? `: ${detail}` : ""}`;
        return;
      }
      pluginModalSession.value = await res.json();
      pluginModalStatus.value = pluginModalSession.value?.modal?.status || pluginModalStatus.value;
    };

    const stopPluginModal = async () => {
      if (!pluginModalSession.value?.session_id || !pluginModalPluginName.value) return;
      const res = await apiFetch(
        `/v1/plugins/${encodeURIComponent(pluginModalPluginName.value)}/modals/${encodeURIComponent(pluginModalSession.value.session_id)}/stop`,
        { method: "POST" }
      );
      if (!res.ok) {
        pluginModalError.value = `Failed to stop modal (${res.status})`;
        return;
      }
      pluginModalSession.value = await res.json();
      pluginModalStatus.value = pluginModalSession.value?.modal?.status || "Modal stopped";
    };

    const closePluginModal = async (removeRemote = true) => {
      pluginModalBackdropArmed.value = false;
      if (removeRemote && pluginModalSession.value?.session_id && pluginModalPluginName.value) {
        const res = await apiFetch(
          `/v1/plugins/${encodeURIComponent(pluginModalPluginName.value)}/modals/${encodeURIComponent(pluginModalSession.value.session_id)}`,
          { method: "DELETE" }
        );
        if (!res.ok && res.status !== 404) {
          pluginModalError.value = `Failed to close modal (${res.status})`;
          return;
        }
      }
      pluginModalOpen.value = false;
      pluginModalLoading.value = false;
      pluginModalError.value = "";
      pluginModalStatus.value = "";
      pluginModalSession.value = null;
      pluginModalPluginName.value = "";
      pluginModalEndpointName.value = "";
    };

    const handlePluginModalBackdropPointerDown = () => {
      pluginModalBackdropArmed.value = true;
    };

    const handlePluginModalBackdropClick = () => {
      if (!pluginModalBackdropArmed.value) {
        return;
      }
      pluginModalBackdropArmed.value = false;
      void closePluginModal(false);
    };

    const getPluginDiagnosticsSummary = (pluginName) => {
      const payload = getPluginDiagnostics(pluginName);
      if (!payload || payload.error) {
        return { blockedCount: 0, failureCount: 0 };
      }
      const endpointEntries = Array.isArray(payload.endpoint_diagnostics) ? payload.endpoint_diagnostics : [];
      const hookEntries = Array.isArray(payload.hook_diagnostics) ? payload.hook_diagnostics : [];
      const blockedCount = endpointEntries.filter((entry) => !!entry.blocked).length + hookEntries.filter((entry) => !!entry.blocked).length;
      const failureCount = endpointEntries.reduce((acc, entry) => acc + Number(entry.consecutive_failures || 0), 0)
        + hookEntries.reduce((acc, entry) => acc + Number(entry.consecutive_failures || 0), 0);
      return { blockedCount, failureCount };
    };

    const getPluginBlockedCount = (pluginName) => getPluginDiagnosticsSummary(pluginName).blockedCount;

    const getPluginFailureCount = (pluginName) => getPluginDiagnosticsSummary(pluginName).failureCount;

    const getPluginControlValue = (pluginName, controlName) => {
      return pluginControlValues.value?.[pluginName]?.[controlName];
    };

    const setPluginControlValue = (pluginName, controlName, value) => {
      if (!pluginControlValues.value[pluginName]) {
        pluginControlValues.value[pluginName] = {};
      }
      pluginControlValues.value[pluginName][controlName] = value;
    };

    const canUsePluginControl = (plugin, control) => {
      const endpoint = getPluginEndpointConfig(plugin, control.endpoint_name);
      if (!endpoint || !Array.isArray(endpoint.roles) || !endpoint.roles.length) {
        return true;
      }
      return endpoint.roles.includes(currentUser.value?.role);
    };

    const setPluginResponse = (pluginName, type, message) => {
      pluginResponses.value[pluginName] = { type, message };
    };

    const invokePluginControl = async (plugin, control, overrideValue = undefined) => {
      const endpoint = getPluginEndpointConfig(plugin, control.endpoint_name);
      if (!endpoint) {
        setPluginResponse(plugin.name, "err", `Unknown endpoint ${control.endpoint_name}`);
        return;
      }
      const currentBucket = { ...(pluginControlValues.value?.[plugin.name] || {}) };
      const value = overrideValue !== undefined ? overrideValue : currentBucket[control.name];
      currentBucket[control.name] = value;
      setPluginControlValue(plugin.name, control.name, value);

      const requestOptions = {
        method: endpoint.method || "POST",
      };
      if (!["GET", "DELETE"].includes(String(endpoint.method || "POST").toUpperCase())) {
        requestOptions.headers = { "Content-Type": "application/json" };
        requestOptions.body = JSON.stringify({
          value,
          control_name: control.name,
          controls: currentBucket,
        });
      }

      const res = await apiFetch(`/v1/plugins/${encodeURIComponent(plugin.name)}/${encodeURIComponent(control.endpoint_name)}`, requestOptions);
      if (!res.ok) {
        let details = "";
        try {
          const payload = await res.json();
          details = payload?.detail || "";
        } catch (_) {
          details = "";
        }
        setPluginResponse(plugin.name, "err", `Plugin call failed (${res.status})${details ? `: ${details}` : ""}`);
        return;
      }
      let payload = {};
      try {
        payload = await res.json();
      } catch (_) {
        payload = {};
      }
      if (Object.prototype.hasOwnProperty.call(payload, "value")) {
        setPluginControlValue(plugin.name, control.name, payload.value);
      }
      setPluginResponse(plugin.name, "ok", payload.message || "Plugin action completed");
    };

    const managePlugin = async (pluginName, action) => {
      const routes = {
        load: { url: `/v1/plugins/${encodeURIComponent(pluginName)}/_load`, method: "POST" },
        reload: { url: `/v1/plugins/${encodeURIComponent(pluginName)}/_reload`, method: "POST" },
        unload: { url: `/v1/plugins/${encodeURIComponent(pluginName)}`, method: "DELETE" },
        health: { url: `/v1/plugins/${encodeURIComponent(pluginName)}/health`, method: "POST" },
      };
      const target = routes[action];
      if (!target) return;
      pluginsStatus.value = "";
      const res = await apiFetch(target.url, { method: target.method });
      if (!res.ok) {
        pluginsStatus.value = `Failed to ${action} plugin ${pluginName} (${res.status})`;
        return;
      }
      const payload = await res.json();
      pluginsStatus.value = payload.message || `Plugin ${action} completed`;
      await loadPlugins();
      if (isPluginDiagnosticsOpen(pluginName)) {
        await loadPluginDiagnostics(pluginName, true);
      }
      if (pluginModalOpen.value && pluginModalPluginName.value === pluginName && ["unload", "reload"].includes(action)) {
        await closePluginModal(false);
      }
    };

    const rescanPlugins = async () => {
      pluginsStatus.value = "";
      const res = await apiFetch("/v1/plugins/_rescan", { method: "POST" });
      if (!res.ok) {
        pluginsStatus.value = `Failed to rescan plugins (${res.status})`;
        return;
      }
      const payload = await res.json();
      pluginsStatus.value = payload.message || "Plugin rescan completed";
      await loadPlugins();
      if (isAdmin.value) {
        const openNames = Object.entries(pluginDiagnosticsOpen.value)
          .filter(([, isOpen]) => !!isOpen)
          .map(([name]) => name);
        await Promise.all(openNames.map((name) => loadPluginDiagnostics(name, true)));
      }
    };

    const initializeAuthenticatedApp = async () => {
      setDefaultActiveTab();
      await fetchPrompts();
      await loadLlmProviders();
      await loadOptimizeConfig();
      await loadPlugins();
      await loadRoles();
      await loadProjects();
      await loadUsers();
      await loadGlobalConfig();
    };

    const loadCurrentUser = async () => {
      if (!authToken.value) {
        return false;
      }
      const res = await apiFetch("/v1/auth/me");
      if (!res.ok) {
        clearSession("");
        return false;
      }
      currentUser.value = await res.json();
      return true;
    };

    const submitAuth = async () => {
      authBusy.value = true;
      authError.value = "";
      authStatus.value = "";
      const endpoint = authMode.value === "bootstrap" ? "/v1/auth/bootstrap-admin" : "/v1/auth/login";
      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: authForm.value.username.trim(),
            password: authForm.value.password,
          }),
        });
        if (!res.ok) {
          if (res.status === 409 && authMode.value === "bootstrap") {
            authBootstrapRequired.value = false;
            authMode.value = "login";
            authError.value = "Bootstrap is no longer available. Sign in with an existing account.";
            return;
          }
          const detail = await res.text();
          authError.value = detail || `Authentication failed (${res.status})`;
          return;
        }
        const payload = await res.json();
        consumeAuthPayload(payload);
        authForm.value.password = "";
        authStatus.value = authMode.value === "bootstrap" ? "Admin account created." : "Signed in.";
        await initializeAuthenticatedApp();
      } catch (err) {
        authError.value = "Authentication request failed.";
      } finally {
        authBusy.value = false;
      }
    };

    const logout = () => {
      clearSession("");
      authStatus.value = "Signed out.";
      fetchAuthStatus();
    };

    const beginEditUser = (user) => {
      if (!canWrite.value) return;
      editingUserId.value = user.id;
      editUserForm.value = {
        username: user.username || "",
        password: "",
        role: user.role || "developer",
        projects: [...(user.projects || [])],
        is_active: !!user.is_active,
      };
      usersStatus.value = "";
    };

    const resolveFormState = (formRef) => formRef?.value ?? formRef ?? {};

    const toggleProjectSelection = (formRef, projectName) => {
      if (!canWrite.value) return;
      const formState = resolveFormState(formRef);
      const current = new Set(normalizeProjects(formState.projects));
      if (current.has(projectName)) {
        current.delete(projectName);
      } else {
        current.add(projectName);
      }
      formState.projects = [...current].sort((left, right) => left.localeCompare(right));
    };

    const isProjectSelected = (formRef, projectName) => {
      const formState = resolveFormState(formRef);
      return normalizeProjects(formState.projects).includes(projectName);
    };

    const cancelUserEdit = () => {
      editingUserId.value = null;
      editUserForm.value = emptyUserForm();
    };

    const createProjectRecord = async () => {
      if (!canWrite.value) return;
      projectsStatus.value = "";
      const res = await apiFetch("/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newProjectForm.value.name.trim() }),
      });
      if (!res.ok) {
        projectsStatus.value = `Failed to create project (${res.status})`;
        return;
      }
      newProjectForm.value = emptyProjectForm();
      projectsStatus.value = "Project created";
      await loadProjects();
    };

    const beginEditProject = (project) => {
      if (!canWrite.value) return;
      editingProjectId.value = project.id;
      editProjectForm.value = { name: project.name || "" };
      projectsStatus.value = "";
    };

    const cancelProjectEdit = () => {
      editingProjectId.value = null;
      editProjectForm.value = emptyProjectForm();
    };

    const saveProjectEdit = async (projectId) => {
      if (!canWrite.value) return;
      projectsStatus.value = "";
      const res = await apiFetch(`/v1/projects/${projectId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editProjectForm.value.name.trim() }),
      });
      if (!res.ok) {
        projectsStatus.value = `Failed to update project (${res.status})`;
        return;
      }
      projectsStatus.value = "Project updated";
      cancelProjectEdit();
      await loadProjects();
      await loadUsers();
      await fetchPrompts();
    };

    const deleteProjectRecord = async (project) => {
      if (!canWrite.value) return;
      projectsStatus.value = "";
      const message = `CAUTION: You are about to delete project "${project.name}" and ALL related prompts with ALL their versions.\n\nThis action cannot be undone.\n\nAre you sure?`;
      if (!window.confirm(message)) return;
      const res = await apiFetch(`/v1/projects/${project.id}`, { method: "DELETE" });
      if (!res.ok) {
        projectsStatus.value = `Failed to delete project (${res.status})`;
        return;
      }
      projectsStatus.value = "Project deleted";
      await loadProjects();
      await loadUsers();
      await fetchPrompts(1);
    };

    const createUserAccount = async () => {
      if (!canWrite.value) return;
      usersStatus.value = "";
      const payload = {
        username: newUserForm.value.username.trim(),
        password: newUserForm.value.password,
        role: newUserForm.value.role,
        projects: normalizeProjects(newUserForm.value.projects),
        is_active: !!newUserForm.value.is_active,
      };
      const res = await apiFetch("/v1/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        usersStatus.value = `Failed to create user (${res.status})`;
        return;
      }
      newUserForm.value = emptyUserForm();
      usersStatus.value = "User created";
      await loadUsers();
    };

    const saveUserEdit = async (userId) => {
      if (!canWrite.value) return;
      usersStatus.value = "";
      const payload = {
        username: editUserForm.value.username.trim(),
        role: editUserForm.value.role,
        projects: normalizeProjects(editUserForm.value.projects),
        is_active: !!editUserForm.value.is_active,
      };
      if (editUserForm.value.password) {
        payload.password = editUserForm.value.password;
      }
      const res = await apiFetch(`/v1/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        usersStatus.value = `Failed to update user (${res.status})`;
        return;
      }
      usersStatus.value = "User updated";
      cancelUserEdit();
      await loadUsers();
      if (currentUser.value?.id === userId) {
        await loadCurrentUser();
      }
    };

    const deleteUserAccount = async (user) => {
      if (!canWrite.value) return;
      usersStatus.value = "";
      if (!window.confirm(`Delete user ${user.username}?`)) return;
      const res = await apiFetch(`/v1/users/${user.id}`, { method: "DELETE" });
      if (!res.ok) {
        usersStatus.value = `Failed to delete user (${res.status})`;
        return;
      }
      usersStatus.value = "User deleted";
      await loadUsers();
    };

    const pushOptimizerLog = (message, level = "info", ts = null) => {
      optimizerLogs.value.push({
        ts: ts ? formatUtcDateTime(ts) : nowTime(),
        level,
        message,
      });
    };

    const clearOptimizationPoll = () => {
      if (optimizerPollTimerId !== null) {
        window.clearTimeout(optimizerPollTimerId);
        optimizerPollTimerId = null;
      }
    };

    const applyOptimizationResponse = (data, ts = null) => {
      optimizerEngine.value = data.engine || "optimizer";
      optimizerNotes.value = data.notes || [];
      optimizerElapsedSeconds.value = Number.isFinite(Number(data.elapsed_seconds)) ? Number(data.elapsed_seconds) : null;
      optimizerStatus.value = optimizerEngine.value.includes("fallback")
        ? "Optimization finished with fallback"
        : "Optimization completed";

      pushOptimizerLog(`Completed. Engine: ${optimizerEngine.value}.`, optimizerEngine.value.includes("fallback") ? "warn" : "success", ts);
      if (optimizerElapsedSeconds.value !== null) {
        pushOptimizerLog(`Backend elapsed: ${optimizerElapsedSeconds.value.toFixed(2)}s.`, "info", ts);
      }
      if (Array.isArray(optimizerNotes.value) && optimizerNotes.value.length) {
        optimizerNotes.value.forEach((note) => {
          const level = String(note || "").toLowerCase().includes("failed") ? "warn" : "info";
          pushOptimizerLog(String(note), level, ts);
        });
      }

      optimizedMarkdown.value = data.optimized_markdown || "";
      optimizedDraft.value = {
        role: data.optimized?.role || "",
        task: data.optimized?.task || "",
        context: data.optimized?.context || "",
        constraints: data.optimized?.constraints || "",
        output_format: data.optimized?.output_format || "",
        examples: data.optimized?.examples || "",
      };
    };

    const finalizeOptimizationJob = (job) => {
      clearOptimizationPoll();
      activeOptimizationJobId.value = "";
      optimizerLoading.value = false;
      const finalTs = job.cancelled_at || job.completed_at || null;
      const actualStartedTs = job.started_at || job.created_at || null;
      const runningEntry = optimizerLogs.value.find((entry) => entry.message === "Optimization is running on backend ...");
      if (runningEntry && actualStartedTs) {
        runningEntry.ts = formatUtcDateTime(actualStartedTs);
      }

      if (job.status === "completed" && job.result) {
        applyOptimizationResponse(job.result, finalTs);
        return;
      }

      if (job.status === "cancelled") {
        optimizerStatus.value = "Optimization cancelled";
        optimizerError.value = "";
        pushOptimizerLog(job.error || "Optimization cancelled.", "warn", finalTs);
        return;
      }

      optimizerStatus.value = "Optimization failed";
      optimizerError.value = job.error || "Optimization failed before completion.";
      pushOptimizerLog(job.error || "Optimization failed before completion.", "error", finalTs);
    };

    const pollOptimizationJob = async (jobId) => {
      if (!jobId || activeOptimizationJobId.value !== jobId) {
        return;
      }

      let res;
      try {
        res = await apiFetch(`/v1/optimize/jobs/${encodeURIComponent(jobId)}`);
      } catch (err) {
        clearOptimizationPoll();
        activeOptimizationJobId.value = "";
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = "Unable to query optimization status.";
        pushOptimizerLog("Unable to query optimization status.", "error");
        return;
      }

      if (!res.ok) {
        let details = "";
        try {
          details = await res.text();
        } catch (err) {
          details = "";
        }
        clearOptimizationPoll();
        activeOptimizationJobId.value = "";
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = `Unable to query optimization status (${res.status}).`;
        pushOptimizerLog(
          `Optimization status query failed with HTTP ${res.status}${details ? `: ${details.slice(0, 220)}` : ""}`,
          "error"
        );
        return;
      }

      const job = await res.json();
      if (job.status === "running") {
        optimizerPollTimerId = window.setTimeout(() => {
          pollOptimizationJob(jobId);
        }, 1000);
        return;
      }

      finalizeOptimizationJob(job);
    };

    const cancelActiveOptimization = async (closeAfterCancel = false) => {
      const jobId = activeOptimizationJobId.value;
      clearOptimizationPoll();

      if (!jobId) {
        optimizerLoading.value = false;
        if (closeAfterCancel) {
          optimizerModalOpen.value = false;
        }
        return true;
      }

      let res;
      try {
        res = await apiFetch(`/v1/optimize/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
      } catch (err) {
        optimizerError.value = "Unable to cancel optimization.";
        pushOptimizerLog("Unable to cancel optimization.", "error");
        return false;
      }

      if (!res.ok) {
        let details = "";
        try {
          details = await res.text();
        } catch (err) {
          details = "";
        }
        optimizerError.value = `Unable to cancel optimization (${res.status}).`;
        pushOptimizerLog(
          `Optimization cancel failed with HTTP ${res.status}${details ? `: ${details.slice(0, 220)}` : ""}`,
          "error"
        );
        return false;
      }

      const job = await res.json();
      finalizeOptimizationJob(job);
      if (closeAfterCancel) {
        optimizerModalOpen.value = false;
      }
      return true;
    };

    const closeOptimizerModal = async () => {
      if (optimizerLoading.value && activeOptimizationJobId.value) {
        const cancelled = await cancelActiveOptimization(true);
        if (!cancelled) {
          return;
        }
        return;
      }
      optimizerModalOpen.value = false;
    };

    const normalizePageNumber = (page) => {
      const parsed = Number(page);
      return Number.isFinite(parsed) && parsed >= 1 ? Math.floor(parsed) : 1;
    };

    const fetchPrompts = async (page = browsePage.value) => {
      if (!currentUser.value) {
        items.value = [];
        browseTotalItems.value = 0;
        return;
      }
      browsePage.value = normalizePageNumber(page);
      const p = new URLSearchParams();
      if (filterProject.value.trim()) p.set("project", filterProject.value.trim());
      if (filterTag.value.trim())     p.set("tag",     filterTag.value.trim());
      p.set("sort_by", browseSortBy.value);
      p.set("sort_order", browseSortOrder.value);
      p.set("limit", String(browsePageSize.value));
      p.set("offset", String((browsePage.value - 1) * browsePageSize.value));
      const q   = p.toString();
      const res = await apiFetch("/v1/prompts" + (q ? "?" + q : ""));
      if (!res.ok) {
        console.error("fetchPrompts failed:", res.status, res.statusText);
        items.value = [];
        browseTotalItems.value = 0;
        return;
      }
      items.value = await res.json();
      browseTotalItems.value = Number(res.headers.get("X-Total-Count") || items.value.length || 0);
    };

    const totalBrowsePages = computed(() => {
      const total = Math.ceil(browseTotalItems.value / browsePageSize.value);
      return Math.max(1, total);
    });

    const paginatedItems = computed(() => items.value);

    const setBrowsePage = async (page) => {
      const nextPage = Math.min(normalizePageNumber(page), totalBrowsePages.value);
      await fetchPrompts(nextPage);
    };

    const browseSummaryLabel = computed(() => {
      return `Total ${browseTotalItems.value || 0}`;
    });

    const loadVersions = async (p) => {
      const res = await apiFetch("/v1/prompts/" + p.project + "/" + p.name + "/versions");
      expandedVersions.value = res.ok ? await res.json() : [];
    };

    const togglePrompt = async (p) => {
      const k = key(p);
      if (expandedKey.value === k) {
        expandedKey.value = null; expandedVersions.value = [];
        openVersionKey.value = null; editTagsMode.value = false;
        newVersionEditorOpen.value = false;
        newVersionRole.value = ""; newVersionTask.value = ""; newVersionContext.value = "";
        newVersionConstraints.value = ""; newVersionOutputFormat.value = ""; newVersionExamples.value = "";
        saveStatus.value = "";
        deleteStatus.value = "";
        return;
      }
      expandedKey.value       = k;
      editTagsMode.value      = false;
      newVersionEditorOpen.value = false;
      editTagsStr.value       = tagsToStr(p.tags);
      newVersionRole.value    = p.role || "";
      newVersionTask.value    = p.task || "";
      newVersionContext.value = p.context || "";
      newVersionConstraints.value = p.constraints || "";
      newVersionOutputFormat.value = p.output_format || "";
      newVersionExamples.value = p.examples || "";
      saveStatus.value        = "";
      deleteStatus.value      = "";
      openVersionKey.value    = null;
      await loadVersions(p);
    };

    const deletePrompt = async (p) => {
      if (!canWrite.value) return;
      deleteStatus.value = "";
      const confirmed = window.confirm(`Delete prompt ${p.project} / ${p.name}? This cannot be undone.`);
      if (!confirmed) return;

      const res = await apiFetch("/v1/prompts/" + p.project + "/" + p.name, {
        method: "DELETE",
      });

      if (!res.ok) {
        deleteStatus.value = "Delete failed (" + res.status + ")";
        return;
      }

      deleteStatus.value = "Prompt deleted";
      expandedKey.value = null;
      expandedVersions.value = [];
      openVersionKey.value = null;
      editTagsMode.value = false;
      await fetchPrompts();
    };

    const saveNewVersion = async (p) => {
      if (!canWrite.value) return;
      saveStatus.value = "";
      const res = await apiFetch("/v1/prompts/" + p.project + "/" + p.name, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: newVersionRole.value || null,
          task: newVersionTask.value,
          context: newVersionContext.value || null,
          constraints: newVersionConstraints.value || null,
          output_format: newVersionOutputFormat.value || null,
          examples: newVersionExamples.value || null,
        }),
      });
      if (!res.ok) { saveStatus.value = "Save failed (" + res.status + ")"; return; }
      saveStatus.value = "Version saved";
      await fetchPrompts();
      await loadVersions(p);
      const updated = items.value.find((i) => key(i) === expandedKey.value);
      if (updated) {
        newVersionRole.value    = updated.role || "";
        newVersionTask.value    = updated.task || "";
        newVersionContext.value = updated.context || "";
        newVersionConstraints.value = updated.constraints || "";
        newVersionOutputFormat.value = updated.output_format || "";
        newVersionExamples.value = updated.examples || "";
      }
    };

    const saveTags = async (p) => {
      if (!canWrite.value) return;
      saveStatus.value = "";
      const res = await apiFetch("/v1/prompts/" + p.project + "/" + p.name + "/tags", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: parseTags(editTagsStr.value) }),
      });
      if (!res.ok) { saveStatus.value = "Tag save failed (" + res.status + ")"; return; }
      saveStatus.value = "Tags updated";
      editTagsMode.value = false;
      await fetchPrompts();
    };

    const createPrompt = async () => {
      if (!canWrite.value) return;
      createStatus.value = "";
      const name = form.value.name.trim();
      const project = form.value.project.trim();
      if (!name || !project) {
        createStatus.value = "Name and Project are required";
        return;
      }

      const payload = {
        name,
        project,
        tags:    parseTags(form.value.tags),
        role:    form.value.role || null,
        task:    form.value.task,
        context: form.value.context || null,
        constraints: form.value.constraints || null,
        output_format: form.value.output_format || null,
        examples: form.value.examples || null,
      };
      const res = await apiFetch("/v1/prompts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) { createStatus.value = "Create failed (" + res.status + ")"; return; }
      form.value = { name: "", project: "", tags: "", role: "", task: "", context: "", constraints: "", output_format: "", examples: "" };
      createStatus.value = "Prompt created";
      await fetchPrompts();
      activeTab.value = "browse";
    };

    const promptPayload = (fields) => ({
      role: fields.role || null,
      task: fields.task || "",
      context: fields.context || null,
      constraints: fields.constraints || null,
      output_format: fields.output_format || null,
      examples: fields.examples || null,
    });

    const getDefaultProviderModels = (provider) => {
      const key = String(provider || "").toLowerCase();
      if (getProviderConfig(key).requiresApiToken) {
        return [];
      }
      return [...(defaultLlmModelsByProvider.value[key] || [])];
    };

    const getProviderConfig = (provider) => {
      const key = String(provider || "").toLowerCase();
      return llmProviderConfigs.value[key] || llmProviderConfigs.value.ollama || initialLlmProviderConfigs.ollama;
    };

    const getProviderLabel = (provider) => {
      return getProviderConfig(provider).label || provider;
    };

    const getProviderDefaultBaseUrl = (provider) => {
      return getProviderConfig(provider).baseUrl || "http://127.0.0.1:11434";
    };

    const getProviderDefaultModel = (provider) => {
      return getDefaultProviderModels(provider)[0] || "";
    };

    const updateProviderBaseUrl = (provider = optimizeConfig.value.llm_provider) => {
      optimizeConfig.value.llm_base_url = getProviderDefaultBaseUrl(provider);
      optimizeConfig.value.llm_model = getProviderDefaultModel(provider);
    };

    const modelRequiresToken = (provider = optimizeConfig.value.llm_provider) => {
      return !!getProviderConfig(provider).requiresApiToken;
    };

    const loadLlmProviders = async () => {
      try {
        const res = await apiFetch("/v1/llm/providers");
        if (!res.ok) {
          return;
        }
        const providers = await res.json();
        if (!Array.isArray(providers) || !providers.length) {
          return;
        }

        const nextConfigs = {};
        providers.forEach((provider) => {
          const key = String(provider?.key || "").toLowerCase().trim();
          if (!key) return;
          const models = Array.isArray(provider?.models)
            ? provider.models.filter((m) => typeof m === "string" && m.trim())
            : [];
          nextConfigs[key] = {
            label: String(provider?.label || key),
            baseUrl: String(provider?.base_url || ""),
            requiresApiToken: Boolean(provider?.requires_api_token),
            models,
          };
        });

        if (Object.keys(nextConfigs).length) {
          llmProviderConfigs.value = nextConfigs;
        }
      } catch (_) {
      }
    };

    const isEmbeddingLikeModel = (modelName) => {
      const normalized = String(modelName || "").toLowerCase();
      return normalized.includes("embed") || normalized.includes("embedding") || normalized.includes("snowflake-arctic");
    };

    const loadAvailableLlmModels = async (provider = optimizeConfig.value.llm_provider, preserveCurrentModel = true) => {
      llmModelsLoading.value = true;
      llmModelsLoadError.value = "";

      const selectedProvider = String(provider || "ollama").toLowerCase();
      const fallbackModels = getDefaultProviderModels(selectedProvider);
      const requiresToken = modelRequiresToken(selectedProvider);
      const token = String(optimizeConfig.value.llm_api_token || "").trim();

      if (requiresToken && !token) {
        availableLlmModels.value = [];
        llmModelsLoadError.value = `${getProviderLabel(selectedProvider)} requires API token. Unable to request available models without token.`;
        llmModelsLoading.value = false;
        return;
      }

      try {
        const params = new URLSearchParams();
        if ((optimizeConfig.value.llm_base_url || "").trim()) {
          params.set("base_url", optimizeConfig.value.llm_base_url.trim());
        }
        if (token) {
          params.set("api_token", token);
        }
        params.set("timeout_seconds", "10");

        const res = await apiFetch(`/v1/llm/providers/${encodeURIComponent(selectedProvider)}/models?${params.toString()}`);
        if (!res.ok) {
          llmModelsLoadError.value = `Failed to load provider models (HTTP ${res.status}).`;
          availableLlmModels.value = requiresToken ? [] : fallbackModels;
        } else {
          const discovered = await res.json();
          const clean = Array.isArray(discovered)
            ? discovered.filter((m) => typeof m === "string" && m.trim())
            : [];
          if (clean.length > 0) {
            availableLlmModels.value = clean;
            console.log(`[Models] Loaded ${clean.length} models from ${selectedProvider}:`, clean);
          } else {
            llmModelsLoadError.value = `No models discovered for ${selectedProvider}.`;
            availableLlmModels.value = requiresToken ? [] : fallbackModels;
          }
        }
      } catch (err) {
        llmModelsLoadError.value = `Unable to connect to ${selectedProvider}: ${err.message}`;
        console.error(`[Models] Error fetching ${selectedProvider} models:`, err);
        availableLlmModels.value = requiresToken ? [] : fallbackModels;
      } finally {
        const currentModel = (optimizeConfig.value.llm_model || "").trim();
        const canPreserveCurrentModel =
          preserveCurrentModel &&
          currentModel &&
          !availableLlmModels.value.includes(currentModel) &&
          !(selectedProvider === "ollama" && isEmbeddingLikeModel(currentModel));
        if (canPreserveCurrentModel) {
          availableLlmModels.value = [currentModel, ...availableLlmModels.value];
        }
        if (!currentModel || !availableLlmModels.value.includes(currentModel)) {
          if (availableLlmModels.value.length) {
            optimizeConfig.value.llm_model = availableLlmModels.value[0];
          }
        }
        llmModelsLoading.value = false;
      }
    };

    const loadOptimizeConfig = async () => {
      if (!currentUser.value) {
        optimizeConfig.value = defaultOptimizeConfig();
        return;
      }
      const res = await apiFetch("/v1/llm/config");
      if (!res.ok) {
        optimizeConfigStatus.value = "Failed to load optimize config (" + res.status + ")";
        return;
      }
      const cfg = await res.json();
      optimizeConfig.value = {
        ...defaultOptimizeConfig(),
        ...cfg,
        model_id: cfg.runtime_model_id || "",
        rounds: cfg.runtime_rounds || cfg.effective_rounds || 2,
        gp_profile: cfg.runtime_gp_profile || cfg.effective_gp_profile || "fast",
        llm_provider: cfg.runtime_llm_provider || cfg.effective_llm_provider || "ollama",
        llm_model: cfg.runtime_llm_model || cfg.effective_llm_model || "qwen2.5:0.5b",
        llm_base_url: cfg.runtime_llm_base_url || cfg.effective_llm_base_url || getProviderDefaultBaseUrl(cfg.runtime_llm_provider || cfg.effective_llm_provider),
        llm_timeout_seconds: cfg.runtime_llm_timeout_seconds || cfg.effective_llm_timeout_seconds || 300,
        llm_api_token: "",  // Never populate token from response for security
        effective_has_llm_api_token: cfg.effective_has_llm_api_token || false,
      };
      await loadAvailableLlmModels(optimizeConfig.value.llm_provider);
    };

    const persistOptimizeConfig = async (showSuccessMessage = true) => {
      if (!canWrite.value) {
        return false;
      }
      optimizeConfigStatus.value = "";
      const payload = {
        llm_provider: optimizeConfig.value.llm_provider || "ollama",
        llm_model: optimizeConfig.value.llm_model || "qwen2.5:0.5b",
        llm_base_url: optimizeConfig.value.llm_base_url || "http://127.0.0.1:11434",
        llm_timeout_seconds: Number(optimizeConfig.value.llm_timeout_seconds) || 300,
        llm_api_token: optimizeConfig.value.llm_api_token || null,
      };
      const res = await apiFetch("/v1/llm/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        optimizeConfigStatus.value = "Failed to save optimize config (" + res.status + ")";
        return false;
      }
      if (showSuccessMessage) {
        optimizeConfigStatus.value = "Optimize config saved";
      }
      await loadOptimizeConfig();
      return true;
    };

    const saveOptimizeConfig = async () => {
      await persistOptimizeConfig(true);
    };

    const optimizePrompt = async (endpoint, fields, source, target = null) => {
      if (!canWrite.value) {
        optimizerError.value = "Viewer role is read-only.";
        return;
      }
      clearOptimizationPoll();
      activeOptimizationJobId.value = "";
      optimizerLoading.value = true;
      optimizerError.value = "";
      optimizerStatus.value = "Optimization started";
      optimizerEngine.value = "";
      optimizerNotes.value = [];
      optimizerElapsedSeconds.value = null;
      optimizerLogs.value = [];
      optimizedMarkdown.value = "";
      optimizeEndpoint.value = endpoint;
      optimizeInputSource.value = source;
      optimizeTargetPrompt.value = target;
      optimizerMode.value = "optimizer";
      optimizerModalOpen.value = true;

      pushOptimizerLog(`Started optimization from ${source}.`);
      pushOptimizerLog("Saving active optimization config before request ...");

      const saved = await persistOptimizeConfig(false);
      if (!saved) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = "Unable to save optimization config before optimization.";
        pushOptimizerLog("Failed to save optimization config before optimization.", "error");
        return;
      }

      pushOptimizerLog("Optimization config saved and applied.", "success");
      pushOptimizerLog(
        `Using provider=${optimizeConfig.value.effective_llm_provider || optimizeConfig.value.llm_provider}, model=${optimizeConfig.value.effective_llm_model || optimizeConfig.value.llm_model}, timeout=${optimizeConfig.value.effective_llm_timeout_seconds || optimizeConfig.value.llm_timeout_seconds}s.`
      );
      pushOptimizerLog(`Creating optimization job via /v1/optimize/jobs for target ${endpoint} ...`);

      let res;
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 20000);
      try {
        res = await apiFetch("/v1/optimize/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(promptPayload(fields)),
          signal: controller.signal,
        });
      } catch (err) {
        window.clearTimeout(timeoutId);
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        if (err && err.name === "AbortError") {
          optimizerError.value = "Optimization job creation timed out.";
          pushOptimizerLog("Optimization job creation timed out.", "error");
        } else {
          optimizerError.value = "Optimization request failed before response.";
          pushOptimizerLog("Request failed: network/server error.", "error");
        }
        return;
      }
      window.clearTimeout(timeoutId);

      if (!res.ok) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        let details = "";
        try {
          details = await res.text();
        } catch (err) {
          details = "";
        }
        optimizerError.value = "Optimization failed (" + res.status + ")";
        pushOptimizerLog(
          `Optimization failed with HTTP ${res.status}${details ? `: ${details.slice(0, 220)}` : ""}`,
          "error"
        );
        return;
      }

      pushOptimizerLog(`Job creation response received (HTTP ${res.status}). Parsing payload ...`);

      let job;
      try {
        job = await res.json();
      } catch (err) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = "Optimization job response is not valid JSON.";
        pushOptimizerLog("Response parse failed: invalid optimization job payload.", "error");
        return;
      }

      activeOptimizationJobId.value = String(job.job_id || "");
      if (!activeOptimizationJobId.value) {
        optimizerLoading.value = false;
        optimizerStatus.value = "Optimization failed";
        optimizerError.value = "Optimization job id is missing in backend response.";
        pushOptimizerLog("Optimization job id is missing in backend response.", "error");
        return;
      }

      pushOptimizerLog(`Optimization job created: ${activeOptimizationJobId.value}.`, "success", job.created_at || null);
      pushOptimizerLog("Optimization is running on backend ...", "info", job.started_at || job.created_at || null);
      optimizerStatus.value = "Optimization is running";
      optimizerPollTimerId = window.setTimeout(() => {
        pollOptimizationJob(activeOptimizationJobId.value);
      }, 600);
    };

    const reoptimizePrompt = async () => {
      optimizerError.value = "";
      pushOptimizerLog("Reoptimize clicked. Saving config before restart ...");
      const saved = await persistOptimizeConfig(false);
      if (!saved) {
        optimizerStatus.value = "Reoptimize failed";
        optimizerError.value = "Reoptimize failed: unable to save optimization config.";
        pushOptimizerLog("Failed to save optimization config before reoptimize.", "error");
        return;
      }

      pushOptimizerLog("Config saved. Restarting optimization ...");

      await optimizePrompt(
        optimizeEndpoint.value,
        optimizedDraft.value,
        optimizeInputSource.value,
        optimizeTargetPrompt.value
      );
    };

    const optimizeFromCreate = async () => {
      createOptimizeMenuOpen.value = false;
      await optimizePrompt("/v1/optimize", form.value, "create", null);
    };

    const optimizeFromBrowse = async (p) => {
      browseOptimizeMenuKey.value = null;
      await optimizePrompt(
        "/v1/optimize",
        {
          role: p.role || "",
          task: p.task || "",
          context: p.context || "",
          constraints: p.constraints || "",
          output_format: p.output_format || "",
          examples: p.examples || "",
        },
        "browse",
        { project: p.project, name: p.name }
      );
    };

    const applyOptimizedPrompt = async () => {
      if (!canWrite.value) {
        optimizerError.value = "Viewer role is read-only.";
        return;
      }
      if (optimizeInputSource.value === "create") {
        form.value.role = optimizedDraft.value.role || "";
        form.value.task = optimizedDraft.value.task || "";
        form.value.context = optimizedDraft.value.context || "";
        form.value.constraints = optimizedDraft.value.constraints || "";
        form.value.output_format = optimizedDraft.value.output_format || "";
        form.value.examples = optimizedDraft.value.examples || "";
        optimizerModalOpen.value = false;
        return;
      }

      const target = optimizeTargetPrompt.value;
      if (!target) {
        optimizerError.value = "No prompt selected for update.";
        return;
      }

      const res = await apiFetch("/v1/prompts/" + target.project + "/" + target.name, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(promptPayload(optimizedDraft.value)),
      });

      if (!res.ok) {
        optimizerError.value = "Update failed (" + res.status + ")";
        return;
      }

      await fetchPrompts();
      const updated = items.value.find((i) => key(i) === expandedKey.value);
      if (updated) {
        await loadVersions(updated);
      }
      optimizerModalOpen.value = false;
      saveStatus.value = "Version saved";
    };

    const changeOwnPassword = async () => {
      changePasswordStatus.value = "";
      const form = changePasswordForm.value;
      if (!form.current_password || !form.new_password) {
        changePasswordStatus.value = "error:All fields are required.";
        return;
      }
      if (form.new_password !== form.confirm_password) {
        changePasswordStatus.value = "error:New passwords do not match.";
        return;
      }
      changePasswordBusy.value = true;
      try {
        const res = await apiFetch("/v1/auth/me/password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current_password: form.current_password,
            new_password: form.new_password,
          }),
        });
        if (!res.ok) {
          let detail = "";
          try { detail = (await res.json()).detail || ""; } catch (_) {}
          changePasswordStatus.value = `error:${detail || `Failed to change password (${res.status})`}`;
          return;
        }
        changePasswordForm.value = { current_password: "", new_password: "", confirm_password: "" };
        changePasswordStatus.value = "ok:Password changed successfully.";
      } finally {
        changePasswordBusy.value = false;
      }
    };

    onMounted(async () => {
      countdownTimerId = window.setInterval(() => {
        clockNow.value = Date.now();
      }, 1000);
      fetch("/v1/version").then(r => r.ok ? r.json() : null).then(d => { if (d && d.version) appVersion.value = d.version; }).catch(() => {});
      await fetchAuthStatus();
      if (await loadCurrentUser()) {
        await initializeAuthenticatedApp();
      }
      authReady.value = true;
    });

    onBeforeUnmount(() => {
      clearProactiveRefresh();
      clearOptimizationPoll();
      if (countdownTimerId !== null) {
        window.clearInterval(countdownTimerId);
        countdownTimerId = null;
      }
    });

    return {
      appVersion,
      authReady, authToken, currentUser, authMode, authForm, authError, authStatus, authBusy, authBootstrapRequired, isAuthenticated, isAdmin, isViewer, canViewAdmin, canWrite, currentUserProjectsLabel,
      activeTab, form, createStatus,
      items, filterProject, filterTag, fetchPrompts, browsePage, browsePageSize, browseTotalItems, totalBrowsePages, paginatedItems, setBrowsePage, browseSummaryLabel,
      browseSortBy, browseSortOrder,
      expandedKey, expandedVersions, openVersionKey,
      editTagsMode, editTagsStr, newVersionRole, newVersionTask, newVersionContext, newVersionConstraints, newVersionOutputFormat, newVersionExamples, saveStatus,
      newVersionEditorOpen,
      createOptimizeMenuOpen, browseOptimizeMenuKey,
      optimizerModalOpen, optimizerLoading, optimizerError, optimizerStatus, optimizerMode, optimizerLogs, optimizerEngine, optimizerNotes, optimizerElapsedSeconds,
      optimizerElapsedPercent, optimizerElapsedSeverity,
      optimizedMarkdown, optimizedDraft,
      optimizeConfig, optimizeConfigStatus, llmProviderOptions, availableLlmModels, llmModelsLoading, llmModelsLoadError,
      globalConfigEntries, globalConfigLoading, globalConfigStatus,
      roleOptions, projects, projectsLoading, projectsStatus, newProjectForm, editingProjectId, editProjectForm,
      users, usersLoading, usersStatus, newUserForm, editingUserId, editUserForm, availableProjectNames,
      plugins, pluginsLoading, pluginsStatus, pluginResponses,
      pluginNameFilter, pluginTagFilters, pluginTagMatchMode, pluginFilterBarOpen, availablePluginTags, pluginTagFilterGroups, filteredPlugins,
      key, togglePrompt, saveNewVersion, saveTags, createPrompt,
      deletePrompt,
      optimizeFromCreate,
      optimizeFromBrowse,
      applyOptimizedPrompt, reoptimizePrompt, saveOptimizeConfig, loadAvailableLlmModels, updateProviderBaseUrl, getProviderLabel, modelRequiresToken, closeOptimizerModal,
      loadGlobalConfig, saveGlobalConfigEntry, resetGlobalConfigDraft,
      getGlobalConfigControlType, getGlobalConfigOptions, setGlobalConfigBooleanDraft,
      submitAuth, logout, createProjectRecord, beginEditProject, cancelProjectEdit, saveProjectEdit, deleteProjectRecord,
      createUserAccount, beginEditUser, cancelUserEdit, saveUserEdit, deleteUserAccount, loadUsers, loadProjects,
      loadPlugins, rescanPlugins, managePlugin, invokePluginControl,
      pluginHasImageIcon, pluginIconFallback, getPluginControlValue, canUsePluginControl,
      getPluginDiagnostics, isPluginDiagnosticsLoading, isPluginDiagnosticsOpen, togglePluginDiagnostics,
      getPluginBlockedCount, getPluginFailureCount,
      getPluginTags, togglePluginTagFilter, clearPluginFilters, togglePluginFilterBar, isPluginTagActive, setPluginTagMatchMode,
      isPluginRoutesOpen, togglePluginRoutes,
      getPluginModalLaunchers, pluginModalOpen, pluginModalLoading, pluginModalError, pluginModalStatus, pluginModalSession,
      pluginModalControls, getPluginModalControlValue, openPluginModal, invokePluginModalControl, stopPluginModal, closePluginModal, refreshPluginModal,
      toggleProjectSelection, isProjectSelected,
      visibleHeaderTags, hiddenHeaderTagCount,
      formatUtcDateTime, formatAuditLine, accessTokenCountdown, nextRefreshCountdown, nextRefreshAt, accessTokenExpiresAt,
      md, buildPromptMarkdown,
      deleteStatus,
      changePasswordForm, changePasswordStatus, changePasswordBusy, changeOwnPassword,
    };
  },

  template: `
    <div v-if="!authReady" class="auth-shell">
      <div class="auth-card">
        <h1 class="app-title"><img src="/P_240x240.png" alt="" class="app-title-icon" aria-hidden="true" />PromptMan</h1>
        <span v-if="appVersion" style="display:block;font-size:0.78rem;color:#9ca3af;margin:-6px 0 6px">v{{ appVersion }}</span>
        <p class="subtitle">Loading session...</p>
      </div>
    </div>

    <div v-else-if="!isAuthenticated" class="auth-shell">
      <div class="auth-card">
        <h1 class="app-title"><img src="/P_240x240.png" alt="" class="app-title-icon" aria-hidden="true" />PromptMan</h1>
        <span v-if="appVersion" style="display:block;font-size:0.78rem;color:#9ca3af;margin:-6px 0 6px">v{{ appVersion }}</span>
        <p class="subtitle">{{ authBootstrapRequired ? 'Create the first admin account for this workspace.' : 'Sign in to access prompts and personal optimization config.' }}</p>
        <p class="auth-helper">Access token lifetime is 30 minutes. The UI refreshes the session automatically while the refresh token is still valid.</p>
        <div class="field">
          <label>Username</label>
          <input v-model="authForm.username" placeholder="admin" />
        </div>
        <div class="field">
          <label>Password</label>
          <input type="password" v-model="authForm.password" placeholder="Enter password" @keyup.enter="submitAuth" />
        </div>
        <div class="btn-row auth-actions">
          <button @click="submitAuth" :disabled="authBusy || !authForm.username.trim() || !authForm.password">{{ authBusy ? 'Please wait...' : (authMode === 'bootstrap' ? 'Create Admin' : 'Sign In') }}</button>
          <button class="ghost" v-if="!authBootstrapRequired" @click="authMode='login'">Use login</button>
        </div>
        <p v-if="authStatus" class="status-ok">{{ authStatus }}</p>
        <p v-if="authError" class="status-err">{{ authError }}</p>
      </div>
    </div>

    <template v-else>
    <header style="margin-bottom:4px">
      <div class="header-topline">
        <div>
          <h1 class="app-title"><img src="/P_240x240.png" alt="" class="app-title-icon" aria-hidden="true" />PromptMan <span v-if="appVersion" style="font-size:0.55em;color:#9ca3af;font-weight:400;vertical-align:middle">v{{ appVersion }}</span></h1>
          <p class="subtitle">Versioned prompts with tags, markdown, and per-user optimization config.</p>
        </div>
        <div class="auth-banner">
          <div>
            <div class="auth-banner-user">{{ currentUser.username }}</div>
            <div class="auth-banner-meta">Role: {{ currentUser.role }} | Projects: {{ currentUserProjectsLabel }}</div>
          </div>
          <button class="ghost" @click="logout">Logout</button>
        </div>
      </div>
    </header>

    <div class="tabs">
      <button class="tab-btn" :class="{active: activeTab==='browse'}" @click="activeTab='browse'">Browse</button>
      <button v-if="canWrite" class="tab-btn" :class="{active: activeTab==='create'}" @click="activeTab='create'">+ Create</button>
      <button class="tab-btn" :class="{active: activeTab==='config'}" @click="activeTab='config'">Config</button>
      <button class="tab-btn" :class="{active: activeTab==='plugins'}" @click="activeTab='plugins'">Plugins</button>
      <button v-if="canViewAdmin" class="tab-btn" :class="{active: activeTab==='admin'}" @click="activeTab='admin'">Admin</button>
      <button class="tab-btn" :class="{active: activeTab==='account'}" @click="activeTab='account'">Account</button>
      <button class="tab-btn" :class="{active: activeTab==='about'}" @click="activeTab='about'">About</button>
    </div>

    <!-- BROWSE TAB -->
    <div class="tab-panel" v-if="activeTab==='browse'">
      <div class="filter-row">
        <div class="field">
          <label>Project</label>
          <select v-model="filterProject">
            <option value="">All projects</option>
            <option v-for="projectName in availableProjectNames" :key="projectName">{{ projectName }}</option>
          </select>
        </div>
        <div class="field">
          <label>Tag</label>
          <input v-model="filterTag" placeholder="production" />
        </div>
        <div style="padding-bottom:1px">
          <button class="secondary" @click="fetchPrompts">Refresh</button>
        </div>
      </div>

      <div class="browse-toolbar" v-if="browseTotalItems>0">
        <p class="browse-summary">{{ browseSummaryLabel }}</p>
        <div class="browse-pagination-controls">
          <label class="browse-page-size-label browse-sort-label">
            Sort by
            <select v-model="browseSortBy" @change="fetchPrompts(1)">
              <option value="updated_at">Last modified</option>
              <option value="created_at">Created time</option>
              <option value="name">Name</option>
              <option value="project">Project</option>
            </select>
          </label>
          <label class="browse-page-size-label browse-sort-label">
            Order
            <select v-model="browseSortOrder" @change="fetchPrompts(1)">
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
          <label class="browse-page-size-label">
            Per page
            <select v-model.number="browsePageSize" @change="fetchPrompts(1)">
              <option :value="5">5</option>
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
            </select>
          </label>
        </div>
      </div>

      <p v-if="browseTotalItems===0" style="color:var(--muted)">No prompts found.</p>

      <div class="prompt-list">
        <div class="prompt-card" v-for="p in paginatedItems" :key="key(p)">

          <div class="prompt-header" @click="togglePrompt(p)">
            <div class="prompt-header-main">
              <h3>{{ p.project }} / {{ p.name }}</h3>
            </div>
            <div class="chips prompt-header-chips">
              <span class="chip" v-for="t in visibleHeaderTags(p.tags)" :key="t">{{ t }}</span>
              <span class="chip chip-overflow" v-if="hiddenHeaderTagCount(p.tags) > 0">+{{ hiddenHeaderTagCount(p.tags) }}</span>
            </div>
            <div class="prompt-header-meta prompt-header-meta-inline">{{ formatAuditLine('Updated', p.updated_at, p.updated_by_username) }}</div>
            <span class="ver-badge">v{{ p.latest_version }}</span>
            <span class="expand-icon" :class="{open: expandedKey===key(p)}">&#9660;</span>
          </div>

          <div class="prompt-detail" v-if="expandedKey===key(p)">
            <div class="audit-block">
              <div class="audit-line">{{ formatAuditLine('Created', p.created_at, p.created_by_username) }}</div>
              <div class="audit-line">{{ formatAuditLine('Updated', p.updated_at, p.updated_by_username) }}</div>
            </div>

            <!-- Tags -->
            <div class="detail-section">
              <h4>Tags</h4>
              <div v-if="!editTagsMode || !canWrite">
                <div class="chips">
                  <span class="chip" v-for="t in p.tags" :key="t">{{ t }}</span>
                  <em v-if="p.tags.length===0" style="color:var(--muted);font-size:0.85rem">none</em>
                </div>
                <div class="btn-row" v-if="canWrite">
                  <button class="ghost" @click="editTagsMode=true; editTagsStr=p.tags.join(', ')">Edit tags</button>
                </div>
              </div>
              <div v-else>
                <div class="field">
                  <label>Tags (comma-separated)</label>
                  <input v-model="editTagsStr" placeholder="alpha, beta, prod" />
                </div>
                <div class="btn-row">
                  <button @click="saveTags(p)">Save tags</button>
                  <button class="ghost" @click="editTagsMode=false">Cancel</button>
                </div>
              </div>
            </div>

            <!-- Latest content rendered as markdown -->
            <div class="detail-section">
              <h4>Latest content &mdash; v{{ p.latest_version }}</h4>
              <div class="md-content" v-html="md(buildPromptMarkdown(p))"></div>
              <div class="btn-row" style="margin-top:12px" v-if="canWrite">
                <button class="secondary" @click.stop="optimizeFromBrowse(p)">Optimize Prompt</button>
                <button class="danger" @click.stop="deletePrompt(p)">Delete Prompt</button>
              </div>
              <p v-if="isViewer" style="margin-top:12px;color:var(--muted)">Viewer role can inspect prompts but cannot optimize, edit, or delete them.</p>
              <p v-if="deleteStatus" :class="deleteStatus.includes('failed') ? 'status-err' : 'status-ok'">{{ deleteStatus }}</p>
            </div>

            <!-- New version editor -->
            <div class="detail-section" v-if="canWrite">
              <div class="section-title-row">
                <h4 style="margin:0">Create new version</h4>
                <button class="ghost" @click="newVersionEditorOpen = !newVersionEditorOpen">
                  {{ newVersionEditorOpen ? 'Hide' : 'Show' }}
                </button>
              </div>
              <div class="new-version-editor" v-if="newVersionEditorOpen">
                <div class="new-version-group">
                  <p class="new-version-group-title">Prompt components</p>
                  <div class="field">
                    <label>Role (optional)</label>
                    <input v-model="newVersionRole" placeholder="You are a helpful assistant..." />
                  </div>
                  <div class="field">
                    <label>Task (required)</label>
                    <textarea v-model="newVersionTask" style="min-height:160px" placeholder="Generate a summary of..."></textarea>
                  </div>
                  <div class="field">
                    <label>Constraints (optional)</label>
                    <textarea v-model="newVersionConstraints" style="min-height:80px" placeholder="Limitations, rules, format restrictions..."></textarea>
                  </div>
                  <div class="field">
                    <label>Output Format (optional)</label>
                    <textarea v-model="newVersionOutputFormat" style="min-height:80px" placeholder="JSON, CSV, markdown, bullet points..."></textarea>
                  </div>
                  <div class="field">
                    <label>Examples (optional)</label>
                    <textarea v-model="newVersionExamples" style="min-height:80px" placeholder="Input/output examples..."></textarea>
                  </div>
                  <div class="field">
                    <label>Context (optional)</label>
                    <textarea v-model="newVersionContext" style="min-height:160px" placeholder="Background information, data format, target audience..."></textarea>
                  </div>
                </div>
                <div class="new-version-group">
                  <p class="new-version-group-title">Composed preview</p>
                  <div class="field">
                    <div class="md-editor-preview-label">Preview</div>
                    <div class="md-editor-preview" :class="{empty: !newVersionTask}" v-html="newVersionTask ? md(buildPromptMarkdown({role: newVersionRole, task: newVersionTask, constraints: newVersionConstraints, output_format: newVersionOutputFormat, examples: newVersionExamples, context: newVersionContext})) : 'Nothing to preview yet\u2026'"></div>
                  </div>
                </div>
              </div>
              <div class="btn-row">
                <button v-if="newVersionEditorOpen" @click="saveNewVersion(p)">Save as new version</button>
              </div>
              <p v-if="saveStatus" :class="saveStatus.includes('failed') ? 'status-err' : 'status-ok'">{{ saveStatus }}</p>
            </div>

            <!-- Version history -->
            <div class="detail-section">
              <h4>Version history ({{ expandedVersions.length }})</h4>
              <div class="version-list">
                <div class="version-item" v-for="v in expandedVersions.slice().reverse()" :key="v.version">
                  <div class="version-item-header" @click="openVersionKey = (openVersionKey===v.version ? null : v.version)">
                    <span>Version {{ v.version }}</span>
                    <span class="version-audit">{{ formatUtcDateTime(v.created_at) }}<template v-if="v.created_by_username"> by {{ v.created_by_username }}</template></span>
                    <span style="font-size:0.75rem;color:var(--muted)">{{ openVersionKey===v.version ? 'hide' : 'show' }}</span>
                  </div>
                  <div class="version-item-body" v-if="openVersionKey===v.version">
                    <div class="md-content" v-html="md(buildPromptMarkdown(v))"></div>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      <div class="browse-pagination" v-if="browseTotalItems > browsePageSize">
        <button class="ghost" :disabled="browsePage===1" @click="setBrowsePage(browsePage - 1)">Previous</button>
        <span class="browse-page-indicator">Page {{ browsePage }} of {{ totalBrowsePages }}</span>
        <button class="ghost" :disabled="browsePage===totalBrowsePages" @click="setBrowsePage(browsePage + 1)">Next</button>
      </div>
    </div>

    <!-- CREATE TAB -->
    <div class="tab-panel" v-if="activeTab==='create' && canWrite">
      <h2 style="margin-top:0">New Prompt</h2>
      <div v-if="!availableProjectNames.length" style="padding:12px;background:rgba(185,28,28,0.1);border:1px solid rgba(185,28,28,0.3);border-radius:10px;color:var(--err)">
        No projects available. Admin must create projects in the Admin tab first.
      </div>
      <template v-else>
        <div class="create-grid">
          <div class="field">
            <label>Name (required)</label>
            <input v-model="form.name" placeholder="checkout-system" required />
          </div>
          <div class="field">
            <label>Project (required)</label>
            <select class="select-pretty" v-model="form.project" required>
              <option value="">Select a project</option>
              <option v-for="projectName in availableProjectNames" :key="projectName" :value="projectName">{{ projectName }}</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label>Tags (comma-separated, optional)</label>
          <input v-model="form.tags" placeholder="system, production, v1" />
        </div>
        <fieldset class="group-box">
          <legend>Prompt Data</legend>
          <div class="field">
            <label>Role (optional)</label>
            <input v-model="form.role" placeholder="You are a helpful assistant..." />
          </div>
          <div class="field">
            <label>Task (required)</label>
            <textarea v-model="form.task" style="min-height:160px" placeholder="Generate a summary of..."></textarea>
          </div>
          <div class="field">
            <label>Constraints (optional)</label>
            <textarea v-model="form.constraints" style="min-height:80px" placeholder="Limitations, rules, format restrictions..."></textarea>
          </div>
          <div class="field">
            <label>Output format (optional)</label>
            <textarea v-model="form.output_format" style="min-height:80px" placeholder="JSON, CSV, markdown, bullet points..."></textarea>
          </div>
          <div class="field">
            <label>Examples (optional)</label>
            <textarea v-model="form.examples" style="min-height:80px" placeholder="Input/output examples..."></textarea>
          </div>
          <div class="field">
            <label>Context (optional)</label>
            <textarea v-model="form.context" style="min-height:160px" placeholder="Background information, data format, target audience..."></textarea>
          </div>
        </fieldset>
        <div class="field">
          <div class="md-editor-preview-label">Preview</div>
          <div class="md-editor-preview" :class="{empty: !form.task}" v-html="form.task ? md(buildPromptMarkdown(form)) : 'Nothing to preview yet\u2026'"></div>
        </div>
        <div class="btn-row">
          <button class="secondary" @click.stop="optimizeFromCreate">Optimize Prompt</button>
          <button @click="createPrompt" :disabled="!form.project">Save Prompt</button>
        </div>
        <p v-if="createStatus" :class="createStatus.includes('failed') ? 'status-err' : 'status-ok'">{{ createStatus }}</p>
      </template>
    </div>

    <!-- CONFIG TAB -->
    <div class="tab-panel" v-if="activeTab==='config'">
      <h2 style="margin-top:0">Optimization Config</h2>
      <p style="margin:0 0 12px;color:var(--muted)">Manage active settings for the configured optimizer backend. These settings are stored per user.</p>
      <p style="margin:0 0 12px;color:var(--muted)">Leo uses a 10-step prompt-engineering system prompt submitted to an LLM — a provider must be configured. Without a provider the service falls back to the built-in heuristic engine.</p>
      <p v-if="isViewer" style="margin:0 0 12px;color:var(--muted)">Viewer role is read-only. Configuration values are visible but cannot be changed.</p>

      <div class="opt-config-box opt-config-box-standalone">
        <div class="opt-settings-group">
          <h5>LLM Provider Settings (required for Leo optimization)</h5>
          <div class="opt-settings-toolbar">
            <button
              class="ghost opt-refresh-btn"
              @click="loadAvailableLlmModels(optimizeConfig.llm_provider)"
              :disabled="llmModelsLoading || !canWrite"
              title="Refresh available models for current API key"
            >
              {{ llmModelsLoading ? "Loading..." : "Refresh Models" }}
            </button>
          </div>
          <div class="create-grid">
            <div class="field">
              <label>Provider</label>
              <select class="select-pretty" v-model="optimizeConfig.llm_provider" :disabled="!canWrite" @change="updateProviderBaseUrl(optimizeConfig.llm_provider); loadAvailableLlmModels(optimizeConfig.llm_provider, false)">
                <option v-for="provider in llmProviderOptions" :key="provider" :value="provider">{{ getProviderLabel(provider) }}</option>
              </select>
            </div>
            <div class="field">
              <label>Model</label>
              <select class="select-pretty" v-model="optimizeConfig.llm_model" :disabled="llmModelsLoading || !canWrite">
                <option v-for="m in availableLlmModels" :key="m" :value="m">{{ m }}</option>
              </select>
            </div>
          </div>
          <div class="create-grid">
            <div class="field">
              <label>Base URL</label>
              <input v-model="optimizeConfig.llm_base_url" :disabled="!canWrite" @change="loadAvailableLlmModels(optimizeConfig.llm_provider)" placeholder="http://127.0.0.1:11434" />
            </div>
            <div class="field" v-if="modelRequiresToken()" style="max-width:220px">
              <label>API Token</label>
              <input type="password" v-model="optimizeConfig.llm_api_token" :disabled="!canWrite" :placeholder="optimizeConfig.effective_has_llm_api_token ? 'Token already set' : 'Enter your API token'" />
              <p v-if="optimizeConfig.effective_has_llm_api_token" style="margin:4px 0 0;color:var(--muted);font-size:0.82rem">✓ Token is configured</p>
            </div>
            <div class="field" v-else style="max-width:220px">
              <label>Timeout (seconds)</label>
              <input type="number" min="5" v-model.number="optimizeConfig.llm_timeout_seconds" :disabled="!canWrite" />
            </div>
          </div>
          <div class="create-grid" v-if="modelRequiresToken()">
            <div class="field" style="max-width:220px">
              <label>Timeout (seconds)</label>
              <input type="number" min="5" v-model.number="optimizeConfig.llm_timeout_seconds" :disabled="!canWrite" />
            </div>
          </div>
          <p v-if="llmModelsLoading" style="margin:4px 0 0;color:var(--muted);font-size:0.84rem">Loading available models...</p>
          <p v-if="llmModelsLoadError" style="margin:4px 0 0;color:var(--muted);font-size:0.84rem">{{ llmModelsLoadError }}</p>
        </div>

        <div class="btn-row" style="margin-top:12px" v-if="canWrite">
          <button class="secondary" @click="saveOptimizeConfig">Save Config</button>
        </div>
        <p v-if="optimizeConfigStatus" :class="optimizeConfigStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ optimizeConfigStatus }}</p>
        <p style="margin:6px 0 0;color:var(--muted);font-size:0.84rem">
          Active model: {{ optimizeConfig.effective_llm_model }} | Active provider: {{ optimizeConfig.effective_llm_provider }} | Timeout: {{ optimizeConfig.effective_llm_timeout_seconds }}s
        </p>
      </div>

      <div v-if="isAdmin" class="opt-config-box opt-config-box-standalone" style="margin-top:14px">
        <div class="opt-settings-group">
          <h5>Global Configuration (admin)</h5>
          <p style="margin:0 0 10px;color:var(--muted);font-size:0.88rem">
            These values are shared app-wide and stored in global_config.
          </p>
          <div class="btn-row" style="margin-bottom:10px">
            <button class="ghost" @click="loadGlobalConfig" :disabled="globalConfigLoading">
              {{ globalConfigLoading ? "Loading..." : "Refresh Global Config" }}
            </button>
          </div>

          <p v-if="!globalConfigEntries.length && !globalConfigLoading" style="color:var(--muted)">
            No global config entries returned.
          </p>

          <div v-for="entry in globalConfigEntries" :key="entry.key" style="padding:10px 0;border-top:1px solid var(--line)">
            <div class="field" style="margin-bottom:8px">
              <label>{{ entry.key }}</label>
              <select
                v-if="getGlobalConfigControlType(entry) === 'select'"
                class="select-pretty"
                v-model="entry.draft"
              >
                <option v-for="optionValue in getGlobalConfigOptions(entry)" :key="optionValue" :value="optionValue">
                  {{ entry.key === 'OPTIMIZER_PROVIDER' ? getProviderLabel(optionValue) : optionValue }}
                </option>
              </select>
              <input
                v-else-if="getGlobalConfigControlType(entry) === 'integer'"
                type="number"
                step="1"
                v-model="entry.draft"
              />
              <label v-else-if="getGlobalConfigControlType(entry) === 'boolean'" class="gc-switch">
                <input
                  type="checkbox"
                  :checked="String(entry.draft || '').toLowerCase() === 'true'"
                  @change="setGlobalConfigBooleanDraft(entry, $event.target.checked)"
                />
                <span class="gc-switch-track"></span>
                <span class="gc-switch-label">{{ String(entry.draft || '').toLowerCase() === 'true' ? 'Enabled' : 'Disabled' }}</span>
              </label>
              <input v-else v-model="entry.draft" />
            </div>
            <div class="btn-row">
              <button class="secondary" @click="saveGlobalConfigEntry(entry)" :disabled="entry.saving || entry.draft === entry.value">
                {{ entry.saving ? "Saving..." : "Save" }}
              </button>
              <button class="ghost" @click="resetGlobalConfigDraft(entry)" :disabled="entry.saving || entry.draft === entry.value">
                Reset
              </button>
            </div>
          </div>

          <p v-if="globalConfigStatus" :class="globalConfigStatus.includes('Failed') ? 'status-err' : 'status-ok'">
            {{ globalConfigStatus }}
          </p>
        </div>
      </div>

      <div v-if="canViewAdmin" class="admin-panel">
        <div class="admin-panel-header">
          <div>
            <h3>{{ isViewer ? 'Read-only admin data' : 'Admin tools moved' }}</h3>
            <p>{{ isViewer ? 'Viewer can inspect projects, users, and roles in the Admin tab.' : 'Project and user management are now available in the dedicated Admin tab.' }}</p>
          </div>
          <button class="secondary" @click="activeTab='admin'">Open Admin</button>
        </div>
      </div>
    </div>

    <div class="tab-panel" v-if="activeTab==='plugins'">
      <div class="plugin-panel-header">
        <div>
          <h2 style="margin-top:0">Plugins</h2>
          <p class="plugin-panel-subtitle">Each plugin appears in its own group box. Controls are rendered in the order requested by the plugin.</p>
        </div>
        <div class="btn-row">
          <button class="ghost" @click="loadPlugins" :disabled="pluginsLoading">{{ pluginsLoading ? 'Loading...' : 'Refresh' }}</button>
          <button v-if="isAdmin" class="secondary" @click="rescanPlugins" :disabled="pluginsLoading">Rescan</button>
        </div>
      </div>

      <div class="plugin-filter-bar">
        <div class="plugin-filter-bar-header">
          <div class="field plugin-filter-field">
            <label>Search by name</label>
            <input v-model="pluginNameFilter" placeholder="example, modal, headless..." />
          </div>
          <button type="button" class="ghost plugin-filter-bar-toggle" @click="togglePluginFilterBar">
            {{ pluginFilterBarOpen ? 'Hide filters' : 'Show filters' }}
          </button>
        </div>
        <div v-if="pluginFilterBarOpen" class="plugin-filter-bar-body">
          <div class="plugin-filter-tags">
            <span class="plugin-filter-tags-label">Filter tags</span>
            <div class="plugin-filter-tag-groups" v-if="pluginTagFilterGroups.length">
              <div class="plugin-filter-tag-group" v-for="group in pluginTagFilterGroups" :key="group.key">
                <div class="plugin-tag-group-title">{{ group.label }}</div>
                <div class="chips plugin-filter-chip-list">
                  <button
                    v-for="tag in group.tags"
                    :key="group.key + '-' + tag"
                    type="button"
                    class="chip plugin-filter-chip"
                    :class="{ active: isPluginTagActive(tag) }"
                    @click="togglePluginTagFilter(tag)"
                  >
                    {{ tag }}
                  </button>
                </div>
              </div>
            </div>
            <p v-else class="plugin-filter-empty">No tags available yet.</p>
          </div>
          <div class="plugin-filter-mode">
            <span class="plugin-filter-tags-label">Tag match</span>
            <div class="plugin-match-switch" role="group" aria-label="Tag match mode">
              <button type="button" class="chip plugin-match-chip" :class="{ active: pluginTagMatchMode === 'or' }" @click="setPluginTagMatchMode('or')">OR</button>
              <button type="button" class="chip plugin-match-chip" :class="{ active: pluginTagMatchMode === 'and' }" @click="setPluginTagMatchMode('and')">AND</button>
            </div>
            <p class="plugin-filter-empty">OR matches any selected tag. AND requires all selected tags.</p>
          </div>
          <div class="btn-row plugin-filter-actions">
            <button class="ghost" @click="clearPluginFilters" :disabled="!pluginNameFilter && !pluginTagFilters.length">Clear filters</button>
          </div>
        </div>
      </div>

      <p v-if="pluginsStatus" :class="pluginsStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ pluginsStatus }}</p>
      <p v-if="!filteredPlugins.length && !pluginsLoading" style="color:var(--muted)">No plugins match the current filters.</p>

      <div class="plugin-scroll-area" v-if="filteredPlugins.length">
        <fieldset class="group-box plugin-group-box" v-for="plugin in filteredPlugins" :key="plugin.name">
          <legend>{{ plugin.name }}</legend>
          <div class="plugin-card-header">
            <div class="plugin-card-title-row">
              <img v-if="pluginHasImageIcon(plugin.icon)" :src="plugin.icon" :alt="plugin.name" class="plugin-card-icon" />
              <div v-else class="plugin-card-icon plugin-card-icon-fallback">{{ pluginIconFallback(plugin) }}</div>
              <div>
                <div class="plugin-card-title">{{ plugin.name }} <span class="plugin-card-version">v{{ plugin.version }}</span></div>
                <div class="plugin-card-description">{{ plugin.description }}</div>
              </div>
            </div>
            <div class="chips plugin-state-chips">
              <span class="chip">{{ plugin.state }}</span>
              <span class="chip" v-if="plugin.available">available</span>
              <span class="chip" v-if="!plugin.compatible">incompatible</span>
              <span class="chip chip-warn" v-if="getPluginFailureCount(plugin.name) > 0">failures: {{ getPluginFailureCount(plugin.name) }}</span>
              <span class="chip chip-err" v-if="getPluginBlockedCount(plugin.name) > 0">blocked: {{ getPluginBlockedCount(plugin.name) }}</span>
            </div>
          </div>

          <div class="plugin-card-meta">
            <div><strong>Source:</strong> {{ plugin.source_path }}</div>
            <div><strong>Routes:</strong> {{ plugin.active_routes.length }}</div>
            <div><strong>Hooks:</strong> {{ plugin.hooks.length }}</div>
            <div><strong>Health fails:</strong> {{ plugin.health_failures }}</div>
            <div><strong>Signature:</strong> {{ plugin.signature_status }}<template v-if="plugin.signature_signer"> by {{ plugin.signature_signer }}</template></div>
          </div>

          <p v-if="plugin.unavailable_reason" class="status-err">{{ plugin.unavailable_reason }}</p>
          <p v-if="plugin.last_error" class="status-err">{{ plugin.last_error }}</p>
          <p v-if="plugin.signature_error" class="status-err">{{ plugin.signature_error }}</p>

          <div class="plugin-routes" v-if="plugin.runtime_failures && Object.keys(plugin.runtime_failures).length">
            <div class="plugin-routes-title">Runtime failure counters</div>
            <div class="plugin-route-item" v-for="(count, endpointName) in plugin.runtime_failures" :key="endpointName">{{ endpointName }}: {{ count }}</div>
          </div>

          <div class="btn-row" v-if="isAdmin">
            <button class="ghost" @click="managePlugin(plugin.name, 'load')" :disabled="plugin.state==='running' || !plugin.compatible">Load</button>
            <button class="ghost" @click="managePlugin(plugin.name, 'reload')" :disabled="!plugin.compatible">Reload</button>
            <button class="ghost" @click="managePlugin(plugin.name, 'health')">Health</button>
            <button class="ghost" @click="togglePluginDiagnostics(plugin.name)">{{ isPluginDiagnosticsOpen(plugin.name) ? 'Hide diagnostics' : 'Diagnostics' }}</button>
            <button class="danger" @click="managePlugin(plugin.name, 'unload')" :disabled="plugin.state==='stopped'">Unload</button>
          </div>

          <div class="btn-row" v-if="getPluginModalLaunchers(plugin).length">
            <button
              v-for="endpoint in getPluginModalLaunchers(plugin)"
              :key="endpoint.name"
              class="secondary"
              @click="openPluginModal(plugin, endpoint.name)"
              :disabled="!plugin.available || !plugin.compatible || pluginModalLoading"
            >
              {{ endpoint.description || ('Open ' + endpoint.name) }}
            </button>
          </div>

          <div class="plugin-routes" v-if="isPluginDiagnosticsOpen(plugin.name)">
            <div class="plugin-routes-title">Diagnostics</div>
            <p v-if="isPluginDiagnosticsLoading(plugin.name)" style="margin:0;color:var(--muted)">Loading diagnostics...</p>
            <template v-else>
              <p v-if="getPluginDiagnostics(plugin.name)?.error" class="status-err" style="margin:0">{{ getPluginDiagnostics(plugin.name).error }}</p>
              <template v-else>
                <div class="plugin-route-item">State: {{ getPluginDiagnostics(plugin.name)?.state || 'unknown' }}</div>
                <div class="plugin-route-item">Lifecycle active: {{ getPluginDiagnostics(plugin.name)?.lifecycle_active ? 'yes' : 'no' }}</div>
                <div class="plugin-route-item">Health failures: {{ getPluginDiagnostics(plugin.name)?.health_failures ?? 0 }}</div>
                <div class="plugin-route-item">Endpoint diagnostics:</div>
                <div
                  class="plugin-route-item"
                  v-for="entry in (getPluginDiagnostics(plugin.name)?.endpoint_diagnostics || [])"
                  :key="'endpoint-' + plugin.name + '-' + entry.endpoint_name"
                >
                  {{ entry.endpoint_name }} | failures: {{ entry.consecutive_failures }} | blocked: {{ entry.blocked ? 'yes' : 'no' }}<template v-if="entry.last_error"> | last error: {{ entry.last_error }}</template>
                </div>
                <div class="plugin-route-item">Hook diagnostics:</div>
                <div
                  class="plugin-route-item"
                  v-for="entry in (getPluginDiagnostics(plugin.name)?.hook_diagnostics || [])"
                  :key="'hook-' + plugin.name + '-' + entry.hook_key"
                >
                  {{ entry.hook_key }} | failures: {{ entry.consecutive_failures }} | blocked: {{ entry.blocked ? 'yes' : 'no' }}<template v-if="entry.last_error"> | last error: {{ entry.last_error }}</template>
                </div>
              </template>
            </template>
          </div>

          <div class="plugin-routes" v-if="plugin.active_routes.length">
            <div class="plugin-routes-header">
              <div class="plugin-routes-title">Registered routes</div>
              <button type="button" class="ghost plugin-routes-toggle" @click="togglePluginRoutes(plugin.name)">
                {{ isPluginRoutesOpen(plugin.name) ? 'Hide' : 'Show' }}
              </button>
            </div>
            <div v-if="isPluginRoutesOpen(plugin.name)">
              <div class="plugin-route-item" v-for="route in plugin.active_routes" :key="route">{{ route }}</div>
            </div>
          </div>

          <div class="plugin-controls" v-if="plugin.ui_controls && plugin.ui_controls.length">
            <div class="plugin-control" v-for="control in plugin.ui_controls" :key="control.name">
              <label>{{ control.label }}</label>
              <p v-if="control.description" class="plugin-control-description">{{ control.description }}</p>

              <label class="gc-switch" v-if="control.control_type==='checkbox'">
                <input
                  type="checkbox"
                  :checked="!!getPluginControlValue(plugin.name, control.name)"
                  :disabled="!canUsePluginControl(plugin, control) || !plugin.available"
                  @change="invokePluginControl(plugin, control, $event.target.checked)"
                />
                <span class="gc-switch-track"></span>
                <span class="gc-switch-label">{{ getPluginControlValue(plugin.name, control.name) ? 'Enabled' : 'Disabled' }}</span>
              </label>

              <select
                v-else-if="control.control_type==='dropdown'"
                class="select-pretty"
                :value="getPluginControlValue(plugin.name, control.name)"
                :disabled="!canUsePluginControl(plugin, control) || !plugin.available"
                @change="invokePluginControl(plugin, control, $event.target.value)"
              >
                <option v-for="option in control.options" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>

              <div v-else-if="control.control_type==='button'" class="btn-row">
                <button class="secondary" @click="invokePluginControl(plugin, control)" :disabled="!canUsePluginControl(plugin, control) || !plugin.available">
                  {{ control.label }}
                </button>
              </div>

              <input
                v-else-if="control.control_type==='text'"
                :value="getPluginControlValue(plugin.name, control.name)"
                :placeholder="control.placeholder || ''"
                :disabled="!canUsePluginControl(plugin, control) || !plugin.available"
                @change="invokePluginControl(plugin, control, $event.target.value)"
              />

              <textarea
                v-else-if="control.control_type==='textarea'"
                :value="getPluginControlValue(plugin.name, control.name)"
                :placeholder="control.placeholder || ''"
                :disabled="!canUsePluginControl(plugin, control) || !plugin.available"
                @change="invokePluginControl(plugin, control, $event.target.value)"
              ></textarea>
            </div>
          </div>
          <p v-else class="plugin-empty-note">This plugin does not request visual controls.</p>

          <p v-if="pluginResponses[plugin.name]" :class="pluginResponses[plugin.name].type === 'err' ? 'status-err' : 'status-ok'">
            {{ pluginResponses[plugin.name].message }}
          </p>
        </fieldset>
      </div>
    </div>

    <div class="tab-panel" v-if="activeTab==='admin' && canViewAdmin">
      <div class="admin-panel" style="margin-top:0;border-top:none;padding-top:0">
        <div class="admin-panel-header">
          <div>
            <h3>Administration</h3>
            <p>{{ canWrite ? 'Manage projects, users, and project access rights.' : 'Viewer mode: inspect projects, users, and roles without making changes.' }}</p>
          </div>
          <button class="ghost" @click="Promise.all([loadRoles(), loadProjects(), loadUsers()])" :disabled="usersLoading || projectsLoading">{{ (usersLoading || projectsLoading) ? 'Loading...' : 'Refresh Admin Data' }}</button>
        </div>

        <div class="admin-grid">
          <div class="admin-card">
            <h4>Projects</h4>
            <div class="field" v-if="canWrite">
              <label>New Project Name</label>
              <input v-model="newProjectForm.name" placeholder="payments" />
            </div>
            <div class="btn-row" v-if="canWrite">
              <button class="secondary" @click="createProjectRecord">Create Project</button>
            </div>
            <p v-if="projectsStatus" :class="projectsStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ projectsStatus }}</p>
            <p v-if="!projects.length && !projectsLoading" style="color:var(--muted)">No projects yet.</p>
            <div class="project-list">
              <div class="project-row" v-for="project in projects" :key="project.id">
                <div v-if="canWrite && editingProjectId===project.id" class="project-edit-row">
                  <input v-model="editProjectForm.name" />
                  <div class="btn-row">
                    <button class="secondary" @click="saveProjectEdit(project.id)">Save</button>
                    <button class="ghost" @click="cancelProjectEdit">Cancel</button>
                  </div>
                </div>
                <div v-else class="project-row-static">
                  <div class="project-name">{{ project.name }}</div>
                  <div class="btn-row" v-if="canWrite">
                    <button class="ghost" @click="beginEditProject(project)">Rename</button>
                    <button class="danger" @click="deleteProjectRecord(project)">Delete</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="admin-card" v-if="canWrite">
            <h4>Create User</h4>
            <div class="field">
              <label>Username</label>
              <input v-model="newUserForm.username" placeholder="developer-1" />
            </div>
            <div class="field">
              <label>Password</label>
              <input type="password" v-model="newUserForm.password" placeholder="Temporary password" />
            </div>
            <div class="create-grid">
              <div class="field">
                <label>Role</label>
                <select class="select-pretty" v-model="newUserForm.role">
                  <option v-for="roleName in roleOptions" :key="roleName" :value="roleName">{{ roleName }}</option>
                </select>
              </div>
              <div class="field">
                <label>Status</label>
                <select class="select-pretty" v-model="newUserForm.is_active">
                  <option :value="true">active</option>
                  <option :value="false">inactive</option>
                </select>
              </div>
            </div>
            <div class="field">
              <label>Projects</label>
              <div class="project-selector" v-if="availableProjectNames.length">
                <button
                  type="button"
                  class="project-pill"
                  :class="{ active: isProjectSelected(newUserForm, projectName) }"
                  v-for="projectName in availableProjectNames"
                  :key="projectName"
                  @click="toggleProjectSelection(newUserForm, projectName)"
                >
                  {{ projectName }}
                </button>
              </div>
              <p v-else class="project-selector-empty">Create at least one project before assigning rights.</p>
            </div>
            <div class="btn-row">
              <button class="secondary" @click="createUserAccount">Create User</button>
            </div>
          </div>

          <div class="admin-card admin-card-wide admin-card-full">
            <h4>Existing Users</h4>
            <p v-if="usersStatus" :class="usersStatus.includes('Failed') ? 'status-err' : 'status-ok'">{{ usersStatus }}</p>
            <p v-if="!users.length && !usersLoading" style="color:var(--muted)">No users found.</p>
            <div class="user-list">
              <div class="user-card" v-for="user in users" :key="user.id">
                <div class="user-card-header">
                  <div>
                    <div class="user-card-title">{{ user.username }}</div>
                    <div class="user-card-meta">Role: {{ user.role }} | {{ user.is_active ? 'active' : 'inactive' }}</div>
                  </div>
                  <div class="chips">
                    <span class="chip" v-for="project in user.projects" :key="project">{{ project }}</span>
                    <span class="chip" v-if="!user.projects.length">all / none assigned</span>
                  </div>
                </div>

                <div v-if="canWrite && editingUserId===user.id" class="user-editor">
                  <div class="field">
                    <label>Username</label>
                    <input v-model="editUserForm.username" />
                  </div>
                  <div class="create-grid">
                    <div class="field">
                      <label>Role</label>
                      <select class="select-pretty" v-model="editUserForm.role">
                        <option v-for="roleName in roleOptions" :key="roleName" :value="roleName">{{ roleName }}</option>
                      </select>
                    </div>
                    <div class="field">
                      <label>Status</label>
                      <select class="select-pretty" v-model="editUserForm.is_active">
                        <option :value="true">active</option>
                        <option :value="false">inactive</option>
                      </select>
                    </div>
                  </div>
                  <div class="field">
                    <label>New Password (optional)</label>
                    <input type="password" v-model="editUserForm.password" placeholder="Leave empty to keep current password" />
                  </div>
                  <div class="field">
                    <label>Projects</label>
                    <div class="project-selector" v-if="availableProjectNames.length">
                      <button
                        type="button"
                        class="project-pill"
                        :class="{ active: isProjectSelected(editUserForm, projectName) }"
                        v-for="projectName in availableProjectNames"
                        :key="projectName"
                        @click="toggleProjectSelection(editUserForm, projectName)"
                      >
                        {{ projectName }}
                      </button>
                    </div>
                    <p v-else class="project-selector-empty">Create at least one project before assigning rights.</p>
                  </div>
                  <div class="btn-row">
                    <button class="secondary" @click="saveUserEdit(user.id)">Save</button>
                    <button class="ghost" @click="cancelUserEdit">Cancel</button>
                  </div>
                </div>

                <div v-else class="btn-row" v-if="canWrite">
                  <button class="ghost" @click="beginEditUser(user)">Edit</button>
                  <button class="danger" :disabled="currentUser.id===user.id" @click="deleteUserAccount(user)">Delete</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ACCOUNT TAB -->
    <div class="tab-panel" v-if="activeTab==='account'">
      <h2 style="margin-top:0">Change Password</h2>
      <p style="color:var(--muted);margin-bottom:1.2rem">You may change your password at most once every 30 minutes.</p>
      <div style="max-width:420px">
        <div class="field">
          <label>Current Password</label>
          <input type="password" v-model="changePasswordForm.current_password" placeholder="Current password" />
        </div>
        <div class="field">
          <label>New Password</label>
          <input type="password" v-model="changePasswordForm.new_password" placeholder="New password" />
        </div>
        <div class="field">
          <label>Confirm New Password</label>
          <input type="password" v-model="changePasswordForm.confirm_password" placeholder="Repeat new password" @keyup.enter="changeOwnPassword" />
        </div>
        <div class="btn-row" style="margin-top:0.8rem">
          <button @click="changeOwnPassword"
            :disabled="changePasswordBusy || !changePasswordForm.current_password || !changePasswordForm.new_password || !changePasswordForm.confirm_password">
            {{ changePasswordBusy ? 'Saving…' : 'Change Password' }}
          </button>
        </div>
        <p v-if="changePasswordStatus" :class="changePasswordStatus.startsWith('ok:') ? 'status-ok' : 'status-err'"
          style="margin-top:0.7rem">{{ changePasswordStatus.replace(/^(ok:|error:)/,'') }}</p>
      </div>
    </div>

    <!-- ABOUT TAB -->
    <div class="tab-panel" v-if="activeTab==='about'">
      <div class="about-card">
        <img src="/PromptMan_240x240.png" alt="PromptMan logo" class="about-logo" />
        <h2 style="margin-top:0">About PromptMan</h2>
        <p class="about-motto">The Secure home for LLM and AI Prompts</p>
        <p><strong>Author:</strong> Alexander Ivanov</p>
        <p><strong>Email:</strong> <a href="mailto:dev.python.powershell@gmail.com">dev.python.powershell@gmail.com</a></p>
        <p><strong>GitHub:</strong> <a href="https://github.com/VeryComplexAndLongName/PromptMan" target="_blank" rel="noopener noreferrer">https://github.com/VeryComplexAndLongName/PromptMan</a></p>
      </div>
    </div>

    <div class="modal-backdrop" v-if="optimizerModalOpen" @click.self="closeOptimizerModal">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Prompt Optimization</h3>
          <button class="ghost" @click="closeOptimizerModal">Close</button>
        </div>

        <p class="status-err" v-if="optimizerError">{{ optimizerError }}</p>
        <p v-if="optimizerStatus" style="margin:0 0 8px;color:var(--muted)">
          Status: {{ optimizerStatus }}
        </p>
        <p v-if="optimizerLoading" style="margin:0 0 10px;color:var(--muted)">Optimization is running on backend ...</p>

        <div class="optimizer-log-box">
          <div class="optimizer-log-title">Execution log</div>
          <div class="optimizer-log-empty" v-if="!optimizerLogs.length">No log entries yet.</div>
          <div
            class="optimizer-log-line"
            v-for="(entry, idx) in optimizerLogs"
            :key="idx"
            :class="'log-' + entry.level"
          >
            [{{ entry.ts }}] {{ entry.message }}
          </div>
        </div>

        <div v-if="!optimizerLoading">
          <div class="md-content" style="margin-top:10px" v-html="md(optimizedMarkdown || buildPromptMarkdown(optimizedDraft))"></div>
          <div class="btn-row" style="margin-top:12px" v-if="canWrite">
            <button class="secondary" :disabled="optimizerLoading" @click="reoptimizePrompt">Reoptimize</button>
            <button @click="applyOptimizedPrompt">Update Prompt</button>
          </div>
        </div>
      </div>
    </div>

    <div
      class="modal-backdrop"
      v-if="pluginModalOpen"
      @pointerdown.self="handlePluginModalBackdropPointerDown"
      @click.self="handlePluginModalBackdropClick"
    >
      <div class="modal-card">
        <div class="modal-header">
          <div>
            <h3>{{ pluginModalSession?.modal?.title || pluginModalPluginName || 'Plugin Modal' }}</h3>
            <p v-if="pluginModalSession?.modal?.description" style="margin:4px 0 0;color:var(--muted)">{{ pluginModalSession.modal.description }}</p>
          </div>
          <div class="btn-row" style="margin-top:0">
            <button class="ghost" v-if="pluginModalSession?.modal?.allow_stop !== false" @click="stopPluginModal" :disabled="pluginModalLoading || pluginModalSession?.state === 'stopped'">{{ pluginModalSession?.modal?.stop_label || 'Stop Plugin' }}</button>
            <button class="ghost" @click="closePluginModal(true)">{{ pluginModalSession?.modal?.close_label || 'Close' }}</button>
          </div>
        </div>

        <p class="status-err" v-if="pluginModalError">{{ pluginModalError }}</p>
        <p v-if="pluginModalStatus" style="margin:0 0 8px;color:var(--muted)">Status: {{ pluginModalStatus }}</p>
        <p v-if="pluginModalLoading" style="margin:0 0 10px;color:var(--muted)">Modal operation is running on backend ...</p>

        <div class="md-content" v-if="pluginModalSession?.modal?.body_markdown" v-html="md(pluginModalSession.modal.body_markdown)"></div>

        <div class="optimizer-log-box" v-if="pluginModalSession?.logs?.length || pluginModalSession?.last_error || pluginModalSession?.state">
          <div class="optimizer-log-title">Modal session</div>
          <div class="optimizer-log-empty" v-if="!pluginModalSession?.logs?.length && !pluginModalSession?.last_error">No modal log entries yet.</div>
          <div class="optimizer-log-line log-warn" v-if="pluginModalSession?.state">State: {{ pluginModalSession.state }}</div>
          <div class="optimizer-log-line log-error" v-if="pluginModalSession?.last_error">Error: {{ pluginModalSession.last_error }}</div>
          <div class="optimizer-log-line" v-for="(entry, idx) in (pluginModalSession?.logs || [])" :key="'modal-log-' + idx">{{ entry }}</div>
        </div>

        <div class="plugin-controls" v-if="pluginModalControls.length">
          <div class="plugin-control" v-for="control in pluginModalControls" :key="control.name">
            <label>{{ control.label }}</label>
            <p v-if="control.description" class="plugin-control-description">{{ control.description }}</p>

            <label class="gc-switch" v-if="control.control_type==='checkbox'">
              <input
                type="checkbox"
                :checked="!!getPluginModalControlValue(control.name)"
                :disabled="pluginModalSession?.state === 'stopped' || pluginModalLoading"
                @change="invokePluginModalControl(control, $event.target.checked)"
              />
              <span class="gc-switch-track"></span>
              <span class="gc-switch-label">{{ getPluginModalControlValue(control.name) ? 'Enabled' : 'Disabled' }}</span>
            </label>

            <select
              v-else-if="control.control_type==='dropdown'"
              class="select-pretty"
              :value="getPluginModalControlValue(control.name)"
              :disabled="pluginModalSession?.state === 'stopped' || pluginModalLoading"
              @change="invokePluginModalControl(control, $event.target.value)"
            >
              <option v-for="option in control.options" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>

            <div v-else-if="control.control_type==='button'" class="btn-row">
              <button class="secondary" @click="invokePluginModalControl(control)" :disabled="pluginModalSession?.state === 'stopped' || pluginModalLoading">
                {{ control.label }}
              </button>
            </div>

            <input
              v-else-if="control.control_type==='text'"
              :value="getPluginModalControlValue(control.name)"
              :placeholder="control.placeholder || ''"
              :disabled="pluginModalSession?.state === 'stopped' || pluginModalLoading"
              @change="invokePluginModalControl(control, $event.target.value)"
            />

            <textarea
              v-else-if="control.control_type==='textarea'"
              :value="getPluginModalControlValue(control.name)"
              :placeholder="control.placeholder || ''"
              :disabled="pluginModalSession?.state === 'stopped' || pluginModalLoading"
              @change="invokePluginModalControl(control, $event.target.value)"
            ></textarea>
          </div>
        </div>

        <div class="btn-row" style="margin-top:12px">
          <button class="secondary" @click="refreshPluginModal" :disabled="pluginModalLoading || !pluginModalSession">Refresh</button>
        </div>
      </div>
    </div>
    </template>
  `,
}).mount("#app");
