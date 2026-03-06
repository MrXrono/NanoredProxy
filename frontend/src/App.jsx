import { useEffect, useMemo, useRef, useState } from 'react'

const API = import.meta.env.VITE_API_URL || '/api/v1'
const WS = import.meta.env.VITE_WS_URL || ((location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/api/v1')

async function api(path, opts = {}, token) {
  const headers = { ...(opts.headers || {}) }
  if (!(opts.body instanceof FormData) && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${API}${path}`, { ...opts, headers })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail || data.error?.message || detail
    } catch {}
    throw new Error(detail)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res.text()
}

function Login({ onLogin }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await api('/admin/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
      onLogin(data.access_token, data.admin)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <h1>NanoredProxy Admin</h1>
        <p>Login to manage proxy pool, sessions, workers and analytics.</p>
        <label>Username<input value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button disabled={loading}>{loading ? 'Signing in...' : 'Sign in'}</button>
      </form>
    </div>
  )
}

function Section({ title, actions, children }) {
  return <section className="card"><div className="section-head"><h3>{title}</h3><div className="actions">{actions}</div></div>{children}</section>
}

function JsonTable({ rows }) {
  if (!rows?.length) return <div className="muted">No data</div>
  const columns = Object.keys(rows[0])
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map(col => <th key={col}>{col}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={row.id || idx}>
              {columns.map(col => <td key={col}>{typeof row[col] === 'object' && row[col] !== null ? JSON.stringify(row[col]) : String(row[col] ?? '')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StatGrid({ summary }) {
  return (
    <div className="grid stats-grid">
      {Object.entries(summary || {}).map(([k, v]) => (
        <div className="card stat-card" key={k}><div className="muted">{k}</div><div className="stat">{String(v)}</div></div>
      ))}
    </div>
  )
}

function Bars({ items, valueKey, labelKey, color = '#38bdf8', formatter = v => v }) {
  if (!items?.length) return <div className="muted">No chart data</div>
  const max = Math.max(...items.map(x => Number(x[valueKey] || 0)), 1)
  return (
    <div className="bars">
      {items.map((item, idx) => {
        const value = Number(item[valueKey] || 0)
        const width = `${Math.max(3, (value / max) * 100)}%`
        return (
          <div className="bar-row" key={`${item[labelKey]}-${idx}`}>
            <div className="bar-label">{item[labelKey]}</div>
            <div className="bar-track"><div className="bar-fill" style={{ width, background: color }} /></div>
            <div className="bar-value">{formatter(value)}</div>
          </div>
        )
      })}
    </div>
  )
}

function formatBytes(v) {
  const n = Number(v || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

function MetricList({ title, items }) {
  return (
    <Section title={title}>
      <div className="metric-list">
        {Object.entries(items || {}).map(([k, v]) => <div key={k}><span className="muted">{k}</span><strong>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</strong></div>)}
      </div>
    </Section>
  )
}

function ratingColor(score) {
  if (score >= 400) return '#22c55e'
  if (score >= 200) return '#f59e0b'
  if (score > 0) return '#ef4444'
  return '#64748b'
}

function statusBadge(status) {
  const colors = { running: '#22c55e', idle: '#64748b', frozen: '#3b82f6', error: '#ef4444', paused: '#f59e0b' }
  return <span style={{ color: colors[status] || '#64748b', fontWeight: 600 }}>{status}</span>
}

function RatingTable({ items, token }) {
  const [filter, setFilter] = useState('')
  const filtered = useMemo(() => {
    if (!filter) return items
    const q = filter.toLowerCase()
    return items.filter(r => r.host.includes(q) || r.country.toLowerCase().includes(q) || r.status.includes(q))
  }, [items, filter])

  return (
    <Section title={`Proxy Rating (${filtered.length})`} actions={<input placeholder="Filter host/country/status..." value={filter} onChange={e => setFilter(e.target.value)} style={{ minWidth: 200 }} />}>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Host</th>
              <th>Status</th>
              <th>Country</th>
              <th style={{ textAlign: 'center' }}>Rating</th>
              <th>Ping ms</th>
              <th>Ping %</th>
              <th>Auth ms</th>
              <th>Auth %</th>
              <th>DL Mbps</th>
              <th>UL Mbps</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={r.id}>
                <td>{i + 1}</td>
                <td>{r.host}:{r.port}</td>
                <td>{r.status}</td>
                <td>{r.country}</td>
                <td style={{ textAlign: 'center' }}>
                  <span style={{
                    display: 'inline-block', minWidth: 44, padding: '2px 8px',
                    borderRadius: 4, background: ratingColor(r.rating), color: '#fff',
                    fontWeight: 700, fontSize: '0.85em', textAlign: 'center',
                  }}>
                    {r.rating}/600
                  </span>
                </td>
                <td>{r.ping_ms != null ? `${r.ping_ms}` : '-'}</td>
                <td>{r.ping_rate != null ? `${r.ping_rate}%` : '-'}</td>
                <td>{r.auth_ms != null ? `${r.auth_ms}` : '-'}</td>
                <td>{r.auth_rate != null ? `${r.auth_rate}%` : '-'}</td>
                <td>{r.download != null ? r.download : '-'}</td>
                <td>{r.upload != null ? r.upload : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function QueueTable({ queueData }) {
  if (!queueData) return <div className="muted">Loading queue data...</div>

  const orch = queueData.orchestrator
  const queue = queueData.queue || []

  const agentLabels = {
    ping_agent: 'Ping Agent',
    auth_agent: 'Auth Agent',
    aggregate_agent: 'Aggregate',
    geo_agent: 'Geo Agent',
    speedtest_agent: 'Speedtest Agent',
    reconcile_agent: 'Reconcile Agent',
  }

  return (
    <>
      {orch && (
        <Section title="Orchestrator">
          <div className="metric-list">
            <div><span className="muted">Status</span><strong>{statusBadge(orch.status)}</strong></div>
            <div><span className="muted">Last started</span><strong>{orch.last_started || '-'}</strong></div>
            <div><span className="muted">Last finished</span><strong>{orch.last_finished || '-'}</strong></div>
            {orch.pause_reason && <div><span className="muted">Reason</span><strong>{orch.pause_reason}</strong></div>}
          </div>
        </Section>
      )}
      <Section title="Agent Queue (by priority)">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Priority</th>
                <th>Agent</th>
                <th>Status</th>
                <th>Last Started</th>
                <th>Last Finished</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {queue.map(q => (
                <tr key={q.agent}>
                  <td style={{ textAlign: 'center', fontWeight: 700 }}>{q.priority}</td>
                  <td>{agentLabels[q.agent] || q.agent}</td>
                  <td>{statusBadge(q.status)}</td>
                  <td>{q.last_started ? q.last_started.replace('T', ' ').slice(0, 19) : '-'}</td>
                  <td>{q.last_finished ? q.last_finished.replace('T', ' ').slice(0, 19) : '-'}</td>
                  <td className="muted">{q.pause_reason || (q.agent === 'speedtest_agent' ? 'yields to higher priority' : '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  )
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('nrp_token') || '')
  const [admin, setAdmin] = useState(null)
  const [tab, setTab] = useState('dashboard')
  const [summary, setSummary] = useState(null)
  const [charts, setCharts] = useState(null)
  const [stats, setStats] = useState({ countries: [], accounts: [], top: [], worst: [], ab: {} })
  const [proxies, setProxies] = useState([])
  const [accounts, setAccounts] = useState([])
  const [sessions, setSessions] = useState([])
  const [workers, setWorkers] = useState([])
  const [settings, setSettings] = useState({})
  const [audit, setAudit] = useState([])
  const [events, setEvents] = useState([])
  const [proxyImportText, setProxyImportText] = useState('')
  const [configPreview, setConfigPreview] = useState('')
  const [message, setMessage] = useState('')
  const [chartPeriod, setChartPeriod] = useState('24h')
  const [selectedProxy, setSelectedProxy] = useState(null)
  const [proxyDetails, setProxyDetails] = useState(null)
  const [proxyChecks, setProxyChecks] = useState([])
  const [proxySpeedtests, setProxySpeedtests] = useState([])
  const [proxyGeoAttempts, setProxyGeoAttempts] = useState([])
  const [proxyRoutingUsage, setProxyRoutingUsage] = useState(null)
  const [selectedSession, setSelectedSession] = useState(null)
  const [sessionDetails, setSessionDetails] = useState(null)
  const [sessionConnections, setSessionConnections] = useState([])
  const [sessionRoutingEvents, setSessionRoutingEvents] = useState([])
  const [ratingData, setRatingData] = useState([])
  const [queueData, setQueueData] = useState(null)
  const wsRef = useRef(null)
  const reloadTimer = useRef(null)
  const tabs = useMemo(() => ['dashboard','stats','rating','proxies','accounts','sessions','workers','settings','config','audit','events'], [])

  function handleLogin(nextToken, nextAdmin) {
    localStorage.setItem('nrp_token', nextToken)
    setToken(nextToken)
    setAdmin(nextAdmin)
  }

  function logout() {
    localStorage.removeItem('nrp_token')
    setToken('')
    setAdmin(null)
    if (wsRef.current) wsRef.current.close()
  }

  async function loadAll(selectedPeriod = chartPeriod) {
    const [summaryData, chartsData, proxyData, accountData, sessionData, workerData, settingsData, configData, auditData, meData, countriesData, accountStatsData, topData, worstData, abData, ratingResp, queueResp] = await Promise.all([
      api('/dashboard/summary', {}, token),
      api(`/dashboard/charts?period=${encodeURIComponent(selectedPeriod)}`, {}, token),
      api('/proxies', {}, token),
      api('/accounts', {}, token),
      api('/sessions', {}, token),
      api('/system/workers', {}, token),
      api('/system/settings', {}, token),
      api('/config/proxychains/preview', {}, token),
      api('/audit/logs', {}, token),
      api('/admin/auth/me', {}, token),
      api('/stats/countries', {}, token),
      api('/stats/accounts', {}, token),
      api('/stats/proxies/top', {}, token),
      api('/stats/proxies/worst', {}, token),
      api('/stats/ab', {}, token),
      api('/stats/rating', {}, token),
      api('/system/workers/queue', {}, token),
    ])
    setSummary(summaryData)
    setCharts(chartsData)
    setProxies(proxyData.items || [])
    setAccounts(accountData.items || [])
    setSessions(sessionData.items || [])
    setWorkers(workerData.items || [])
    setSettings(settingsData || {})
    setConfigPreview(configData.content || '')
    setAudit(auditData.items || [])
    setAdmin(meData)
    setStats({ countries: countriesData.items || [], accounts: accountStatsData.items || [], top: topData.items || [], worst: worstData.items || [], ab: abData || {} })
    setRatingData(ratingResp.items || [])
    setQueueData(queueResp)
  }

  async function loadProxyDetails(id) {
    const [detail, checks, speedtests, geo, usage] = await Promise.all([
      api(`/proxies/${id}`, {}, token),
      api(`/proxies/${id}/checks`, {}, token),
      api(`/proxies/${id}/speedtests`, {}, token),
      api(`/proxies/${id}/geo-attempts`, {}, token),
      api(`/proxies/${id}/routing-usage`, {}, token),
    ])
    setSelectedProxy(id)
    setProxyDetails(detail)
    setProxyChecks(checks.items || [])
    setProxySpeedtests(speedtests.items || [])
    setProxyGeoAttempts(geo.items || [])
    setProxyRoutingUsage(usage)
  }

  async function loadSessionDetails(id) {
    const [detail, connections, events] = await Promise.all([
      api(`/sessions/${id}`, {}, token),
      api(`/sessions/${id}/connections`, {}, token),
      api(`/sessions/${id}/routing-events`, {}, token),
    ])
    setSelectedSession(id)
    setSessionDetails(detail)
    setSessionConnections(connections.items || [])
    setSessionRoutingEvents(events.items || [])
  }

  function scheduleReload() {
    if (reloadTimer.current) return
    reloadTimer.current = setTimeout(async () => {
      reloadTimer.current = null
      try { await loadAll() } catch {}
      try { if (selectedProxy) await loadProxyDetails(selectedProxy) } catch {}
      try { if (selectedSession) await loadSessionDetails(selectedSession) } catch {}
    }, 800)
  }

  useEffect(() => {
    if (!token) return
    loadAll().catch(err => {
      setMessage(err.message)
      if ((err.message || '').toLowerCase().includes('token')) logout()
    })
  }, [token])

  useEffect(() => {
    if (!token) return
    const ws = new WebSocket(`${WS}/ws/events?token=${encodeURIComponent(token)}`)
    wsRef.current = ws
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data)
        setEvents(prev => [data, ...prev].slice(0, 100))
        if (!String(data.type || '').startsWith('system.heartbeat')) scheduleReload()
      } catch {}
    }
    return () => ws.close()
  }, [token, selectedProxy, selectedSession])

  async function importProxies() {
    setMessage('')
    try {
      const res = await api('/proxies/import/text', { method: 'POST', body: JSON.stringify({ text: proxyImportText }) }, token)
      setMessage(`Imported: ${res.inserted}, duplicates: ${res.duplicates}`)
      setProxyImportText('')
      await loadAll()
    } catch (err) {
      setMessage(err.message)
    }
  }

  async function saveSettings() {
    await api('/system/settings', { method: 'PATCH', body: JSON.stringify(settings) }, token)
    setMessage('Settings saved')
    await loadAll()
  }

  async function reconcileAccounts() { await api('/accounts/reconcile', { method: 'POST' }, token); await loadAll() }
  async function killSession(id) { await api(`/sessions/${id}/kill`, { method: 'POST', body: JSON.stringify({ reason: 'manual kill from UI' }) }, token); await loadAll(); if (selectedSession === id) await loadSessionDetails(id) }
  async function workerAction(name, action) { await api(`/system/workers/${name}/${action}`, { method: 'POST' }, token); await loadAll() }
  async function toggleProxy(id, enabled) { await api(`/proxies/${id}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' }, token); await loadAll(); if (selectedProxy === id) await loadProxyDetails(id) }
  async function quarantineProxy(id, enabled) { await api(`/proxies/${id}/${enabled ? 'quarantine' : 'unquarantine'}`, { method: 'POST' }, token); await loadAll(); if (selectedProxy === id) await loadProxyDetails(id) }
  async function recheckProxy(id) { await api(`/proxies/${id}/recheck`, { method: 'POST' }, token); await loadAll(); if (selectedProxy === id) await loadProxyDetails(id) }
  async function setCountry(id, current) {
    const value = prompt('Country code', current || '')
    if (value === null) return
    if (!value.trim()) {
      await api(`/proxies/${id}/clear-country`, { method: 'POST' }, token)
    } else {
      await api(`/proxies/${id}/set-country`, { method: 'POST', body: JSON.stringify({ country_code: value.trim().toLowerCase() }) }, token)
    }
    await loadAll()
    if (selectedProxy === id) await loadProxyDetails(id)
  }

  if (!token) return <Login onLogin={handleLogin} />

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>NanoredProxy Admin</h1>
          <div className="muted">Logged in as {admin?.username || 'admin'}</div>
        </div>
        <div className="actions">
          <button onClick={() => loadAll()}>Refresh</button>
          <button className="secondary" onClick={logout}>Logout</button>
        </div>
      </header>

      <nav className="tabs">
        {tabs.map(name => <button key={name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>{name}</button>)}
      </nav>

      {message && <div className="flash">{message}</div>}

      {tab === 'dashboard' && <>
        <StatGrid summary={summary} />
        <div className="grid cols-2">
          <Section title="Traffic by bucket" actions={<select value={chartPeriod} onChange={async e => { setChartPeriod(e.target.value); await loadAll(e.target.value) }}><option value="24h">24h</option><option value="7d">7d</option><option value="30d">30d</option></select>}>
            <Bars items={charts?.traffic_by_bucket || []} valueKey="total_bytes" labelKey="bucket_start" color="#22c55e" formatter={formatBytes} />
          </Section>
          <Section title="Country distribution">
            <Bars items={charts?.country_distribution || []} valueKey="working_proxies" labelKey="country_code" color="#a78bfa" formatter={v => `${v} proxies`} />
          </Section>
          <Section title="Latency top">
            <Bars items={charts?.latency_top || []} valueKey="avg_latency_day_ms" labelKey="host" color="#f59e0b" formatter={v => `${v.toFixed ? v.toFixed(1) : v} ms`} />
          </Section>
          <Section title="Speed top">
            <Bars items={charts?.speed_top || []} valueKey="avg_download_day_mbps" labelKey="host" color="#38bdf8" formatter={v => `${v.toFixed ? v.toFixed(1) : v} Mbps`} />
          </Section>
        </div>
      </>}

      {tab === 'stats' && <div className="grid cols-2">
        <Section title="Countries"><JsonTable rows={stats.countries} /></Section>
        <Section title="Accounts"><JsonTable rows={stats.accounts} /></Section>
        <Section title="Top proxies"><JsonTable rows={stats.top} /></Section>
        <Section title="Worst proxies"><JsonTable rows={stats.worst} /></Section>
        <MetricList title="A/B routing" items={stats.ab} />
      </div>}

      {tab === 'rating' && <>
        <RatingTable items={ratingData} token={token} />
        <QueueTable queueData={queueData} />
      </>}

      {tab === 'proxies' && <div className="grid cols-2">
        <Section title="Import proxies" actions={<button onClick={importProxies}>Import</button>}>
          <textarea rows="10" value={proxyImportText} onChange={e => setProxyImportText(e.target.value)} placeholder="ip:port or user:pass@ip:port" />
        </Section>
        <Section title="Proxy pool">
          <div className="table-wrap">
            <table>
              <thead><tr><th>id</th><th>host</th><th>status</th><th>country</th><th>rating</th><th>actions</th></tr></thead>
              <tbody>
                {proxies.map(p => <tr key={p.id} className={selectedProxy === p.id ? 'selected-row' : ''}><td>{p.id}</td><td>{p.host}:{p.port}</td><td>{p.status}</td><td>{p.country_code || '-'}</td><td><span style={{ color: ratingColor(p.rating_score || 0), fontWeight: 700 }}>{p.rating_score || 0}</span></td><td className="actions wrap"><button onClick={() => loadProxyDetails(p.id)}>details</button><button onClick={() => toggleProxy(p.id, !p.is_enabled)}>{p.is_enabled ? 'disable' : 'enable'}</button><button onClick={() => quarantineProxy(p.id, !p.is_quarantined)}>{p.is_quarantined ? 'unquarantine' : 'quarantine'}</button><button onClick={() => setCountry(p.id, p.country_code)}>country</button><button onClick={() => recheckProxy(p.id)}>recheck</button></td></tr>)}
              </tbody>
            </table>
          </div>
        </Section>
        <Section title="Proxy details">
          {proxyDetails ? <>
            <MetricList title="Selected proxy" items={proxyDetails} />
            <Section title="Availability checks"><JsonTable rows={proxyChecks} /></Section>
            <Section title="Speedtests"><JsonTable rows={proxySpeedtests} /></Section>
            <Section title="Geo attempts"><JsonTable rows={proxyGeoAttempts} /></Section>
            <Section title="Routing usage"><JsonTable rows={proxyRoutingUsage?.recent_events || []} /></Section>
          </> : <div className="muted">Select a proxy to inspect details.</div>}
        </Section>
      </div>}

      {tab === 'accounts' && <Section title="Accounts" actions={<button onClick={reconcileAccounts}>Reconcile</button>}><JsonTable rows={accounts} /></Section>}

      {tab === 'sessions' && <div className="grid cols-2">
        <Section title="Sessions">
          <div className="table-wrap">
            <table>
              <thead><tr><th>id</th><th>login</th><th>status</th><th>proxy</th><th>traffic</th><th>actions</th></tr></thead>
              <tbody>
                {sessions.map(s => <tr key={s.id} className={selectedSession === s.id ? 'selected-row' : ''}><td>{s.id.slice(0, 8)}</td><td>{s.client_login}</td><td>{s.status}</td><td>{s.assigned_proxy_id || '-'}</td><td>{formatBytes(s.total_bytes)}</td><td className="actions wrap"><button onClick={() => loadSessionDetails(s.id)}>details</button><button onClick={() => killSession(s.id)}>kill</button></td></tr>)}
              </tbody>
            </table>
          </div>
        </Section>
        <Section title="Session details">
          {sessionDetails ? <>
            <MetricList title="Selected session" items={sessionDetails} />
            <Section title="Connections"><JsonTable rows={sessionConnections} /></Section>
            <Section title="Routing events"><JsonTable rows={sessionRoutingEvents} /></Section>
          </> : <div className="muted">Select a session to inspect details.</div>}
        </Section>
      </div>}

      {tab === 'workers' && <Section title="Workers"><div className="table-wrap"><table><thead><tr><th>worker</th><th>status</th><th>last_started_at</th><th>pause_reason</th><th>actions</th></tr></thead><tbody>{workers.map(w => <tr key={w.worker_name}><td>{w.worker_name}</td><td>{w.status}</td><td>{w.last_started_at || '-'}</td><td>{w.pause_reason || '-'}</td><td className="actions wrap"><button onClick={() => workerAction(w.worker_name, 'run-now')}>run</button><button onClick={() => workerAction(w.worker_name, 'pause')}>pause</button><button onClick={() => workerAction(w.worker_name, 'resume')}>resume</button></td></tr>)}</tbody></table></div></Section>}

      {tab === 'settings' && <Section title="Settings" actions={<button onClick={saveSettings}>Save</button>}>
        <div className="settings-grid">
          {Object.entries(settings).map(([key, value]) => <label key={key}><span>{key}</span><textarea rows="3" value={typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)} onChange={e => {
            const raw = e.target.value
            setSettings(prev => {
              const next = { ...prev }
              try { next[key] = JSON.parse(raw) } catch { next[key] = raw }
              return next
            })
          }} /></label>)}
        </div>
      </Section>}

      {tab === 'config' && <Section title="proxychains config" actions={<button onClick={() => navigator.clipboard.writeText(configPreview)}>Copy</button>}><textarea rows="24" value={configPreview} readOnly /></Section>}

      {tab === 'audit' && <Section title="Audit log"><JsonTable rows={audit} /></Section>}

      {tab === 'events' && <Section title="Realtime events"><JsonTable rows={events} /></Section>}
    </div>
  )
}
