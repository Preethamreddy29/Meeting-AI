import { useState, useRef, useEffect } from "react"
import axios from "axios"
import { Send } from "lucide-react"

export default function Chat() {
  const [messages, setMessages] = useState([
    {
      role: "ai",
      text: "Hi! I know everything about your meetings. Ask me anything — what was discussed, who said what, action items, comparisons across meetings, anything.",
    },
  ])
  const [input,   setInput]   = useState("")
  const [loading, setLoading] = useState(false)
  const bottom = useRef()

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const send = async () => {
    const q = input.trim()
    if (!q || loading) return

    setInput("")
    setMessages(prev => [...prev, { role: "user", text: q }])
    setLoading(true)

    // Build history for context
    const history = messages
      .filter(m => m.role !== "thinking")
      .map(m => ({
        role:    m.role === "user" ? "user" : "assistant",
        content: m.text,
      }))

    try {
      const r = await axios.post("http://localhost:8000/api/chat", {
        question: q,
        history,
      })
      setMessages(prev => [
        ...prev,
        { role: "ai", text: r.data.answer },
      ])
    } catch (e) {
      setMessages(prev => [
        ...prev,
        {
          role: "ai",
          text: "Sorry, something went wrong. Make sure Ollama is running.",
        },
      ])
    }

    setLoading(false)
  }

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div>
      <h1 className="page-title">Chat with your Meetings</h1>
      <div className="card chat-wrap">
        <div className="chat-msgs">
          {messages.map((m, i) => (
            <div key={i} className={`msg msg-${m.role}`}>
              {m.text}
            </div>
          ))}
          {loading && (
            <div className="msg-thinking">Thinking...</div>
          )}
          <div ref={bottom} />
        </div>

        <div className="chat-input">
          <input
            type="text"
            placeholder="Ask anything about your meetings..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
          />
          <button
            className="btn btn-primary"
            onClick={send}
            disabled={loading || !input.trim()}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}