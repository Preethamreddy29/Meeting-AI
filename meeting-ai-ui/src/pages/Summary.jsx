import { useEffect, useRef, useState } from "react"
import { api, requestError } from "../api"
import { Sparkles, Loader } from "lucide-react"

export default function Summary() {
  const [meetings, setMeetings]  = useState([])
  const [selected, setSelected]  = useState(null)
  const [summary,  setSummary]   = useState(null)
  const [status,   setStatus]    = useState(null)
  const pollTimer = useRef(null)

  useEffect(() => {
    api.get("/api/meetings")
      .then(r => setMeetings(r.data.meetings))
      .catch((error) => setStatus({ status: "error", message: requestError(error, "Could not load meetings.") }))
    return () => window.clearTimeout(pollTimer.current)
  }, [])

  const load = (id) => {
    setSelected(id)
    setSummary(null)
    setStatus(null)
    api.get(`/api/meetings/${id}/summary`)
      .then(r => setSummary(r.data.summary))
      .catch(() => setSummary(null))
  }

  const generate = async () => {
    if (!selected) return
    window.clearTimeout(pollTimer.current)
    try {
      const r = await api.post(`/api/meetings/${selected}/summarize`)
      const meetingId = selected
      setStatus({ status: "running", message: "Generating summary..." })

      const poll = async () => {
        try {
          const response = await api.get(`/api/jobs/${r.data.job_id}`)
          setStatus(response.data)
          if (["queued", "running"].includes(response.data.status)) {
            pollTimer.current = window.setTimeout(poll, 2000)
          } else if (response.data.status === "done") {
            load(meetingId)
          }
        } catch (error) {
          setStatus({ status: "error", message: requestError(error, "Lost connection while checking summary progress.") })
        }
      }
      poll()
    } catch (error) {
      setStatus({ status: "error", message: requestError(error, "Could not start summary generation.") })
    }
  }

  return (
    <div>
      <div className="page-heading"><div className="page-heading-copy">
        <span className="eyebrow">Step 3 · Understand</span>
        <h1 className="page-title">AI summaries</h1>
        <p className="page-subtitle">Use Gemini to generate a concise summary after the transcript has been reviewed.</p>
      </div></div>
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
                    {["queued", "running"].includes(status.status) && (
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
                      <button className="btn btn-primary" onClick={generate} disabled={["queued", "running"].includes(status?.status)}>
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
                        disabled={["queued", "running"].includes(status?.status)}
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
