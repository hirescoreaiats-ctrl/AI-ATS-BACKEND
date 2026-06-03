import { useState } from "react";
import { Send, Sparkles } from "lucide-react";
import { enterpriseApi } from "../../services/enterpriseApi.js";
import { Button } from "../design-system/Button.jsx";

export function AIRecruiterCopilot({ jobId }) {
  const [message, setMessage] = useState("Analyze bottlenecks and recommend next actions");
  const [response, setResponse] = useState(null);

  async function askCopilot() {
    try {
      setResponse(await enterpriseApi.copilotChat({ job_id: jobId, message }));
    } catch {
      setResponse({ answer: "Copilot is ready once the API server is running.", intent: "offline" });
    }
  }

  return (
    <section className="rounded-md border border-ats-line bg-white shadow-sm">
      <header className="flex items-center gap-2 border-b border-ats-line px-4 py-3">
        <Sparkles size={18} className="text-ats-brand" />
        <h2 className="text-sm font-semibold text-ats-ink">AI Recruiter Copilot</h2>
      </header>
      <div className="space-y-3 p-4">
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} className="h-24 w-full rounded-md border border-ats-line p-3 text-sm outline-none focus:border-ats-brand" />
        <Button onClick={askCopilot}><Send size={17} />Ask</Button>
        {response && <div className="rounded-md bg-ats-surface p-3 text-sm text-ats-ink">{response.answer || JSON.stringify(response)}</div>}
      </div>
    </section>
  );
}
