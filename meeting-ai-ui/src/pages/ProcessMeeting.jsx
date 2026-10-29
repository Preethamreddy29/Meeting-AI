import { useRef, useState } from "react"
import { Link } from "react-router-dom"
import axios from "axios"
import {
  ArrowRight, AudioLines, Check, CheckCircle2, FileAudio, FileText,
  LoaderCircle, RotateCcw, ShieldCheck, Sparkles, Upload, UsersRound, X,
} from "lucide-react"

const STEPS = [
  { label: "Prepare audio", detail: "Normalize the recording for analysis" },
  { label: "Create transcript", detail: "Whisper converts speech to text" },
  { label: "Separate speakers", detail: "Diarization groups each voice" },
  { label: "Identify known voices", detail: "Match enrolled speaker profiles" },
  { label: "Build meeting record", detail: "Save searchable, attributed segments" },
  { label: "Ready for review", detail: "Continue to the transcript workspace" },
]

function formatBytes(bytes) {
  if (!bytes) return "0 MB"
  const mb = bytes / 1024 / 1024
  return `${mb < 1 ? mb.toFixed(1) : mb.toFixed(1)} MB`
}

export default function ProcessMeeting() {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState(null)
  const [drag, setDrag] = useState(false)
  const [error, setError] = useState("")
  const ref = useRef()

  const poll = (id) => {
    const interval = window.setInterval(() => {
      axios.get(`http://localhost:8000/api/jobs/${id}`)
        .then((response) => {
          setStatus(response.data)
          if (!["queued", "running"].includes(response.data.status)) window.clearInterval(interval)
        })
        .catch(() => {
          window.clearInterval(interval)
          setStatus({ status: "error", message: "Lost connection to the local processing service." })
        })
    }, 2000)
  }

  const chooseFile = (selectedFile) => {
    if (!selectedFile) return
    const extension = selectedFile.name.split(".").pop()?.toLowerCase()
    if (!["mp3", "mp4", "wav", "m4a", "ogg"].includes(extension)) {
      setError("Choose an MP3, MP4, WAV, M4A, or OGG recording.")
      return
    }
    setError(""); setFile(selectedFile); setStatus(null)
  }

  const start = async () => {
    if (!file) return
    setError(""); setStatus({ status: "queued", message: "Adding the meeting to the local queue…", step: 0, total: 6 })
    const form = new FormData(); form.append("file", file)
    try {
      const response = await axios.post("http://localhost:8000/api/meetings/upload", form)
      poll(response.data.job_id)
    } catch (requestError) {
      setStatus({ status: "error", message: requestError.response?.data?.detail || "The recording could not be uploaded." })
    }
  }

  const reset = () => { setFile(null); setStatus(null); setError(""); if (ref.current) ref.current.value = "" }
  const active = ["queued", "running"].includes(status?.status)

  return (
    <div className="process-page">
      <div className="page-heading">
        <div className="page-heading-copy"><span className="eyebrow">Step 1 · Capture</span><h1 className="page-title">Import a meeting</h1><p className="page-subtitle">Create a speaker-attributed meeting record from an audio or video recording. Processing happens locally on this device.</p></div>
      </div>

      {!status && <div className="import-layout">
        <section className="card import-card">
          <div className="card-header"><div><span className="section-label">Recording</span><h2>{file ? "Ready to process" : "Choose a meeting recording"}</h2><p>You will review the selection before processing starts.</p></div></div>
          {!file ? <div className={`upload-zone professional-upload ${drag ? "active" : ""}`} onDragOver={(event) => { event.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={(event) => { event.preventDefault(); setDrag(false); chooseFile(event.dataTransfer.files[0]) }} onClick={() => ref.current?.click()}>
            <div><span className="upload-icon"><Upload size={24} /></span><strong>Drop a recording here</strong><p>or click to choose a file</p><small>MP3, MP4, WAV, M4A, OGG</small></div>
            <input ref={ref} type="file" accept=".mp3,.mp4,.wav,.m4a,.ogg" hidden onChange={(event) => chooseFile(event.target.files[0])} />
          </div> : <div className="file-review"><span className="file-review-icon"><FileAudio size={24} /></span><div><strong>{file.name}</strong><span>{formatBytes(file.size)} · {file.type || "Audio recording"}</span></div><button className="icon-btn" aria-label="Remove selected file" onClick={reset}><X size={15} /></button></div>}
          {error && <div className="status-bar status-error import-error">{error}</div>}
          {file && <div className="import-actions"><button className="btn btn-ghost" onClick={() => ref.current?.click()}>Choose another</button><button className="btn btn-primary" onClick={start}><AudioLines size={15} />Start local processing</button><input ref={ref} type="file" accept=".mp3,.mp4,.wav,.m4a,.ogg" hidden onChange={(event) => chooseFile(event.target.files[0])} /></div>}
        </section>
        <aside className="card processing-info"><span className="section-label">What happens next</span><div className="info-item"><FileText size={16} /><div><strong>Accurate transcript</strong><span>Timestamped text you can review.</span></div></div><div className="info-item"><UsersRound size={16} /><div><strong>Speaker attribution</strong><span>Known voices are matched locally.</span></div></div><div className="info-item"><Sparkles size={16} /><div><strong>Ready for intelligence</strong><span>Summaries, chat, and actions use the saved record.</span></div></div><div className="privacy-note"><ShieldCheck size={15} /><span>The recording is processed by the configured local audio pipeline.</span></div></aside>
      </div>}

      {status && <section className="card processing-card">
        {active && <><div className="processing-hero"><span className="processing-spinner"><LoaderCircle size={23} /></span><div><span className="section-label">Processing locally</span><h2>{status.message || "Preparing your meeting…"}</h2><p>{file?.name}</p></div><span className="processing-percent">{Math.round(((status.step || 0) / 6) * 100)}%</span></div><div className="large-progress"><span style={{ width: `${((status.step || 0) / 6) * 100}%` }} /></div><div className="pipeline-steps">{STEPS.map((step,index) => { const number=index+1; const done=number < (status.step || 0); const current=number === (status.step || 0); return <div className={`pipeline-step${done ? " done" : ""}${current ? " current" : ""}`} key={step.label}><span className="pipeline-dot">{done ? <Check size={12} /> : number}</span><div><strong>{step.label}</strong><small>{step.detail}</small></div>{current && <LoaderCircle className="spin" size={14} />}</div> })}</div></>}
        {status.status === "done" && <div className="completion-state"><span className="completion-icon"><CheckCircle2 size={28} /></span><span className="section-label">Processing complete</span><h2>Your meeting is ready for review.</h2><p>Meeting #{status.meeting_id} has been transcribed and added to the workspace.</p>{status.speakers?.length > 0 && <div className="speaker-result"><UsersRound size={14} /><span>{status.num_speakers} speakers:</span>{status.speakers.map((speaker) => <span className={`badge ${speaker === "UNKNOWN" ? "badge-unknown" : "badge-approved"}`} key={speaker}>{speaker}</span>)}</div>}<div className="completion-actions"><button className="btn btn-ghost" onClick={reset}><RotateCcw size={14} />Process another</button><Link className="btn btn-primary" to="/transcripts">Review transcript <ArrowRight size={14} /></Link></div></div>}
        {status.status === "error" && <div className="completion-state error-completion"><span className="completion-icon"><X size={28} /></span><span className="section-label">Processing stopped</span><h2>We could not process this recording.</h2><p>{status.message}</p><button className="btn btn-secondary" onClick={reset}><RotateCcw size={14} />Choose another file</button></div>}
      </section>}
    </div>
  )
}
