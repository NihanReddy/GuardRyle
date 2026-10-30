import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AlertTriangle, ArrowUpRight, Check, ChevronDown, CircleHelp, Eye, EyeOff, FileUp, Filter, Gauge,
  KeyRound, LayoutDashboard, ListFilter, LockKeyhole, MoreHorizontal, RefreshCw, Save, Search, ServerCog,
  Settings2, ShieldCheck, SlidersHorizontal, UploadCloud, X,
} from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { runtimeApi, type DashboardData, type DashboardFinding, type EmbeddingProvider, type EmbeddingStatus, type OpenAIStatus } from './api'
import './App.css'

type EventStatus = 'blocked' | 'review' | 'allowed'

const navItems = [
  { label: 'Overview', icon: LayoutDashboard }, { label: 'Event log', icon: ListFilter },
  { label: 'Policies', icon: ShieldCheck }, { label: 'Evaluations', icon: Gauge },
]
const statusFromFinding = (finding: DashboardFinding): EventStatus => finding.observed === 'deny' ? 'blocked' : finding.observed === 'review' ? 'review' : 'allowed'
const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`
const emptyEmbeddingStatus: EmbeddingStatus = {
  configuredProvider: null, configuredModel: null, activeProvider: null, activeModel: null,
  dimensions: null, execution: 'unknown', providerHealth: 'unknown', degraded: false,
  securityEvaluationRequired: false, securityEvaluationAvailable: true, error: null,
}

function App() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loadError, setLoadError] = useState('')
  const [activeNav, setActiveNav] = useState('Overview')
  const [statusFilter, setStatusFilter] = useState<EventStatus | 'all'>('all')
  const [query, setQuery] = useState('')
  const [selectedFinding, setSelectedFinding] = useState<DashboardFinding | null>(null)
  const [reviewedIds, setReviewedIds] = useState<string[]>([])
  const [uploadedFile, setUploadedFile] = useState('')
  const [notice, setNotice] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus>(emptyEmbeddingStatus)
  const [providers, setProviders] = useState<EmbeddingProvider[]>([])
  const [openAIStatus, setOpenAIStatus] = useState<OpenAIStatus | null>(null)
  const [openAIKey, setOpenAIKey] = useState('')
  const [showOpenAIKey, setShowOpenAIKey] = useState(false)
  const [runtimeError, setRuntimeError] = useState('')
  const [runtimeBusy, setRuntimeBusy] = useState(false)

  const refreshDashboard = useCallback(async () => {
    try {
      setData(await runtimeApi.getDashboard())
      setLoadError('')
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Live dashboard data is unavailable.')
    }
  }, [])
  useEffect(() => {
    void refreshDashboard()
    const timer = window.setInterval(() => { void refreshDashboard() }, 15_000)
    return () => window.clearInterval(timer)
  }, [refreshDashboard])

  const refreshRuntime = useCallback(async () => {
    setRuntimeBusy(true)
    setRuntimeError('')
    try {
      const [status, availableProviders, openAI] = await Promise.all([
        runtimeApi.getEmbeddingStatus(), runtimeApi.getProviders(), runtimeApi.getOpenAIStatus(),
      ])
      setEmbeddingStatus(status)
      setProviders(availableProviders)
      setOpenAIStatus(openAI)
    } catch (error) {
      setRuntimeError(error instanceof Error ? error.message : 'Runtime status is unavailable.')
    } finally {
      setRuntimeBusy(false)
    }
  }, [])
  useEffect(() => { void refreshRuntime() }, [refreshRuntime])

  const saveOpenAIKey = async () => {
    if (!openAIKey.trim()) { setRuntimeError('Enter an API key before saving.'); return }
    setRuntimeBusy(true)
    try {
      setOpenAIStatus(await runtimeApi.saveOpenAIKey(openAIKey))
      setOpenAIKey('')
      showNotice('OpenAI key saved by the backend. The key is not retained in this browser.')
    } catch (error) { setRuntimeError(error instanceof Error ? error.message : 'The OpenAI key could not be saved.') } finally { setRuntimeBusy(false) }
  }
  const testOpenAIConnection = async () => {
    setRuntimeBusy(true)
    try {
      setOpenAIStatus(await runtimeApi.testOpenAIConnection())
    } catch (error) { setRuntimeError(error instanceof Error ? error.message : 'The OpenAI connection test failed.') } finally { setRuntimeBusy(false) }
  }
  const selectProvider = async (provider: string, model: string) => {
    setRuntimeBusy(true)
    try {
      setEmbeddingStatus(await runtimeApi.selectProvider(provider, model))
      showNotice('Provider configuration confirmed by the backend.')
    } catch (error) { setRuntimeError(error instanceof Error ? error.message : 'The provider configuration was rejected.') } finally { setRuntimeBusy(false) }
  }

  const findings = useMemo(() => data?.findings ?? [], [data])
  const visibleFindings = useMemo(() => findings.filter((finding) => {
    const statusMatches = statusFilter === 'all' || statusFromFinding(finding) === statusFilter
    const searchMatches = !query || `${finding.id} ${finding.prompt} ${finding.category} ${finding.policy}`.toLowerCase().includes(query.toLowerCase())
    return statusMatches && searchMatches && !reviewedIds.includes(finding.id)
  }), [findings, query, reviewedIds, statusFilter])
  const categoryData = data ? [
    { category: 'Blocked', count: data.runtime.blocked },
    { category: 'Review', count: data.runtime.review },
    { category: 'Allowed', count: data.runtime.allowed },
  ] : []

  const showNotice = (message: string) => { setNotice(message); window.setTimeout(() => setNotice(''), 3500) }
  const handleUpload = async (file: File | undefined) => {
    if (!file) return
    if (!/\.(json|ya?ml)$/i.test(file.name)) { showNotice('Choose a JSON or YAML policy file.'); return }
    try {
      if (file.name.toLowerCase().endsWith('.json')) {
        const parsed = JSON.parse(await file.text())
        if (!parsed.id && !parsed.policy_id) throw new Error('Policy needs an id or policy_id field.')
      }
      setUploadedFile(file.name)
      showNotice(`${file.name} passed the local file check.`)
    } catch (error) { showNotice(error instanceof Error ? error.message : 'The policy file could not be read.') }
  }
  const markReviewed = () => {
    if (!selectedFinding) return
    void runtimeApi.reviewEvent(selectedFinding.id)
      .then(() => {
        setReviewedIds((current) => [...current, selectedFinding.id])
        setSelectedFinding(null)
        void refreshDashboard()
        showNotice('Runtime event marked as reviewed.')
      })
      .catch((error: Error) => setRuntimeError(error.message))
  }

  if (loadError) return <div className="data-state"><ShieldCheck size={30} /><h1>Dashboard data unavailable</h1><p>{loadError}</p><button className="primary-button" onClick={() => window.location.reload()}>Retry</button></div>
  if (!data) return <div className="data-state"><ShieldCheck size={30} /><h1>Loading GuardRyle data</h1><p>Reading the latest local policy and evaluation report.</p></div>

  const { policy, runtime } = data
  const metricCards = [
    { label: 'Blocked decisions', value: runtime.blocked.toLocaleString(), note: `of ${runtime.total.toLocaleString()} live events`, icon: <LockKeyhole size={16} />, tone: 'coral' },
    { label: 'Needs review', value: runtime.review.toLocaleString(), note: `${runtime.reviewed.toLocaleString()} reviewed`, icon: <AlertTriangle size={16} />, tone: 'amber' },
    { label: 'Allowed decisions', value: runtime.allowed.toLocaleString(), note: `${runtime.degraded.toLocaleString()} degraded`, icon: <Check size={16} />, tone: 'teal' },
    { label: 'Average latency', value: runtime.averageLatencyMs === null ? '—' : `${runtime.averageLatencyMs.toFixed(1)} ms`, note: 'live audit events', icon: <Gauge size={16} />, tone: 'blue' },
  ]
  const policyRows = [
    { label: 'Deterministic rules', version: `${policy.rules} configured`, live: policy.rules > 0 },
    { label: 'Semantic examples', version: `${policy.semanticExamples} configured`, live: policy.semanticExamples > 0 },
    { label: 'Default decision', version: (policy.defaultDecision ?? 'unavailable').toUpperCase(), live: policy.defaultDecision !== null },
    { label: 'Runtime events', version: `${runtime.total} recorded`, live: true },
  ]

  return (
    <div className="app-shell">
      <aside className="sidebar"><div className="brand-lockup"><div className="brand-mark"><ShieldCheck size={19} /></div><div><strong>GuardRyle</strong><span>control room</span></div></div><div className="workspace-switcher"><div className="workspace-dot">G</div><div><strong>{policy.name}</strong><span>{policy.id}</span></div><ChevronDown size={15} /></div><nav className="primary-nav" aria-label="Main navigation"><span className="nav-kicker">Monitor</span>{navItems.map(({ label, icon: Icon }) => <button key={label} className={`nav-item ${activeNav === label ? 'active' : ''}`} onClick={() => { setActiveNav(label); if (label === 'Event log') document.querySelector('.events-panel')?.scrollIntoView({ behavior: 'smooth' }); if (label === 'Policies') document.querySelector('.policy-panel')?.scrollIntoView({ behavior: 'smooth' }); if (label === 'Evaluations') document.querySelector('.evaluation-panel')?.scrollIntoView({ behavior: 'smooth' }) }}><Icon size={17} /><span>{label}</span>{label === 'Event log' && <em>{findings.length}</em>}</button>)}</nav><div className="sidebar-bottom"><button className={`nav-item ${activeNav === 'Settings' ? 'active' : ''}`} onClick={() => { setActiveNav('Settings'); document.querySelector('.settings-panel')?.scrollIntoView({ behavior: 'smooth' }) }}><Settings2 size={17} /><span>Settings</span></button><button className="nav-item" onClick={() => showNotice(`Dashboard data comes from ${data.source.report}`)}><CircleHelp size={17} /><span>Help center</span></button><div className="user-card"><div className="avatar">GR</div><div><strong>GuardRyle operator</strong><span>Local workspace</span></div><MoreHorizontal size={17} /></div></div></aside>
      <main className="main-content"><header className="topbar"><div className="breadcrumb"><span>{policy.id ?? 'No policy'}</span><span>/</span><strong>{activeNav}</strong></div><div className="topbar-actions"><span className="live-status"><i /> Live runtime data</span><button className="icon-button" title="Refresh live data" onClick={() => void refreshDashboard()}><RefreshCw size={18} /></button><button className="icon-button" title="Policy thresholds" onClick={() => showNotice(`Deny ${policy.semanticDenyThreshold ?? 'not set'} · Review ${policy.semanticReviewThreshold ?? 'not set'}`)}><SlidersHorizontal size={18} /></button></div></header>
        <div className="page-content"><section className="page-heading"><div><p className="eyebrow">Live operational dashboard</p><h1>{policy.name}</h1><p className="heading-copy">{runtime.total.toLocaleString()} runtime evaluations from the active server store.</p></div><div className="heading-actions"><button className="secondary-button" onClick={() => setFilterOpen((open) => !open)}><Filter size={16} /> Filter view</button><label className="primary-button upload-button"><UploadCloud size={16} /> Validate policy<input type="file" accept=".json,.yaml,.yml" onChange={(event) => handleUpload(event.target.files?.[0])} /></label></div></section>
          {filterOpen && <div className="filter-popover"><strong>Finding status</strong><button onClick={() => { setStatusFilter('all'); setFilterOpen(false) }}>All findings</button><button onClick={() => { setStatusFilter('blocked'); setFilterOpen(false) }}>Observed blocked</button><button onClick={() => { setStatusFilter('review'); setFilterOpen(false) }}>Observed review</button><button onClick={() => { setStatusFilter('allowed'); setFilterOpen(false) }}>Observed allowed</button></div>}
          {(uploadedFile || notice) && <div className="upload-toast"><Check size={16} /><span>{uploadedFile ? <><strong>{uploadedFile}</strong> is ready for server validation.</> : notice}</span><button onClick={() => { setUploadedFile(''); setNotice('') }}><X size={15} /></button></div>}
          <section className="metric-grid">{metricCards.map((metric, index) => <article className={`metric-card ${index === 0 ? 'accent-card' : ''}`} key={metric.label}><MetricTop label={metric.label} icon={metric.icon} tone={metric.tone} /><strong>{metric.value}</strong><div className="metric-footer neutral">{metric.note}</div></article>)}</section>
          <section className="chart-row"><article className="panel volume-panel"><PanelHeading title="Live decision distribution" detail="Counts from the operational store"><span className="data-chip">{runtime.total.toLocaleString()} total</span></PanelHeading><div className="chart large-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={categoryData} margin={{ top: 10, right: 4, left: -22, bottom: 0 }}><CartesianGrid stroke="#ece8df" vertical={false} /><XAxis dataKey="category" axisLine={false} tickLine={false} tick={{ fill: '#8c8980', fontSize: 10 }} interval={0} /><YAxis axisLine={false} tickLine={false} tick={{ fill: '#8c8980', fontSize: 11 }} /><Tooltip contentStyle={{ border: '1px solid #e7e2d8', borderRadius: 8, fontSize: 12 }} /><Bar dataKey="count" fill="#2e8c7b" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div></article><article className="panel evaluation-panel"><PanelHeading title="Live runtime health" detail="Measured from actual requests"><button className="text-button" onClick={() => document.querySelector('.events-panel')?.scrollIntoView({ behavior: 'smooth' })}>View events <ArrowUpRight size={14} /></button></PanelHeading><div className="evaluation-score"><div className="donut"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={[{ value: runtime.total ? runtime.allowed / runtime.total : 0 }, { value: runtime.total ? 1 - runtime.allowed / runtime.total : 1 }]} dataKey="value" innerRadius={47} outerRadius={61} startAngle={90} endAngle={-270} stroke="none"><Cell fill="#2e8c7b" /><Cell fill="#e9eee9" /></Pie></PieChart></ResponsiveContainer><div><strong>{runtime.total ? formatPercent(runtime.allowed / runtime.total) : '—'}</strong><span>allow rate</span></div></div><div className="eval-meta"><strong>{runtime.degraded} degraded checks</strong><span>{runtime.reviewed} reviewed events</span><small><Check size={13} /> Average latency {runtime.averageLatencyMs === null ? '—' : `${runtime.averageLatencyMs.toFixed(1)} ms`}</small></div></div><div className="eval-bars"><ScoreBar label="Allow rate" value={runtime.total ? runtime.allowed / runtime.total : 0} /><ScoreBar label="Review rate" value={runtime.total ? runtime.review / runtime.total : 0} /><ScoreBar label="Block rate" value={runtime.total ? runtime.blocked / runtime.total : 0} /></div></article></section>
          <section className="lower-grid"><article className="panel events-panel"><PanelHeading title="Live runtime events" detail="Recent decisions from the operational store"><button className="text-button" onClick={() => { setQuery(''); setStatusFilter('all') }}>Reset view <ArrowUpRight size={14} /></button></PanelHeading><div className="event-toolbar"><div className="search-box"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search request IDs or reason codes" /></div><div className="filter-pills"><button className={statusFilter === 'all' ? 'selected' : ''} onClick={() => setStatusFilter('all')}>All</button><button className={statusFilter === 'blocked' ? 'selected' : ''} onClick={() => setStatusFilter('blocked')}>Blocked</button><button className={statusFilter === 'review' ? 'selected' : ''} onClick={() => setStatusFilter('review')}>Review</button></div></div><div className="event-table-wrap"><table><thead><tr><th>Request</th><th>Policy / reason</th><th>Required</th><th>Observed</th><th>Latency</th><th /></tr></thead><tbody>{visibleFindings.map((finding) => <tr key={finding.id} onClick={() => setSelectedFinding(finding)}><td><div className="event-copy"><span className="event-id">{finding.id}</span><strong>{finding.createdAt}</strong></div></td><td><span className="policy-name">{finding.policy}</span><span className="table-muted">{finding.reasonCode}</span></td><td><span className="source-tag">{finding.degraded ? 'failed' : 'runtime'}</span></td><td><span className={`status-badge ${statusFromFinding(finding)}`}><i /> {finding.observed}</span></td><td><strong className="score">{finding.latencyMs == null ? '—' : `${finding.latencyMs.toFixed(3)} ms`}</strong></td><td><button className="row-more" title="Review event"><MoreHorizontal size={17} /></button></td></tr>)}</tbody></table>{visibleFindings.length === 0 && <div className="empty-table">No live runtime events match this view.</div>}</div></article><article className="panel policy-panel"><PanelHeading title="Active policy" detail="Loaded from the running backend"><button className="icon-button small" title="Policy details" onClick={() => showNotice(`${policy.rules} rules and ${policy.semanticExamples} semantic examples loaded.`)}><Settings2 size={16} /></button></PanelHeading><div className="policy-score"><div className="policy-ring"><span>{policy.rules + policy.semanticExamples}</span></div><div><strong>{policy.rules + policy.semanticExamples} controls</strong><span>loaded from {data.source.policy}</span></div></div><div className="policy-list">{policyRows.map((row) => <PolicyRow key={row.label} label={row.label} version={row.version} live={row.live} />)}</div><label className="dropzone"><FileUp size={19} /><strong>Validate policy file</strong><span>Local check only; backend activation is not available</span><input type="file" accept=".json,.yaml,.yml" onChange={(event) => handleUpload(event.target.files?.[0])} /></label></article></section>
          <section className="panel settings-panel runtime-panel"><PanelHeading title="Runtime providers & security" detail="Live configuration from the GuardRyle backend"><button className="secondary-button" onClick={() => void refreshRuntime()} disabled={runtimeBusy}><RefreshCw size={14} className={runtimeBusy ? 'spin' : ''} /> Refresh</button></PanelHeading>{runtimeError && <div className="runtime-alert failure"><AlertTriangle size={15} /> {runtimeError}</div>}<div className="runtime-columns"><div><h3><ServerCog size={15} /> Active embedding model</h3><div className="runtime-status-grid"><RuntimeValue label="Configured primary" value={embeddingStatus.configuredModel ?? 'Unavailable'} /><RuntimeValue label="Actually used" value={embeddingStatus.activeModel ?? 'Unavailable'} /><RuntimeValue label="Provider" value={embeddingStatus.activeProvider ?? 'Unavailable'} /><RuntimeValue label="Dimensions" value={embeddingStatus.dimensions?.toString() ?? 'Unavailable'} /><RuntimeValue label="Execution" value={embeddingStatus.execution} /><RuntimeValue label="Provider health" value={embeddingStatus.providerHealth} /></div>{embeddingStatus.degraded && <div className="runtime-alert warning"><AlertTriangle size={15} /> Degraded mode is active. Required security evaluations remain fail-closed.</div>}{embeddingStatus.securityEvaluationRequired && !embeddingStatus.securityEvaluationAvailable && <div className="runtime-alert failure"><LockKeyhole size={15} /> Required security evaluation is unavailable. Protected operations must remain in REVIEW, never approval.</div>}</div><div><h3><KeyRound size={15} /> OpenAI configuration</h3><p className="settings-help">The backend stores the credential. This page never stores it locally, puts it in a URL, or renders it after saving.</p><div className="key-entry"><input aria-label="OpenAI API key" type={showOpenAIKey ? 'text' : 'password'} value={openAIKey} onChange={(event) => setOpenAIKey(event.target.value)} placeholder="Enter key for backend storage" autoComplete="off" /><button className="icon-button" onClick={() => setShowOpenAIKey((visible) => !visible)} title={showOpenAIKey ? 'Hide API key' : 'Show API key'}>{showOpenAIKey ? <EyeOff size={16} /> : <Eye size={16} />}</button><button className="primary-button" onClick={() => void saveOpenAIKey()} disabled={runtimeBusy}><Save size={14} /> Save</button></div><div className="settings-actions"><span className={`configuration-state ${openAIStatus?.configured ? 'configured' : 'not-configured'}`}><i /> {openAIStatus?.configured ? 'Key configured' : 'Key not configured'}</span><button className="secondary-button" onClick={() => void testOpenAIConnection()} disabled={runtimeBusy}>Test connection</button>{openAIStatus?.connection === 'connected' && <span className="connection-ok"><Check size={14} /> Backend confirmed connected</span>}{openAIStatus?.connection === 'failed' && <span className="connection-failed"><AlertTriangle size={14} /> Connection failed</span>}</div></div></div><div className="provider-config"><h3>Supported embedding providers</h3>{providers.length === 0 ? <p className="settings-help">Provider capabilities are unavailable until the backend responds.</p> : <div className="provider-list">{providers.map((provider) => <label key={provider.id} className="provider-option"><input type="radio" name="embedding-provider" checked={provider.id === embeddingStatus.configuredProvider} onChange={() => { const model = provider.supportedModels[0]; if (model) void selectProvider(provider.id, model.id) }} /><span><strong>{provider.label}</strong><small>{provider.execution} · {provider.health}</small><select aria-label={`${provider.label} model`} value={provider.id === embeddingStatus.configuredProvider ? (embeddingStatus.configuredModel ?? '') : (provider.supportedModels[0]?.id ?? '')} onChange={(event) => void selectProvider(provider.id, event.target.value)}>{provider.supportedModels.map((model) => <option key={model.id} value={model.id}>{model.id} ({model.dimensions}d)</option>)}</select></span></label>)}</div>}</div></section>
        </div>
      </main>
      {selectedFinding && <div className="modal-backdrop" onClick={() => setSelectedFinding(null)}><section className="review-modal" onClick={(event) => event.stopPropagation()}><div className="modal-header"><div><span className={`status-badge ${statusFromFinding(selectedFinding)}`}><i /> observed {selectedFinding.observed}</span><h2>Review {selectedFinding.id}</h2></div><button className="icon-button" onClick={() => setSelectedFinding(null)} title="Close review"><X size={18} /></button></div><div className="prompt-preview"><span>Evaluation example</span><p>{selectedFinding.prompt}</p></div><dl className="detail-grid"><div><dt>Policy</dt><dd>{selectedFinding.policy}</dd></div><div><dt>Expected</dt><dd>{selectedFinding.expected}</dd></div><div><dt>Category</dt><dd>{selectedFinding.category}</dd></div><div><dt>Latency</dt><dd>{selectedFinding.latencyMs == null ? 'Not recorded' : `${selectedFinding.latencyMs.toFixed(3)} ms`}</dd></div></dl><div className="modal-actions"><button className="secondary-button" onClick={() => setSelectedFinding(null)}>Close</button><button className="primary-button" onClick={markReviewed}><Check size={16} /> Mark reviewed</button></div></section></div>}
    </div>
  )
}

function MetricTop({ label, icon, tone }: { label: string; icon: ReactNode; tone: string }) { return <div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}>{icon}</span></div> }
function PanelHeading({ title, detail, children }: { title: string; detail: string; children?: ReactNode }) { return <div className="panel-heading"><div><h2>{title}</h2><p>{detail}</p></div>{children}</div> }
function ScoreBar({ label, value }: { label: string; value: number }) { return <div className="eval-bar-row"><span>{label}</span><div className="bar-track"><i style={{ width: `${value * 100}%`, background: '#2e8c7b' }} /></div><strong>{formatPercent(value)}</strong></div> }
function PolicyRow({ label, version, live }: { label: string; version: string; live: boolean }) { return <div><span className={`policy-status ${live ? 'live' : 'warning'}`} /><span>{label}</span><small>{version}</small></div> }
function RuntimeValue({ label, value }: { label: string; value: string }) { return <div className="runtime-value"><span>{label}</span><strong>{value}</strong></div> }

export default App
