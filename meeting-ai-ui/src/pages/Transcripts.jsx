import { useEffect, useState } from "react"
import axios from "axios"

export default function Transcripts() {
  const [meetings,   setMeetings]   = useState([])
  const [selected,   setSelected]   = useState(null)
  const [transcript, setTranscript] = useState(null)

  useEffect(() => {
    axios.get("http://localhost:8000/api/meetings")
      .then(r => setMeetings(r.data.meetings))
  }, [])

  const load = (id) => {
    setSelected(id)
    axios.get(`http://localhost:8000/api/meetings/${id}/transcript`)
      .then(r => setTranscript(r.data))
  }

  const fmt = (s) => {
    s = Math.round(s)
    return `${String(Math.floor(s/3600)).padStart(2,"0")}:${String(Math.floor((s%3600)/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`
  }

  const badgeClass = (tier) => {
    if (tier === "high")   return "badge badge-high"
    if (tier === "medium") return "badge badge-medium"
    return "badge badge-low"
  }

  return (
    <div>
      <h1 className="page-title">Transcripts</h1>
      <div className="grid-2" style={{alignItems:"start"}}>
        <div className="card">
          <h3 style={{marginBottom:16}}>Select Meeting</h3>
          {meetings.length === 0
            ? <p style={{color:"#64748b",fontSize:14}}>No meetings yet.</p>
            : meetings.map(m => (
              <div
                key={m.id}
                onClick={() => load(m.id)}
                style={{
                  padding:"12px",
                  borderRadius:"8px",
                  cursor:"pointer",
                  background: selected === m.id ? "#1e1b4b" : "transparent",
                  border: `1px solid ${selected === m.id ? "#4f46e5" : "#2d3748"}`,
                  marginBottom:"10px",
                }}
              >
                <div style={{fontWeight:600,fontSize:14}}>
                  #{m.id} — {m.filename}
                </div>
                <div style={{fontSize:12,color:"#64748b",marginTop:4}}>
                  {m.processed_at?.slice(0,10)} · {m.num_speakers} speakers
                </div>
              </div>
            ))
          }
        </div>

        <div className="card" style={{maxHeight:"75vh",overflowY:"auto"}}>
          {!transcript
            ? <p style={{color:"#64748b",fontSize:14}}>
                Select a meeting to view its transcript.
              </p>
            : (
              <>
                <h3 style={{marginBottom:16}}>
                  {transcript.meeting.filename}
                </h3>
                {transcript.segments.map((seg, i) => (
                  <div className="transcript-line" key={i}>
                    <span className="ts">{fmt(seg.start_time)}</span>
                    <span className="name">
                      {seg.speaker_name || "UNKNOWN"}
                      {seg.tier && (
                        <span
                          className={badgeClass(seg.tier)}
                          style={{marginLeft:6,fontSize:10}}
                        >
                          {seg.tier}
                        </span>
                      )}
                    </span>
                    <span className="text">{seg.transcript_text}</span>
                  </div>
                ))}
              </>
            )
          }
        </div>
      </div>
    </div>
  )
}