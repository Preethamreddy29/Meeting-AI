import { useEffect, useState } from "react"
import axios from "axios"

export default function Dashboard() {
  const [data, setData] = useState(null)

  useEffect(() => {
    axios.get("http://localhost:8000/api/dashboard")
      .then(r => setData(r.data))
      .catch(() => {})
  }, [])

  if (!data) return <p style={{color:"#64748b"}}>Loading...</p>

  const { stats, recent_meetings } = data

  return (
    <div>
      <h1 className="page-title">Dashboard</h1>

      <div className="grid-4" style={{marginBottom:24}}>
        {[
          { label: "Enrolled Speakers", value: stats.total_speakers },
          { label: "Meetings Processed", value: stats.total_meetings },
          { label: "Total Segments",    value: stats.total_segments  },
          { label: "Unknown Segments",  value: stats.unknown_segments},
        ].map(s => (
          <div className="card" key={s.label}>
            <h3>{s.label}</h3>
            <div className="stat">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <h3 style={{marginBottom:16}}>Recent Meetings</h3>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th><th>File</th><th>Processed</th>
              <th>Speakers</th><th>Duration</th>
            </tr>
          </thead>
          <tbody>
            {recent_meetings.map(m => (
              <tr key={m.id}>
                <td>#{m.id}</td>
                <td>{m.filename}</td>
                <td>{m.processed_at?.slice(0,10)}</td>
                <td>{m.num_speakers ?? "—"}</td>
                <td>{m.duration_sec ? `${Math.round(m.duration_sec)}s` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}