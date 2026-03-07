import { useEffect, useState } from 'react'

const cards = [
  ['Backend', 'FastAPI'],
  ['Gateway', 'SOCKS5 frontend'],
  ['Workers', 'availability / speedtest / geo / aggregate / reconcile'],
  ['Storage', 'PostgreSQL + Redis']
]

export default function App() {
  const [summary, setSummary] = useState(null)

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/dashboard/summary').then(r => r.json()).then(setSummary).catch(() => setSummary({ error: true }))
  }, [])

  return (
    <div className="app">
      <h1>NanoredProxy Admin</h1>
      <p>Containerized SOCKS5 proxy pool manager.</p>
      <div className="grid">
        {cards.map(([k, v]) => <div className="card" key={k}><h3>{k}</h3><p>{v}</p></div>)}
      </div>
      <div className="card">
        <h3>Dashboard summary</h3>
        <pre>{JSON.stringify(summary, null, 2)}</pre>
      </div>
    </div>
  )
}
