const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  const ct = res.headers.get("content-type") ?? ""
  return ct.includes("json") ? res.json() : (res.text() as unknown as T)
}

// ── Auth ────────────────────────────────────────────────────────────────────
export const auth = {
  login: (password: string) =>
    request("/login", { method: "POST", body: new URLSearchParams({ password }).toString(), headers: { "Content-Type": "application/x-www-form-urlencoded" } }),
  logout: () => request("/logout"),
  setup: (password: string, confirm: string) =>
    request("/setup", { method: "POST", body: new URLSearchParams({ password, confirm }).toString(), headers: { "Content-Type": "application/x-www-form-urlencoded" } }),
}

// ── Dashboard ────────────────────────────────────────────────────────────────
export const dashboard = {
  get: () => request<DashboardData>("/api/dashboard"),
}

// ── Projects ─────────────────────────────────────────────────────────────────
export const projects = {
  list: () => request<Project[]>("/api/projects"),
  create: (data: { name: string; website?: string; description?: string; context?: string }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<Project>(`/api/projects/${id}`),
  update: (id: string, data: Partial<Project>) =>
    request<Project>(`/api/projects/${id}/edit`, { method: "POST", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request(`/api/projects/${id}/delete`, { method: "POST" }),
}

// ── Tasks ────────────────────────────────────────────────────────────────────
export const tasks = {
  list: (projectId: string) => request<Task[]>(`/api/projects/${projectId}/tasks`),
  get: (projectId: string, taskId: string) =>
    request<Task>(`/api/projects/${projectId}/tasks/${taskId}`),
  create: (projectId: string, data: { objective: string; domain: string; persona?: string; context?: string; backend?: string }) =>
    request<{ task_id: string; status: string }>(`/api/projects/${projectId}/tasks`, { method: "POST", body: JSON.stringify(data) }),
  run: (projectId: string, taskId: string) =>
    request(`/api/projects/${projectId}/tasks/${taskId}/run`, { method: "POST" }),
  status: (projectId: string, taskId: string) =>
    request<TaskStatus>(`/projects/${projectId}/tasks/${taskId}/status.json`),
  chat: (projectId: string, taskId: string, message: string) =>
    request(`/api/projects/${projectId}/tasks/${taskId}/chat`, { method: "POST", body: JSON.stringify({ message }) }),
  feedback: (projectId: string, taskId: string, signal: 1 | -1, note?: string) =>
    request(`/api/projects/${projectId}/tasks/${taskId}/feedback`, { method: "POST", body: JSON.stringify({ signal, note }) }),
  delete: (projectId: string, taskId: string) =>
    request(`/api/projects/${projectId}/tasks/${taskId}/delete`, { method: "POST" }),
}

// ── Knowledge Base ────────────────────────────────────────────────────────────
export const kb = {
  get: (projectId: string) => request<KBData>(`/api/projects/${projectId}/kb`),
  addSource: (projectId: string, url: string) =>
    request(`/api/projects/${projectId}/kb/sources`, { method: "POST", body: JSON.stringify({ url }) }),
  deleteSource: (projectId: string, sourceId: string) =>
    request(`/api/projects/${projectId}/kb/sources/${sourceId}/delete`, { method: "POST" }),
  retrySource: (projectId: string, sourceId: string) =>
    request(`/api/projects/${projectId}/kb/sources/${sourceId}/retry`, { method: "POST" }),
  getSourceChunks: (projectId: string, sourceId: string) =>
    request<KBChunk[]>(`/api/projects/${projectId}/kb/sources/${sourceId}/chunks`),
  search: (projectId: string, query: string) =>
    request<KBSearchResult[]>(`/api/projects/${projectId}/kb/search?q=${encodeURIComponent(query)}`),
  chat: (projectId: string, message: string) =>
    request(`/api/projects/${projectId}/kb/chat`, { method: "POST", body: JSON.stringify({ message }) }),
}

// ── Memory ────────────────────────────────────────────────────────────────────
export const memory = {
  get: (projectId: string) => request<MemoryData>(`/api/projects/${projectId}/memory`),
  deleteRun: (projectId: string, runId: string) =>
    request(`/api/projects/${projectId}/memory/${runId}/delete`, { method: "POST" }),
}

// ── Agents ───────────────────────────────────────────────────────────────────
export const agents = {
  list: () => request<AgentSpec[]>("/api/agents"),
  update: (key: string, data: Partial<AgentConfig>) =>
    request(`/api/agents/${key}`, { method: "POST", body: JSON.stringify(data) }),
  create: (data: Partial<AgentSpec>) =>
    request("/api/agents", { method: "POST", body: JSON.stringify(data) }),
  delete: (key: string) =>
    request(`/api/agents/${key}/delete`, { method: "POST" }),
}

// ── Personas ──────────────────────────────────────────────────────────────────
export const personas = {
  list: () => request<Persona[]>("/api/personas"),
  create: (data: Partial<Persona>) =>
    request("/api/personas/create", { method: "POST", body: JSON.stringify(data) }),
  generate: (description: string) =>
    request<Persona>("/api/personas/generate", { method: "POST", body: JSON.stringify({ description }) }),
  delete: (id: string) =>
    request(`/api/personas/${id}/delete`, { method: "POST" }),
}

// ── Focus ─────────────────────────────────────────────────────────────────────
export const focus = {
  list: () => request<FocusEntity[]>("/api/focus"),
}

// ── Artifacts ─────────────────────────────────────────────────────────────────
export const artifacts = {
  list: (projectId?: string) =>
    request<Artifact[]>(`/api/artifacts${projectId ? `?project=${projectId}` : ""}`),
}

// ── Settings ──────────────────────────────────────────────────────────────────
export const settings = {
  get: () => request<SentinelConfig>("/api/settings"),
  updateBackend: (data: Partial<BackendConfig>) =>
    request("/api/settings/backends", { method: "POST", body: JSON.stringify(data) }),
  updateGeneration: (data: GenerationConfig) =>
    request("/api/settings/generation", { method: "POST", body: JSON.stringify(data) }),
  updateGovernance: (data: GovernanceConfig) =>
    request("/api/settings/governance", { method: "POST", body: JSON.stringify(data) }),
  updateSearch: (data: SearchConfig) =>
    request("/api/settings/search", { method: "POST", body: JSON.stringify(data) }),
  updateStrategy: (data: StrategyConfig) =>
    request("/api/settings/strategy", { method: "POST", body: JSON.stringify(data) }),
  updateMemory: (data: MemoryConfig) =>
    request("/api/settings/memory", { method: "POST", body: JSON.stringify(data) }),
  changePassword: (current: string, password: string) =>
    request("/api/settings/password", { method: "POST", body: JSON.stringify({ current, password }) }),
}

// ── Prompts ───────────────────────────────────────────────────────────────────
export const prompts = {
  list: () => request<PromptTemplate[]>("/api/prompts"),
  get: (key: string) => request<PromptTemplate>(`/api/prompts/${key}`),
  update: (key: string, template: string) =>
    request(`/api/settings/prompts/${key}`, { method: "POST", body: JSON.stringify({ template }) }),
  reset: (key: string) =>
    request(`/api/settings/prompts/${key}/reset`, { method: "POST" }),
  create: (data: Partial<PromptTemplate>) =>
    request("/api/settings/prompts/create", { method: "POST", body: JSON.stringify(data) }),
}

// ── Types ─────────────────────────────────────────────────────────────────────
export interface DashboardData {
  total_runs: number
  total_artifacts: number
  total_public_findings: number
  total_private_findings: number
  recent_runs: RunRecord[]
  focus: FocusEntity[]
}

export interface Project {
  id: string
  name: string
  website?: string
  description?: string
  context?: string
  created_at: string
  task_count?: number
  artifact_count?: number
}

export interface Task {
  id: string
  project_id: string
  objective: string
  domain: string
  persona?: string
  status: "created" | "planned" | "running" | "done" | "failed"
  created_at: string
  result?: TaskResult
  chat?: ChatMessage[]
}

export interface TaskStatus {
  status: "running" | "done" | "failed"
  steps: StepStatus[]
  current_step?: string
  findings_so_far?: number
  sources_checked?: number
  log?: LogEntry[]
}

export interface StepStatus {
  id: string
  capability: string
  status: "pending" | "running" | "done" | "failed"
  tool_calls?: string[]
}

export interface LogEntry {
  timestamp: string
  agent: string
  message: string
  type: "info" | "tool" | "finding" | "error"
}

export interface TaskResult {
  summary: string
  artifacts: ArtifactData[]
  citations: Citation[]
  grade?: GradeReport
}

export interface ArtifactData {
  type: string
  target: string
  content: Record<string, unknown>
  public_count: number
  private_count: number
  gaps: number
}

export interface Citation {
  label: string
  url?: string
  boundary: "public" | "private"
}

export interface GradeReport {
  passed: boolean
  score?: number
  hard_failures: string[]
}

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
  timestamp: string
}

export interface RunRecord {
  id: string
  entity: string
  target: string
  mode: string
  backend: string
  kind: string
  public: number
  private: number
  gaps: number
  reference: string
  finding_texts: string[]
  created_at: string
  project_id?: string
}

export interface Artifact {
  id: string
  target: string
  type: string
  mode: string
  backend: string
  public_count: number
  private_count: number
  gaps: number
  content?: Record<string, unknown>
  created_at: string
  project_id?: string
  task_id?: string
  finding_texts: string[]
  reference: string
}

export interface KBData {
  sources: KBSource[]
  chunk_count: number
}

export interface KBSource {
  id: string
  url: string
  source_type: string
  status: "pending" | "crawling" | "indexed" | "failed"
  chunk_count: number
  error?: string
}

export interface KBSearchResult {
  text: string
  source: string
  score: number
}

export interface KBChunk {
  id: string
  text: string
  metadata: {
    url?: string
    source_id?: string
    source_type?: string
    title?: string
    chunk_index?: number
    [key: string]: unknown
  }
}

export interface MemoryData {
  episodes: RunRecord[]
  facts: MemoryEntry[]
}

export interface MemoryEntry {
  id: string
  entity: string
  boundary: "public" | "private"
  content: string
  source_label: string
  strength: number
  created_at: string
}

export interface FocusEntity {
  id: string
  name: string
  run_count: number
  public_findings: number
  private_signals: number
  last_researched: string
  // UI-computed / optional
  tier?: "tier1" | "tier2" | "tier3"
  type?: string
  description?: string
  priority_score?: number
  gaps?: number
  signals?: number
}

export function taskExportUrl(projectId: string, taskId: string): string {
  return `/projects/${projectId}/tasks/${taskId}/export.html`
}

export interface AgentSpec {
  id: string
  name: string
  capability: string
  role: string
  model?: string
  enabled: boolean
  eval_score?: number
  boundary?: "public_only" | "private_only" | "both" | "orchestrator"
  description?: string
  capabilities?: string[]
  tools?: string[]
}

export interface AgentConfig {
  enabled: boolean
  model?: string
  role: string
  generation: GenerationConfig
}

export interface Persona {
  id: string
  name: string
  description?: string
  role?: string
  public_sources?: number
  private_sources?: number
  domains?: string[]
  system_prompt?: string
  reading_level?: string
  tone?: string
  format?: string
  source_policy?: string
}

export interface SentinelConfig {
  backend: BackendConfig
  generation: GenerationConfig
  governance: GovernanceConfig
  search: SearchConfig
  strategy: StrategyConfig
  memory: MemoryConfig
}

// Flat config shape used by the /api/settings page (simpler REST contract)
export interface FlatSentinelConfig {
  backend?: "gemini" | "vllm"
  vllm_base_url?: string
  model?: string
  governance?: "cloud_ok" | "on_prem_preferred" | "on_prem_required"
  temperature?: number
  max_tokens?: number
  thinking_budget?: number
  enable_web_search?: boolean
  max_web_results?: number
  enable_private_retrieval?: boolean
  enable_kb?: boolean
  enable_grading?: boolean
  enable_gap_analysis?: boolean
  gap_threshold?: number
  enable_citation?: boolean
  enable_memory?: boolean
  enable_semantic_memory?: boolean
  memory_ttl_days?: number
  chroma_prefix?: string
  competitor_system_prompt?: string
  account_system_prompt?: string
}

export interface BackendConfig {
  default: "gemini" | "vllm"
  gemini: { model: string }
  vllm: { model: string; api_base: string }
  max_concurrency: number
  max_turns: number
  max_retries: number
}

export interface GenerationConfig {
  temperature?: number
  max_output_tokens?: number
  top_p?: number
  top_k?: number
}

export interface GovernanceConfig {
  compliance_mode: "cloud_ok" | "on_prem_preferred" | "on_prem_required"
  audit_log: boolean
  block_cloud_on_private: boolean
}

export interface SearchConfig {
  provider: string
  results: number
  onprem_fallback: string
  max_calls: number
}

export interface StrategyConfig {
  enabled: boolean
  playbook_dir: string
}

export interface MemoryConfig {
  entity_memory: boolean
  retention_days: number
  episodic_recall: boolean
  kb_context: boolean
}

export interface PromptTemplate {
  key: string
  template: string
  variables: string[]
  default_template: string
  is_custom: boolean
}
