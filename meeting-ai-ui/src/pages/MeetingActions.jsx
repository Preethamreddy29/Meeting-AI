import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import axios from "axios"
import {
  AlertCircle, ArrowRight, CalendarDays, Check, CheckCircle2, ChevronDown,
  CircleDot, Clock3, Download, FileText, History, LoaderCircle, PencilLine,
  Quote, Save, Sparkles, Upload, UserRound, X,
} from "lucide-react"

const API = "http://localhost:8000"
const ACTIVE_JOB_STATES = new Set(["queued", "running"])
const KINDS = [
  { id: "action", label: "Actions" },
  { id: "decision", label: "Decisions" },
  { id: "follow_up", label: "Follow-ups" },
]

function errorMessage(error) { return error.response?.data?.detail || error.message || "Request failed" }
function formatSeconds(value) {
  if (value === null || value === undefined) return ""
  const seconds = Math.max(0, Math.floor(Number(value)))
  return `${String(Math.floor(seconds / 3600)).padStart(2, "0")}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`
}

export default function MeetingActions() {
  const localTimezone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata"
  const [meetings, setMeetings] = useState([])
  const [meetingId, setMeetingId] = useState("")
  const [sourceMode, setSourceMode] = useState("existing")
  const [title, setTitle] = useState("")
  const [notes, setNotes] = useState("")
  const [meetingDate, setMeetingDate] = useState("")
  const [timezone, setTimezone] = useState(localTimezone)
  const [items, setItems] = useState([])
  const [runs, setRuns] = useState([])
  const [runId, setRunId] = useState("")
  const [units, setUnits] = useState([])
  const [sourceType, setSourceType] = useState("")
  const [contextDate, setContextDate] = useState("")
  const [contextTimezone, setContextTimezone] = useState(localTimezone)
  const [activeKind, setActiveKind] = useState("action")
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState("")
  const [error, setError] = useState("")
  const latestMeeting = useRef("")

  const loadMeetings = useCallback(async () => {
    const response = await axios.get(`${API}/api/meetings`)
    setMeetings(response.data.meetings)
  }, [])
  const loadRuns = useCallback(async (id) => {
    const response = await axios.get(`${API}/api/actions/meetings/${id}/runs`)
    if (latestMeeting.current !== String(id)) return []
    setRuns(response.data.runs)
    return response.data.runs
  }, [])
  const loadItems = useCallback(async (id, selectedRun = "") => {
    const response = await axios.get(`${API}/api/actions/meetings/${id}/items${selectedRun ? `?run_id=${selectedRun}` : ""}`)
    if (latestMeeting.current !== String(id)) return
    setItems(response.data.items)
    setRunId(response.data.run_id ? String(response.data.run_id) : "")
    setUnits(response.data.units)
  }, [])
  const loadContext = useCallback(async (id) => {
    const response = await axios.get(`${API}/api/actions/meetings/${id}/context`)
    if (latestMeeting.current !== String(id)) return
    setSourceType(response.data.source_type)
    setContextDate(response.data.meeting_date || "")
    setContextTimezone(response.data.timezone || localTimezone())
  }, [])

  useEffect(() => {
    let active = true
    axios.get(`${API}/api/meetings`)
      .then((response) => { if (active) setMeetings(response.data.meetings) })
      .catch((requestError) => { if (active) setError(errorMessage(requestError)) })
    return () => { active = false }
  }, [])
  useEffect(() => {
    latestMeeting.current = String(meetingId)
    if (!meetingId) return
    Promise.all([loadRuns(meetingId), loadItems(meetingId), loadContext(meetingId)])
      .catch((requestError) => setError(errorMessage(requestError)))
  }, [meetingId, loadContext, loadItems, loadRuns])

  const selectMeeting = (id) => {
    latestMeeting.current = String(id); setMeetingId(String(id)); setItems([]); setRuns([])
    setRunId(""); setUnits([]); setSourceType(""); setContextDate(""); setError(""); setStatus("")
  }
  const createNotes = async () => {
    setBusy(true); setError("")
    try {
      const response = await axios.post(`${API}/api/actions/notes`, { title, text: notes, meeting_date: meetingDate || null, timezone: meetingDate ? timezone || null : null })
      await loadMeetings(); selectMeeting(response.data.meeting_id); setSourceMode("existing")
      setStatus("Notes saved. Your source is ready for extraction.")
    } catch (requestError) { setStatus(""); setError(errorMessage(requestError)) } finally { setBusy(false) }
  }
  const generate = async () => {
    if (!meetingId) return
    const hasReviewed = runs.some((run) => Number(run.reviewed_count) > 0)
    let acknowledged = false
    if (hasReviewed) {
      acknowledged = window.confirm("This meeting has reviewed items. A new draft run will be created and existing runs will remain available. Continue?")
      if (!acknowledged) return
    }
    setBusy(true); setError(""); setStatus("Gemini is reading the source and grounding every item…")
    const selectedMeeting = String(meetingId)
    try {
      const response = await axios.post(`${API}/api/actions/meetings/${selectedMeeting}/extract`, { acknowledge_existing_reviewed: acknowledged })
      let completed = false
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const job = (await axios.get(`${API}/api/jobs/${response.data.job_id}`)).data
        if (latestMeeting.current !== selectedMeeting) return
        setStatus(job.message || job.status)
        if (job.status === "done") { await loadRuns(selectedMeeting); await loadItems(selectedMeeting, job.run_id); completed = true; setStatus("Draft ready. Review the source evidence before approval."); break }
        if (!ACTIVE_JOB_STATES.has(job.status)) throw new Error(job.message || "Extraction failed")
        await new Promise((resolve) => window.setTimeout(resolve, 1500))
      }
      if (!completed) throw new Error("Extraction is taking longer than expected. Check job status before retrying.")
    } catch (requestError) { setStatus(""); setError(errorMessage(requestError)) } finally { setBusy(false) }
  }
  const saveContext = async () => {
    setBusy(true); setError("")
    try {
      await axios.patch(`${API}/api/actions/meetings/${meetingId}/context`, { meeting_date: contextDate || null, timezone: contextDate ? contextTimezone || null : null })
      await Promise.all([loadItems(meetingId, runId), loadRuns(meetingId)])
      setStatus("Meeting context saved. Relative dates have been recalculated.")
    } catch (requestError) { setStatus(""); setError(errorMessage(requestError)) } finally { setBusy(false) }
  }
  const save = async (item, changes) => {
    try {
      const response = await axios.patch(`${API}/api/actions/items/${item.id}`, { version: item.version, ...changes })
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, ...response.data, dirty: false } : entry))
      setError(""); await loadRuns(meetingId)
    } catch (requestError) { setError(errorMessage(requestError)); await loadItems(meetingId, runId) }
  }
  const edit = (id, field, value) => setItems((current) => current.map((item) => item.id === id ? { ...item, [field]: value, dirty: true } : item))
  const editEvidence = (itemId, evidenceIndex, field, value) => setItems((current) => current.map((item) => {
    if (item.id !== itemId) return item
    return { ...item, evidence: item.evidence.map((entry, index) => index === evidenceIndex ? { ...entry, [field]: value } : entry), dirty: true }
  }))

  const unitById = useMemo(() => new Map(units.map((unit) => [unit.id, unit])), [units])
  const selectedMeeting = meetings.find((meeting) => String(meeting.id) === String(meetingId))
  const approvedCount = items.filter((item) => item.review_status === "approved").length
  const filteredItems = items.filter((item) => item.kind === activeKind)
  const currentRun = runs.find((run) => String(run.id) === String(runId))
  const currentStep = items.length || runId ? 3 : meetingId ? 2 : 1

  return (
    <div className="actions-page">
      <div className="page-heading actions-heading">
        <div className="page-heading-copy"><span className="eyebrow">Human-reviewed AI</span><h1 className="page-title">Action center</h1><p className="page-subtitle">Turn notes or transcripts into accountable, source-backed work. Nothing leaves this workspace until you approve it.</p></div>
        {runId && <a className="btn btn-secondary" href={`${API}/api/actions/meetings/${meetingId}/export?run_id=${runId}`}><Download size={15} />Export approved CSV</a>}
      </div>

      <div className="stepper" aria-label="Action workflow progress">
        {[{n:1,t:"Choose source"},{n:2,t:"Extract draft"},{n:3,t:"Review & approve"}].map((step) => (
          <div className={`stepper-item${currentStep === step.n ? " current" : ""}${currentStep > step.n ? " complete" : ""}`} key={step.n}>
            <span>{currentStep > step.n ? <Check size={13} /> : step.n}</span><strong>{step.t}</strong>
          </div>
        ))}
      </div>

      {(status || error) && <div className={`action-notice ${error ? "notice-error" : "notice-info"}`}>{error ? <AlertCircle size={16} /> : busy ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}<span>{error || status}</span></div>}

      <section className="card source-card">
        <div className="source-card-head"><div><span className="section-label">Step 1 · Source</span><h2>What should Gemini analyze?</h2></div><div className="segmented-control"><button className={sourceMode === "existing" ? "active" : ""} onClick={() => setSourceMode("existing")}><History size={14} />Saved meeting</button><button className={sourceMode === "notes" ? "active" : ""} onClick={() => setSourceMode("notes")}><PencilLine size={14} />New notes</button></div></div>

        {sourceMode === "notes" ? (
          <div className="notes-composer">
            <div className="composer-main"><label htmlFor="action-title">Meeting title</label><input id="action-title" placeholder="e.g. Product launch weekly sync" value={title} onChange={(event) => setTitle(event.target.value)} /><label htmlFor="action-notes">Meeting notes</label><textarea id="action-notes" rows={9} placeholder="Paste the meeting notes here. Keep owners, commitments, and date wording as stated…" value={notes} onChange={(event) => setNotes(event.target.value)} /><div className="file-inline"><Upload size={14} /><label htmlFor="action-upload">Import a .txt or .md file</label><input id="action-upload" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={async (event) => { const file = event.target.files[0]; if (!file) return; if (file.size > 256000) { setError("Text file is too large"); return } setNotes(await file.text()); if (!title) setTitle(file.name) }} /></div></div>
            <aside className="composer-context"><span className="section-label">Meeting context</span><p>Context is optional, but required to resolve words such as “tomorrow” or “next Friday.”</p><label htmlFor="action-date">Meeting date</label><input id="action-date" type="date" value={meetingDate} onChange={(event) => setMeetingDate(event.target.value)} /><label htmlFor="action-timezone">Timezone</label><input id="action-timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)} disabled={!meetingDate} placeholder="Asia/Kolkata" /><button className="btn btn-primary" disabled={busy || !title.trim() || !notes.trim()} onClick={createNotes}>Save source <ArrowRight size={14} /></button></aside>
          </div>
        ) : (
          <div className="existing-source">
            <label htmlFor="meeting-choice">Saved notes or processed transcript</label>
            <select id="meeting-choice" value={meetingId} onChange={(event) => selectMeeting(event.target.value)}><option value="">Select a meeting…</option>{meetings.map((meeting) => <option key={meeting.id} value={meeting.id}>#{meeting.id} · {meeting.filename}</option>)}</select>
            {selectedMeeting ? <div className="selected-source"><span className="selected-source-icon"><FileText size={18} /></span><div><strong>{selectedMeeting.filename}</strong><span>Meeting #{selectedMeeting.id} · {sourceType || "transcript"}</span></div><CheckCircle2 size={18} /></div> : <p className="source-hint">Processed audio and saved notes both appear here.</p>}
          </div>
        )}
      </section>

      {meetingId && <section className="extraction-layout">
        <div className="card extraction-card"><div><span className="section-label">Step 2 · AI extraction</span><h2>Create a grounded draft</h2><p>Gemini identifies explicit actions, decisions, and follow-ups. Every result must include an exact quotation from the source.</p></div><button className="btn btn-primary" disabled={busy} onClick={generate}>{busy ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}{runs.length ? "Extract a new draft" : "Extract with Gemini"}</button></div>
        <div className="card context-card"><div className="context-title"><CalendarDays size={16} /><div><strong>Date context</strong><span>Used only to resolve relative due dates</span></div></div><div className="context-fields"><input aria-label="Meeting date" type="date" value={contextDate} onChange={(event) => setContextDate(event.target.value)} /><input aria-label="Meeting timezone" value={contextTimezone} onChange={(event) => setContextTimezone(event.target.value)} disabled={!contextDate} placeholder="Asia/Kolkata" /><button className="btn btn-ghost btn-sm" disabled={busy || Boolean(contextDate && !contextTimezone)} onClick={saveContext}>Save</button></div></div>
      </section>}

      {runs.length > 0 && <section className="review-workspace">
        <div className="review-toolbar"><div><span className="section-label">Step 3 · Review</span><h2>Verify before approval</h2><p>{items.length} extracted · {approvedCount} approved · {items.length - approvedCount} awaiting review</p></div><div className="run-picker"><History size={14} /><select aria-label="Extraction run" value={runId} onChange={(event) => { setRunId(event.target.value); loadItems(meetingId, event.target.value).catch((requestError) => setError(errorMessage(requestError))) }}>{runs.map((run) => <option key={run.id} value={run.id}>Run #{run.id} · {run.item_count} items · {run.approved_count || 0} approved</option>)}</select></div></div>
        <div className="review-summary"><div className="approval-progress"><span style={{ width: `${items.length ? approvedCount / items.length * 100 : 0}%` }} /></div><span>{items.length ? Math.round(approvedCount / items.length * 100) : 0}% approved</span>{currentRun && <small>Model: {currentRun.model || "Gemini"}</small>}</div>
        <div className="kind-tabs" role="tablist">{KINDS.map((kind) => { const count = items.filter((item) => item.kind === kind.id).length; return <button role="tab" aria-selected={activeKind === kind.id} className={activeKind === kind.id ? "active" : ""} key={kind.id} onClick={() => setActiveKind(kind.id)}>{kind.label}<span>{count}</span></button> })}</div>

        {filteredItems.length === 0 ? <div className="card empty-review"><CircleDot size={20} /><strong>No {KINDS.find((kind) => kind.id === activeKind)?.label.toLowerCase()} found</strong><span>Gemini only returns items explicitly supported by the source.</span></div> : filteredItems.map((item, itemIndex) => (
          <article className={`review-card review-${item.review_status}`} key={item.id}>
            <header className="review-card-head"><div className="item-index">{String(itemIndex + 1).padStart(2,"0")}</div><div><span className={`badge badge-${item.review_status}`}>{item.review_status === "approved" && <Check size={10} />}{item.review_status}</span>{item.dirty && <span className="unsaved-label">Unsaved changes</span>}</div><div className="review-actions"><button className="btn btn-ghost btn-sm" disabled={!item.dirty} onClick={() => save(item,{description:item.description,owner:item.owner||null,due_date_text:item.due_date_text||null,evidence:item.evidence})}><Save size={13} />Save</button><button className="btn btn-secondary btn-sm" disabled={item.dirty || !item.evidence_valid || item.review_status === "approved"} onClick={() => save(item,{review_status:"approved"})}><Check size={13} />Approve</button><button className="icon-btn reject-btn" aria-label="Reject item" title="Reject" disabled={item.dirty || item.review_status === "rejected"} onClick={() => save(item,{review_status:"rejected"})}><X size={15} /></button></div></header>
            <div className="review-card-body"><div className="item-fields"><label htmlFor={`description-${item.id}`}>Description</label><textarea id={`description-${item.id}`} rows={2} value={item.description} onChange={(event) => edit(item.id,"description",event.target.value)} /><div className="field-grid"><div><label htmlFor={`owner-${item.id}`}><UserRound size={12} />Owner</label><input id={`owner-${item.id}`} value={item.owner||""} onChange={(event) => edit(item.id,"owner",event.target.value)} placeholder="Unassigned" /></div><div><label htmlFor={`due-${item.id}`}><Clock3 size={12} />Due date as stated</label><input id={`due-${item.id}`} value={item.due_date_text||""} onChange={(event) => edit(item.id,"due_date_text",event.target.value)} placeholder="No due date stated" />{item.due_date_iso && <span className="resolved-date">Resolved to {item.due_date_iso}</span>}</div></div>{item.due_date_needs_review && <div className="inline-warning"><AlertCircle size={13} />This relative date needs context or manual review.</div>}</div>
              <aside className={`evidence-panel${item.evidence_valid ? "" : " invalid"}`}><div className="evidence-head"><span><Quote size={14} />Source evidence</span>{item.evidence_valid ? <span className="evidence-valid"><CheckCircle2 size={12} />Verified</span> : <span className="evidence-invalid"><AlertCircle size={12} />Needs correction</span>}</div>{item.evidence.map((evidence,index) => { const unit=unitById.get(evidence.source_unit_id); return <div className="evidence-entry" key={`${item.id}-${index}`}><select aria-label={`Source unit ${index+1}`} value={evidence.source_unit_id} onChange={(event) => editEvidence(item.id,index,"source_unit_id",event.target.value)}>{units.map((sourceUnit) => <option key={sourceUnit.id} value={sourceUnit.id}>{sourceUnit.id}{sourceUnit.start===undefined?"":` · ${formatSeconds(sourceUnit.start)}`}</option>)}</select><textarea aria-label={`Exact quotation ${index+1}`} rows={3} value={evidence.quote} onChange={(event) => editEvidence(item.id,index,"quote",event.target.value)} />{unit?.speaker && <span className="source-attribution">{unit.speaker}{unit.start===undefined?"":` · ${formatSeconds(unit.start)}`}</span>}</div>})}{!item.evidence_valid && <p className="evidence-issue">{item.evidence_issue}. Choose the right source and copy the exact wording before approval.</p>}</aside>
            </div>
          </article>
        ))}
      </section>}

      {units.length > 0 && <details className="source-drawer"><summary><span><FileText size={15} />Original source · {units.length} {sourceType === "notes" ? "lines" : "segments"}</span><ChevronDown size={15} /></summary><div className="source-units">{units.map((unit) => <div className="source-unit" key={unit.id}><span>{unit.id}{unit.start===undefined?"":` · ${formatSeconds(unit.start)}`}</span><p>{unit.speaker ? <strong>{unit.speaker}: </strong> : null}{unit.text}</p></div>)}</div></details>}
    </div>
  )
}
