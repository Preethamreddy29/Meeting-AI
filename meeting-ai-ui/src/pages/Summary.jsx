import { useEffect, useState } from "react"
import axios from "axios"
import { Sparkles, Loader } from "lucide-react"

export default function Summary() {
  const [meetings, setMeetings]  = useState([])
  const [selected, setSelected]  = useState(null)
  const [summary,  setSummary]   = useState(null)
  const [jobId,    setJobId]     = useState(null)
  const [status,   setStatus]    = useState(null)

  useEffect(() => {
    axios.get("http://localhost:8000/api/meetings")
      .then(r => setMeetings(r.data.meetings))
  }, [])

  const load = (id) => {
    setSelected(id)
    setSummary(null)
    axios.get(`http://localhost:8000/api/meetings/${id}/summary`)
      .then(r => setSummary(r.data.summary))
      .catch(() => setSummary(null))
  }

  const generate = async () => {
    if (!selected) return
    const r = await axios.post(
      `http://localhost:8000/api/meetings/${selected}/summarize`
    )
    setJobId(r.data.job_id)
    setStatus({ status: "running", message: "Generating summary..." })

    const interval = setInterval(() => {
      axios.get(`http://localhost:8000/api/jobs/${r.data.job_id}`)
        .then(j => {
          setStatus(j.data)
          if (j.data.status !== "running") {
            clearInterval(interval)
            if (j.data.status === "done") load(selected)
          }
        })
    }, 2000)
  }

  return (
    <div>
      <h1 className="page-title">Meeting Summary</h1>
      <div className="grid-2" style={{alignItems:"start"}}>
        <div className="card">
          <h3 style={{marginBottom:16}}>Select Meeting</h3>
          {meetings.map(m => (
            <div
              key={m.id}
              onClick={() => load(m.id)}
              style={{
                padding:"12px",
                borderRadius:"8px",
                cursor:"pointer",
                background: selected === m.id ? "#1e1b4b" : "transparent",
                border:`1px solid ${selected===m.id?"#4f46e5":"#2d3748"}`,
                marginBottom:"10px",
              }}
            >
              <div style={{fontWeight:600,fontSize:14}}>
                #{m.id} — {m.filename}
              </div>
              <div style={{fontSize:12,color:"#64748b",marginTop:4}}>
                {m.summary_path ? "✅ Summary ready" : "⏳ No summary yet"}
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          {!selected
            ? <p style={{color:"#64748b",fontSize:14}}>
                Select a meeting to view or generate its summary.
              </p>
            : (
              <>
                {status && (
                  <div className={`status-bar status-${status.status}`}
                    style={{marginBottom:16}}>
                    {status.status === "running" && (
                      <Loader size={14} style={{
                        display:"inline",marginRight:8,
                        animation:"spin 1s linear infinite"
                      }}/>
                    )}
                    {status.message}
                  </div>
                )}
                {!summary
                  ? (
                    <div style={{textAlign:"center",padding:"32px 0"}}>
                      <p style={{color:"#64748b",fontSize:14,marginBottom:20}}>
                        No summary generated yet for this meeting.
                      </p>
                      <button className="btn btn-primary" onClick={generate}>
                        <Sparkles size={16} />
                        Generate Summary
                      </button>
                    </div>
                  )
                  : (
                    <>
                      <div style={{
                        whiteSpace:"pre-wrap",
                        fontSize:13,
                        lineHeight:1.7,
                        color:"#cbd5e1",
                        maxHeight:"65vh",
                        overflowY:"auto",
                      }}>
                        {summary}
                      </div>
                      <button
                        className="btn btn-ghost"
                        onClick={generate}
                        style={{marginTop:16}}
                      >
                        Regenerate
                      </button>
                    </>
                  )
                }
              </>
            )
          }
        </div>
      </div>
      <style>{`@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}