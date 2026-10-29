import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import axios from "axios"
import {
  ArrowRight, AudioWaveform, Clock3, FileAudio, FileText,
  ListChecks, MessageSquareText, Sparkles, UsersRound,
} from "lucide-react"

const statMeta = [
  { key: "total_meetings", label: "Meetings", note: "Processed locally", icon: FileAudio, tone: "blue" },
  { key: "total_speakers", label: "Known speakers", note: "Voice profiles", icon: UsersRound, tone: "teal" },
  { key: "total_segments", label: "Transcript segments", note: "Searchable moments", icon: AudioWaveform, tone: "violet" },
  { key: "unknown_segments", label: "Needs attribution", note: "Unknown speakers", icon: MessageSquareText, tone: "amber" },
]

const workflow = [
  { step: "01", title: "Bring in a meeting", body: "Upload a recording or start from notes.", to: "/process", icon: FileAudio },
  { step: "02", title: "Review the record", body: "Check speakers, transcript, and context.", to: "/transcripts", icon: FileText },
  { step: "03", title: "Turn talk into work", body: "Extract, verify, approve, and export.", to: "/actions", icon: ListChecks },
]

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    axios.get("http://localhost:8000/api/dashboard")
      .then((response) => setData(response.data))
      .catch(() => setError("The local API is not available. Start the FastAPI server and refresh."))
  }, [])

  const stats = data?.stats || {}
  const meetings = data?.recent_meetings || []

  return (
    <div className="dashboard-page">
      <div className="page-heading">
        <div className="page-heading-copy">
          <span className="eyebrow">Meeting intelligence</span>
          <h1 className="page-title">Move every conversation forward.</h1>
          <p className="page-subtitle">Capture a meeting once, then turn it into a trustworthy transcript, summary, and source-backed action plan.</p>
        </div>
        <Link className="btn btn-primary" to="/process"><FileAudio size={16} />Import a meeting</Link>
      </div>

      {error && <div className="status-bar status-error dashboard-alert">{error}</div>}

      <section className="grid-4 metric-grid" aria-label="Workspace metrics">
        {statMeta.map((item) => (
          <article className={`metric-card metric-${item.tone}`} key={item.key}>
            <div className="metric-top"><span className="metric-icon"><item.icon size={17} /></span><span className="metric-trend">Workspace</span></div>
            <strong>{data ? stats[item.key] : "—"}</strong>
            <span className="metric-label">{item.label}</span>
            <small>{item.note}</small>
          </article>
        ))}
      </section>

      <div className="dashboard-layout">
        <section className="card workflow-card">
          <div className="card-header">
            <div><span className="section-label">Recommended workflow</span><h2>From recording to accountable work</h2><p>A clear path through the workspace.</p></div>
          </div>
          <div className="workflow-list">
            {workflow.map((item) => (
              <Link className="workflow-item" to={item.to} key={item.step}>
                <span className="workflow-number">{item.step}</span>
                <span className="workflow-icon"><item.icon size={18} /></span>
                <span className="workflow-copy"><strong>{item.title}</strong><small>{item.body}</small></span>
                <ArrowRight size={16} />
              </Link>
            ))}
          </div>
        </section>

        <aside className="card focus-card">
          <span className="focus-icon"><Sparkles size={19} /></span>
          <span className="section-label">Action center</span>
          <h2>Decisions should not disappear into notes.</h2>
          <p>Gemini extracts commitments with the exact source attached. You stay in control of owners, dates, and approval.</p>
          <Link className="btn btn-secondary" to="/actions">Open action center <ArrowRight size={15} /></Link>
        </aside>
      </div>

      <section className="card recent-card">
        <div className="card-header">
          <div><span className="section-label">Recent activity</span><h2>Latest meetings</h2></div>
          <Link className="quiet-link" to="/transcripts">View transcripts <ArrowRight size={14} /></Link>
        </div>
        {meetings.length === 0 ? (
          <div className="empty-state"><FileAudio size={22} /><strong>No meetings yet</strong><span>Import your first recording to begin.</span></div>
        ) : (
          <div className="meeting-list">
            {meetings.map((meeting) => (
              <div className="meeting-row" key={meeting.id}>
                <span className="meeting-file-icon"><FileAudio size={17} /></span>
                <div className="meeting-main"><strong>{meeting.filename}</strong><span>Meeting #{meeting.id}</span></div>
                <div className="meeting-meta"><span><UsersRound size={13} />{meeting.num_speakers ?? "—"} speakers</span><span><Clock3 size={13} />{meeting.duration_sec ? `${Math.round(meeting.duration_sec)} sec` : "No duration"}</span></div>
                <span className="meeting-date">{meeting.processed_at?.slice(0, 10) || "—"}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
