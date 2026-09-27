"""Generate an OFFLINE synthetic trace with scripted replies, never model-quality evidence.

Run from the repository root. Generated files stay in ignored runs/ until reviewed.
No credentials, provider calls, or held-out cases are used.
"""

import json
from pathlib import Path

from dealer_evidence_agent.corpus import load_corpus
from dealer_evidence_agent.graph import run_agent
from dealer_evidence_agent.model_client import ModelClient, RecordingClient
from dealer_evidence_agent.tracing import JsonlTrace, inspect_trace


def message(content):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]}


def main():
    documents = load_corpus(Path("data/manifest.json"))
    client = RecordingClient(
        [
            message(
                {"decision": {"action": "search_policies", "arguments": {"query": "loaner return"}}}
            ),
            message(
                {
                    "status": "answered",
                    "text": "Record the return time, odometer, and key count.",
                    "citations": [{"kind": "policy", "id": "shared_loaner_return"}],
                }
            ),
        ]
    )
    trace = JsonlTrace(Path("runs"))
    result = run_agent(
        "What should I record for a loaner return?",
        identity="tech_demo",
        documents=documents,
        model=ModelClient(client),
        trace=trace,
    )
    trace.close()
    report = inspect_trace(trace.path.parent, trace.run_id)
    assert result.answer.status == "answered" and report["complete"]
    assert report["usage"] == {}  # Scripted replies cannot claim provider token usage.
    print(f"OFFLINE recording_fake example: {trace.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
