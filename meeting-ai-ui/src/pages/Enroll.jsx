import { useState, useEffect } from "react"
import axios from "axios"
import { UserPlus, CheckCircle } from "lucide-react"

export default function Enroll() {
  const [name,     setName]     = useState("")
  const [files,    setFiles]    = useState([])
  const [jobId,    setJobId]    = useState(null)
  const [status,   setStatus]   = useState(null)
  const [speakers, setSpeakers] = useState([])

  useEffect(() => {
    axios.get("http://localhost:8000/api/speakers")
      .then(r => setSpeakers(r.data.speakers))
  }, [status])

  useEffect(() => {
    if (!jobId) return
    const interval = setInterval(() => {
      axios.get(`http://localhost:8000/api/jobs/${jobId}`)
        .then(r => {
          setStatus(r.data)
          if (r.data.status !== "running") clearInterval(interval)
        })
    }, 1500)
    return () => clearInterval(interval)
  }, [jobId])

  const submit = async () => {
    if (!name.trim() || files.length === 0) return
    const fd = new FormData()
    fd.append("name", name)
    for (const f of files) fd.append("files", f)
    const r = await axios.post("http://localhost:8000/api/speakers/enroll", fd)
    setJobId(r.data.job_id)
    setStatus({ status: "running", message: "Enrolling..." })
  }

  return (
    <div>
      <h1 className="page-title">Enroll Speaker</h1>
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
            <label>Voice Samples (2-5 audio files, 20-30 sec each)</label>
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
          <button
            className="btn btn-primary"
            onClick={submit}
            disabled={!name || files.length === 0 || status?.status === "running"}
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