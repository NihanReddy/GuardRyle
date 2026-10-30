export type ProviderHealth = 'healthy' | 'unhealthy' | 'unknown'

export type EmbeddingStatus = {
  configuredProvider: string | null
  configuredModel: string | null
  activeProvider: string | null
  activeModel: string | null
  dimensions: number | null
  execution: 'local' | 'remote' | 'unknown'
  providerHealth: ProviderHealth
  degraded: boolean
  securityEvaluationRequired: boolean
  securityEvaluationAvailable: boolean
  error: string | null
}

export type EmbeddingProvider = {
  id: string
  label: string
  execution: 'local' | 'remote'
  supportedModels: Array<{ id: string; dimensions: number }>
  health: ProviderHealth
}

export type OpenAIStatus = {
  configured: boolean
  connection: 'connected' | 'failed' | 'unknown'
  error: string | null
}

export type DashboardFinding = {
  id: string
  prompt: string
  category: string
  policy: string
  expected: string
  observed: 'allow' | 'deny' | 'review'
  kind: string
  latencyMs: number | null
  source: string
  reasonCode: string
  provider: string | null
  degraded: boolean
  reviewed: boolean
  createdAt: string
}

export type DashboardData = {
  live: boolean
  lastUpdated: string | null
  source: { policy: string; dataset: string; report: string }
  policy: {
    id: string | null
    name: string
    defaultDecision: string | null
    rules: number
    semanticExamples: number
    semanticDenyThreshold: number | null
    semanticReviewThreshold: number | null
  }
  runtime: {
    total: number
    blocked: number
    review: number
    allowed: number
    degraded: number
    reviewed: number
    averageLatencyMs: number | null
    lastEventAt: string | null
  }
  findings: DashboardFinding[]
}

export type EvaluationResponse = {
  decision: 'allow' | 'deny' | 'review'
  reasons: string[]
  rule_hits: string[]
  metadata: {
    request_id: string
    provider_used: string | null
    degraded_mode: boolean
    latency_ms: number | null
  }
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    throw new ApiError(`Backend returned ${response.status}`, response.status)
  }
  return response.json() as Promise<T>
}

export const runtimeApi = {
  getDashboard: () => request<DashboardData>('/api/dashboard'),
  reviewEvent: (requestId: string) => request<{ request_id: string; reviewed: boolean }>(`/api/dashboard/events/${requestId}/review`, { method: 'POST' }),
  getEmbeddingStatus: () => request<EmbeddingStatus>('/api/embedding/status'),
  getProviders: () => request<EmbeddingProvider[]>('/api/embedding/providers'),
  getOpenAIStatus: () => request<OpenAIStatus>('/api/providers/openai/status'),
  saveOpenAIKey: (apiKey: string) => request<OpenAIStatus>('/api/providers/openai/key', {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey }),
  }),
  testOpenAIConnection: () => request<OpenAIStatus>('/api/providers/openai/test', { method: 'POST' }),
  selectProvider: (provider: string, model: string) => request<EmbeddingStatus>('/api/embedding/config', {
    method: 'PUT',
    body: JSON.stringify({ provider, model }),
  }),
  evaluate: (text: string, requiredSecurityCheck = false, policyId?: string) => request<EvaluationResponse>('/api/evaluate', {
    method: 'POST',
    body: JSON.stringify({
      text,
      required_security_check: requiredSecurityCheck,
      ...(policyId ? { policy_id: policyId } : {}),
    }),
  }),
}
