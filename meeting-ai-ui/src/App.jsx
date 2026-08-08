import { useState } from "react"
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom"
import Dashboard from "./pages/Dashboard"
import Enroll from "./pages/Enroll"
import ProcessMeeting from "./pages/ProcessMeeting"
import Transcripts from "./pages/Transcripts"
import Summary from "./pages/Summary"
import Chat from "./pages/Chat"
import {
  LayoutDashboard, UserPlus, Upload,
  FileText, Sparkles, MessageSquare
} from "lucide-react"
import "./App.css"

const nav = [
  { to: "/",           label: "Dashboard",  icon: LayoutDashboard },
  { to: "/enroll",     label: "Enroll",     icon: UserPlus        },
  { to: "/process",    label: "Process",    icon: Upload          },
  { to: "/transcripts",label: "Transcripts",icon: FileText        },
  { to: "/summary",    label: "Summary",    icon: Sparkles        },
  { to: "/chat",       label: "Chat",       icon: MessageSquare   },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <aside className="sidebar">
          <div className="logo">
            <Sparkles size={22} />
            <span>Meeting AI</span>
          </div>
          <nav>
            {nav.map(n => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  "nav-item" + (isActive ? " active" : "")
                }
              >
                <n.icon size={18} />
                <span>{n.label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="content">
          <Routes>
            <Route path="/"            element={<Dashboard />}      />
            <Route path="/enroll"      element={<Enroll />}         />
            <Route path="/process"     element={<ProcessMeeting />} />
            <Route path="/transcripts" element={<Transcripts />}    />
            <Route path="/summary"     element={<Summary />}        />
            <Route path="/chat"        element={<Chat />}           />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}