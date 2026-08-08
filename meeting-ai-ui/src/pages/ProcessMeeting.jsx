import { useState, useRef } from "react"
import axios from "axios"
import { Upload, Loader, CheckCircle, Users } from "lucide-react"

const STEPS = [
  "Converting audio",
  "Transcribing (Whisper)",
  "Detecting speakers (pyannote)",
  "Identifying speakers (ECAPA)",
  "Building named transcript",
  "Complete",
]

export default function ProcessMeeting() {
  const [file,   setFile]   = useState(null)
  const [jobId,  setJobId]  = useState(null)
  const [status, setStatus] = useState(null)
  const [drag,   setDrag]   = useState(false)
  const ref = useRef()

  const poll = (id) => {
    const interval = setInterval(() => {
      axios.get(`http://localhost:8000/api/jobs/${id}`)
        .then(r => {
          setStatus(r.data)
          if (r.data.status !== "running") clearInterval(interval)
        })
    }, 2000)
  }

  const upload = async (f) => {
    if (!f) return
    const fd = new FormData()
    fd.append("file", f)
    const r = await axios.post(
      "http://localhost:8000/api/meetings/upload", fd
    )
    setJobId(r.data.job_id)
    setStatus({ status: "running", message: "Starting...", step: 0, total: 6 })
    poll(r.data.job_id)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDrag(false)
    const f = e.dataTransfer.files[0]
    if (f) { setFile(f); upload(f) }
  }

  const reset = () => {
    setFile(null)
    setJobId(null)
    setStatus(null)
  }

  return (
    <div>
      <h1 className="page-title">Process Meeting</h1>
      <div className="card">

        {/* Upload zone — hide when processing */}
        {!status && (
          <div
            className={`upload-zone ${drag ? "active" : ""}`}
            onDragOver={e => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            onClick={() => ref.current.click()}
          >
            <Upload
              size={32}
              style={{ margin: "0 auto 12px", display: "block" }}
            />
            <p style={{ fontSize: 15, marginBottom: 6 }}>
              Drop your meeting recording here
            </p>
            <p style={{ fontSize: 13 }}>
              MP3, MP4, WAV, M4A supported
            </p>
            <input
              ref={ref}
              type="file"
              accept=".mp3,.mp4,.wav,.m4a,.ogg"
              style={{ display: "none" }}
              onChange={e => {
                const f = e.target.files[0]
                if (f) { setFile(f); upload(f) }
              }}
            />
          </div>
        )}

        {file && (
          <p style={{ marginTop: 12, fontSize: 14, color: "#64748b" }}>
            File: {file.name}
          </p>
        )}

        {/* Step progress */}
        {status && status.status === "running" && (
          <div style={{ marginTop: 20 }}>
            <div style={{
              fontSize: 14,
              color: "#93c5fd",
              marginBottom: 16,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}>
              <Loader
                size={16}
                style={{ animation: "spin 1s linear infinite" }}
              />
              {status.message}
            </div>

            {STEPS.map((label, i) => {
              const stepNum    = i + 1
              const done       = stepNum < (status.step || 0)
              const current    = stepNum === (status.step || 0)
              const upcoming   = stepNum > (status.step || 0)
              return (
                <div
                  key={i}
                  style={{
                    display:      "flex",
                    alignItems:   "center",
                    gap:          10,
                    padding:      "8px 0",
                    borderBottom: "1px solid #1e2535",
                    opacity:      upcoming ? 0.35 : 1,
                  }}
                >
                  <div style={{
                    width:        24,
                    height:       24,
                    borderRadius: "50%",
                    background:   done    ? "#052e16"
                                : current ? "#1e2d40"
                                : "#1a1f2e",
                    border:       `2px solid ${
                                    done    ? "#166534"
                                  : current ? "#1d4ed8"
                                  : "#374151"
                                }`,
                    display:      "flex",
                    alignItems:   "center",
                    justifyContent: "center",
                    fontSize:     11,
                    flexShrink:   0,
                    color:        done ? "#86efac" : current ? "#93c5fd" : "#64748b",
                  }}>
                    {done ? "✓" : stepNum}
                  </div>
                  <span style={{
                    fontSize: 14,
                    color:    done    ? "#86efac"
                            : current ? "#93c5fd"
                            : "#64748b",
                  }}>
                    {label}
                  </span>
                  {current && (
                    <Loader
                      size={12}
                      style={{
                        marginLeft: "auto",
                        color: "#3b82f6",
                        animation: "spin 1s linear infinite",
                      }}
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Success state */}
        {status?.status === "done" && (
          <div style={{ marginTop: 20 }}>
            <div className="status-bar status-done" style={{ marginBottom: 16 }}>
              <CheckCircle
                size={16}
                style={{ display: "inline", marginRight: 8 }}
              />
              Meeting processed successfully — Meeting #{status.meeting_id}
            </div>

            {status.speakers && (
              <div className="card" style={{ marginBottom: 16 }}>
                <div style={{
                  display:    "flex",
                  alignItems: "center",
                  gap:        8,
                  marginBottom: 12,
                  color:      "#94a3b8",
                  fontSize:   13,
                }}>
                  <Users size={14} />
                  Speakers identified: {status.num_speakers}
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {status.speakers.map(s => (
                    <span
                      key={s}
                      style={{
                        padding:      "4px 12px",
                        borderRadius: 20,
                        background:   s === "UNKNOWN" ? "#1e1b4b" : "#052e16",
                        color:        s === "UNKNOWN" ? "#a5b4fc" : "#86efac",
                        fontSize:     13,
                        fontWeight:   500,
                      }}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: "flex", gap: 10 }}>
              <a
                href={`/transcripts`}
                style={{
                  padding:        "9px 18px",
                  background:     "#4f46e5",
                  color:          "white",
                  borderRadius:   8,
                  textDecoration: "none",
                  fontSize:       14,
                  fontWeight:     500,
                }}
              >
                View Transcript →
              </a>
              <button className="btn btn-ghost" onClick={reset}>
                Process Another Meeting
              </button>
            </div>
          </div>
        )}

        {/* Error state */}
        {status?.status === "error" && (
          <div style={{ marginTop: 16 }}>
            <div className="status-bar status-error">
              {status.message}
            </div>
            <button
              className="btn btn-ghost"
              onClick={reset}
              style={{ marginTop: 10 }}
            >
              Try Again
            </button>
          </div>
        )}

      </div>
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg) }
          to   { transform: rotate(360deg) }
        }
      `}</style>
    </div>
  )
  
}