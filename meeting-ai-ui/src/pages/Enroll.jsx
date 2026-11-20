import { useState, useEffect } from "react"
import { api, requestError } from "../api"
import { UserPlus } from "lucide-react"

export default function Enroll() {
  const [name,     setName]     = useState("")
  const [files,    setFiles]    = useState([])
  const [jobId,    setJobId]    = useState(null)
  const [status,   setStatus]   = useState(null)
  const [speakers, setSpeakers] = useState([])
  const [error,    setError]    = useState("")

  useEffect(() => {
    api.get("/api/speakers")
      .then(r => setSpeakers(r.data.speakers))
      .catch((request) => setError(requestError(request, "Could not load enrolled speakers.")))
  }, [])

  useEffect(() => {
    if (!jobId) return
    const interval = setInterval(() => {
      api.get(`/api/jobs/${jobId}`)
        .then(r => {
          setStatus(r.data)
          if (!["queued", "running"].includes(r.data.status)) {
            clearInterval(interval)
            if (r.data.status === "done") {
              api.get("/api/speakers")
                .then((response) => setSpeakers(response.data.speakers))
                .catch((request) => setError(requestError(request, "Enrollment finished, but the speaker list could not be refreshed.")))
            }
          }
        })
        .catch((request) => {
          clearInterval(interval)
          setStatus({ status: "error", message: requestError(request, "Lost connection while checking enrollment progress.") })
        })
    }, 1500)
    return () => clearInterval(interval)
  }, [jobId])

  const submit = async () => {
    if (!name.trim() || files.length === 0) return
    const fd = new FormData()
    fd.append("name", name)
    for (const f of files) fd.append("files", f)
    setError("")
    if (files.length > 5) {
      setError("Choose no more than five voice samples.")
      return
    }
    try {
      const r = await api.post("/api/speakers/enroll", fd)
      setJobId(r.data.job_id)
      setStatus({ status: "running", message: "Enrolling..." })
    } catch (request) {
      setStatus({ status: "error", message: requestError(request, "Could not start speaker enrollment.") })
    }
  }

  return (
    <div>
      <div className="page-heading"><div className="page-heading-copy">
        <span className="eyebrow">Speaker intelligence</span>
        <h1 className="page-title">Speaker library</h1>
        <p className="page-subtitle">Create trusted voice profiles so future transcripts can identify who said what.</p>
      </div></div>
      <div className="grid-2">
        <div className="card">
          <div className="form-group">
            <label>Speaker Name</label>
            <input
              type="text"
              placeholder="e.g. Preetham"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>Voice Samples (1-5 audio files, 20-30 sec each)</label>
            <input
              type="file"
              multiple
              accept=".mp3,.wav,.ogg,.m4a,.mp4"
              onChange={e => setFiles([...e.target.files])}
            />
            {files.length > 0 && (
              <p style={{fontSize:13,color:"#64748b",marginTop:6}}>
                {files.length} file(s) selected
              </p>
            )}
          </div>
          {status && (
            <div className={`status-bar status-${status.status}`}>
              {status.message}
            </div>
          )}
          {error && <div className="status-bar status-error">{error}</div>}
          <button
            className="btn btn-primary"
            onClick={submit}
            disabled={!name || files.length === 0 || ["queued", "running"].includes(status?.status)}
          >
            <UserPlus size={16} />
            Enroll Speaker
          </button>
        </div>

        <div className="card">
          <h3 style={{marginBottom:16}}>Enrolled Speakers</h3>
          {speakers.length === 0
            ? <p style={{color:"#64748b",fontSize:14}}>No speakers enrolled yet.</p>
            : (
              <table className="table">
                <thead>
                  <tr><th>Name</th><th>Samples</th><th>Enrolled</th></tr>
                </thead>
                <tbody>
                  {speakers.map(s => (
                    <tr key={s.id}>
                      <td>{s.name}</td>
                      <td>{s.num_samples}</td>
                      <td>{s.enrolled_at?.slice(0,10)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      </div>
    </div>
  )
}
