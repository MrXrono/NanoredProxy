import { useEffect, useMemo, useRef, useState } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
const WS = import.meta.env.VITE_WS_URL || API.replace(/^http/, 'ws')

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
        <p>Login to manage proxy pool, accounts, sessions, charts and workers.</p>
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
  const wsRef = useRef(null)
  const reloadTimer = useRef(null)
  const tabs = useMemo(() => ['dashboard','stats','proxies','accounts','sessions','workers','settings','config','audit','events'], [])

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
    const [summaryData, chartsData, proxyData, accountData, sessionData, workerData, settingsData, configData, auditData, meData, countriesData, accountStatsData, topData, worstData, abData] = await Promise.all([
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
  }

  function scheduleReload() {
    if (reloadTimer.current) return
    reloadTimer.current = setTimeout(async () => {
      reloadTimer.current = null
      try { await loadAll() } catch {}
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
  }, [token])

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

  async function reconcileAccounts() { await api('/accounts/reconcile', { method: 'POST' }, token); await loadAll() }
  async function killSession(id) { await api(`/sessions/${id}/kill`, { method: 'POST', body: JSON.stringify({ reason: 'manual kill from UI' }) }, token); await loadAll() }
  async function workerAction(name, action) { await api(`/system/workers/${name}/${action}`, { method: 'POST' }, token); await loadAll() }
  async function toggleProxy(id, enabled) { await api(`/proxies/${id}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' }, token); await loadAll() }
  async function quarantineProxy(id, enabled) { await api(`/proxies/${id}/${enabled ? 'quarantine' : 'unquarantine'}`, { method: 'POST' }, token); await loadAll() }
  async function recheckProxy(id) { await api(`/proxies/${id}/recheck`, { method: 'POST' }, token); await loadAll() }
  async function setCountry(id, current) {
    const value = prompt('Country code', current || '')
    if (value === null) return
    if (!value.trim()) {
      await api(`/proxies/${id}/clear-country`, { method: 'POST' }, token)
    } else {
      await api(`/proxies/${id}/set-country`, { method: 'POST', body: JSON.stringify({ country_code: value.trim().toLowerCase() }) }, token)
    }
    await loadAll()
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

      {message && <div className="card message">{message}</div>}

      {tab === 'dashboard' && summary && (
        <>
          <StatGrid summary={summary} />
          <Section title="Traffic charts" actions={<div className="actions"><button className={chartPeriod==='24h'?'active':''} onClick={() => { setChartPeriod('24h'); loadAll('24h') }}>24h</button><button className={chartPeriod==='7d'?'active':''} onClick={() => { setChartPeriod('7d'); loadAll('7d') }}>7d</button><button className={chartPeriod==='30d'?'active':''} onClick={() => { setChartPeriod('30d'); loadAll('30d') }}>30d</button></div>}>
            <div className="grid two-col">
              <div>
                <h4>Traffic by bucket</h4>
                <Bars items={(charts?.traffic_by_bucket || []).slice(-12)} valueKey="total_bytes" labelKey="bucket_start" formatter={formatBytes} />
              </div>
              <div>
                <h4>Country distribution</h4>
                <Bars items={(charts?.country_distribution || []).slice(0, 10)} valueKey="working_proxies" labelKey="country_code" color="#22c55e" />
              </div>
            </div>
          </Section>
          <Section title="Best latency proxies"><JsonTable rows={charts?.latency_top || []} /></Section>
          <Section title="Top daily speed proxies"><JsonTable rows={charts?.speed_top || []} /></Section>
        </>
      )}

      {tab === 'stats' && (
        <>
          <Section title="Countries"><JsonTable rows={stats.countries} /></Section>
          <Section title="Account statistics"><JsonTable rows={stats.accounts} /></Section>
          <div className="grid two-col">
            <Section title="Top proxies"><JsonTable rows={stats.top} /></Section>
            <Section title="Worst proxies"><JsonTable rows={stats.worst} /></Section>
          </div>
          <Section title="A/B routing"><pre>{JSON.stringify(stats.ab, null, 2)}</pre></Section>
        </>
      )}

      {tab === 'proxies' && (
        <>
          <Section title="Import proxies" actions={<button onClick={importProxies}>Import</button>}>
            <textarea rows="8" value={proxyImportText} onChange={e => setProxyImportText(e.target.value)} placeholder="1.2.3.4:1080
user:pass@5.6.7.8:1080" />
          </Section>
          <Section title={`Proxy pool (${proxies.length})`}>
            <div className="table-wrap">
              <table>
                <thead><tr><th>id</th><th>host</th><th>port</th><th>status</th><th>country</th><th>score</th><th>stability</th><th>latency</th><th>actions</th></tr></thead>
                <tbody>
                  {proxies.map(p => (
                    <tr key={p.id}>
                      <td>{p.id}</td>
                      <td>{p.host}</td>
                      <td>{p.port}</td>
                      <td>{p.status}{p.is_quarantined ? ' / quarantine' : ''}</td>
                      <td>{p.country_code || '-'}</td>
                      <td>{p.composite_score ?? '-'}</td>
                      <td>{p.stability_score ?? '-'}</td>
                      <td>{p.avg_latency_day_ms ?? '-'}</td>
                      <td className="actions stack-actions">
                        <button onClick={() => toggleProxy(p.id, !p.is_enabled)}>{p.is_enabled ? 'Disable' : 'Enable'}</button>
                        <button onClick={() => quarantineProxy(p.id, !p.is_quarantined)}>{p.is_quarantined ? 'Unquarantine' : 'Quarantine'}</button>
                        <button onClick={() => setCountry(p.id, p.country_code)}>Country</button>
                        <button onClick={() => recheckProxy(p.id)}>Recheck</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </>
      )}

      {tab === 'accounts' && <Section title="Accounts" actions={<button onClick={reconcileAccounts}>Reconcile</button>}><JsonTable rows={accounts} /></Section>}

      {tab === 'sessions' && (
        <Section title="Sessions">
          <div className="table-wrap"><table><thead><tr><th>id</th><th>login</th><th>client_ip</th><th>proxy</th><th>status</th><th>connections</th><th>traffic</th><th>actions</th></tr></thead><tbody>
            {sessions.map(s => <tr key={s.id}><td>{s.id}</td><td>{s.client_login}</td><td>{s.client_ip}</td><td>{s.assigned_proxy_id ?? '-'}</td><td>{s.status}</td><td>{s.active_connections_count}/{s.connections_count}</td><td>{formatBytes(s.total_bytes)}</td><td><button onClick={() => killSession(s.id)}>Kill</button></td></tr>)}
          </tbody></table></div>
        </Section>
      )}

      {tab === 'workers' && (
        <Section title="Workers">
          <div className="table-wrap"><table><thead><tr><th>worker</th><th>status</th><th>last_started_at</th><th>last_finished_at</th><th>pause_reason</th><th>actions</th></tr></thead><tbody>
            {workers.map(w => <tr key={w.worker_name}><td>{w.worker_name}</td><td>{w.status}</td><td>{w.last_started_at || '-'}</td><td>{w.last_finished_at || '-'}</td><td>{w.pause_reason || '-'}</td><td className="actions"><button onClick={() => workerAction(w.worker_name, 'run-now')}>Run</button><button onClick={() => workerAction(w.worker_name, 'pause')}>Pause</button><button onClick={() => workerAction(w.worker_name, 'resume')}>Resume</button></td></tr>)}
          </tbody></table></div>
        </Section>
      )}

      {tab === 'settings' && <Section title="Runtime settings"><pre>{JSON.stringify(settings, null, 2)}</pre></Section>}
      {tab === 'config' && <Section title="Unified proxychains config" actions={<button onClick={() => navigator.clipboard.writeText(configPreview)}>Copy</button>}><pre>{configPreview}</pre></Section>}
      {tab === 'audit' && <Section title="Audit logs"><JsonTable rows={audit} /></Section>}
      {tab === 'events' && <Section title="Realtime events"><JsonTable rows={events} /></Section>}
    </div>
  )
}
