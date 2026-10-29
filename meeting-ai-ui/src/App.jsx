import { BrowserRouter, NavLink, Route, Routes, useLocation } from "react-router-dom"
import {
  AudioLines, BotMessageSquare, ChevronRight, FileAudio, FileText,
  LayoutDashboard, ListChecks, Mic2, Sparkles, UserRoundPlus,
} from "lucide-react"
import Dashboard from "./pages/Dashboard"
import Enroll from "./pages/Enroll"
import ProcessMeeting from "./pages/ProcessMeeting"
import Transcripts from "./pages/Transcripts"
import Summary from "./pages/Summary"
import Chat from "./pages/Chat"
import MeetingActions from "./pages/MeetingActions"
import "./App.css"

const navGroups = [
  { label: "Workspace", items: [
    { to: "/", label: "Overview", icon: LayoutDashboard },
  ]},
  { label: "Meeting workflow", items: [
    { to: "/process", label: "Import meeting", icon: FileAudio, step: "01" },
    { to: "/transcripts", label: "Transcripts", icon: FileText, step: "02" },
    { to: "/summary", label: "AI summary", icon: Sparkles, step: "03" },
    { to: "/actions", label: "Action center", icon: ListChecks, step: "04" },
  ]},
  { label: "Intelligence", items: [
    { to: "/chat", label: "Ask meetings", icon: BotMessageSquare },
    { to: "/enroll", label: "Speaker library", icon: UserRoundPlus },
  ]},
]

const routeMeta = {
  "/": ["Workspace", "Overview"],
  "/process": ["Meeting workflow", "Import meeting"],
  "/transcripts": ["Meeting workflow", "Transcripts"],
  "/summary": ["Meeting workflow", "AI summary"],
  "/actions": ["Meeting workflow", "Action center"],
  "/chat": ["Intelligence", "Ask meetings"],
  "/enroll": ["Intelligence", "Speaker library"],
}

function AppShell() {
  const location = useLocation()
  const [group, page] = routeMeta[location.pathname] || ["Meeting AI", "Workspace"]
  const mobileItems = navGroups.flatMap((entry) => entry.items).slice(0, 5)

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><AudioLines size={20} /></span>
          <span><strong>MeetingAI</strong><small>Intelligence workspace</small></span>
        </div>
        <nav className="primary-nav" aria-label="Primary navigation">
          {navGroups.map((navGroup) => (
            <div className="nav-group" key={navGroup.label}>
              <p className="nav-group-label">{navGroup.label}</p>
              {navGroup.items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.to === "/"}
                  className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
                  <item.icon size={18} strokeWidth={1.8} />
                  <span>{item.label}</span>
                  {item.step && <span className="nav-step">{item.step}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="privacy-card">
            <span className="privacy-icon"><Mic2 size={16} /></span>
            <div><strong>Local workspace</strong><span>Audio stays on this device</span></div>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><span>{group}</span><ChevronRight size={14} /><strong>{page}</strong></div>
          <div className="service-status"><span className="status-dot" />Local workspace</div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/enroll" element={<Enroll />} />
            <Route path="/process" element={<ProcessMeeting />} />
            <Route path="/transcripts" element={<Transcripts />} />
            <Route path="/summary" element={<Summary />} />
            <Route path="/actions" element={<MeetingActions />} />
            <Route path="/chat" element={<Chat />} />
          </Routes>
        </main>
      </div>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {mobileItems.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/"}
            className={({ isActive }) => isActive ? "active" : ""}>
            <item.icon size={19} /><span>{item.label.split(" ")[0]}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export default function App() {
  return <BrowserRouter><AppShell /></BrowserRouter>
}
