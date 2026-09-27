"""Build a 110-second offline replay deck from reviewed real outputs; no service calls.

This prepares a screen-recording surface, not a video or hosted red-CI claim.
The final public recording still needs the separately authorized regression PR.
"""

import html
import json
from pathlib import Path


def main():
    root = Path("docs/evidence")
    held = json.loads((root / "m7-held-out-live.json").read_text(encoding="utf-8"))
    role = json.loads((root / "m7-role-demo.json").read_text(encoding="utf-8"))
    live = json.loads((root / "m7-live-nhtsa.json").read_text(encoding="utf-8"))
    shared = next(c for c in held["cases"] if c["case_id"] == "held_007")
    tech, manager = role["cases"]
    scenes = [
        {
            "seconds": 10,
            "title": "Dealer Evidence Agent",
            "label": "Captured execution replay",
            "body": "A bounded LangGraph agent for fictional dealership policies and public recall "
            "campaigns. Two tools. One logical tool call. At most two model calls.",
            "evidence": "Recorded 2026-09-27 • gpt-4.1-mini-2025-04-14 • No calls during playback",
        },
        {
            "seconds": 17,
            "title": "A supported policy answer",
            "label": "Live held-out case held_007",
            "body": shared["question"] + "\n\n" + shared["answer"]["text"],
            "evidence": "Citations: shared_record_corrections + shared_customer_contact\n"
            "Run: " + shared["run_id"],
        },
        {
            "seconds": 16,
            "title": "Technician: restricted question",
            "label": "Live development demo",
            "body": tech["question"] + "\n\n" + tech["answer"]["text"],
            "evidence": "Identity: tech_demo • Restricted IDs absent from model input\nRun: "
            + tech["answer"]["run_id"],
        },
        {
            "seconds": 16,
            "title": "Manager: the same question",
            "label": "Live development demo",
            "body": manager["question"] + "\n\n" + manager["answer"]["text"],
            "evidence": "Identity: manager_demo • Synthetic manager_goodwill_review supplied\nRun: "
            + manager["answer"]["run_id"],
        },
        {
            "seconds": 21,
            "title": "Real public recall integration",
            "label": "Live OpenAI + live NHTSA",
            "body": "2020 Toyota Corolla: campaigns 19V877000, 20V682000, and 23V865000.\n\n"
            "Actual graph execution: 2 model calls, 1 tool call, 1 HTTP attempt, 0 retries.\n\n"
            "General campaign records do not establish VIN eligibility, repair completion, "
            "or vehicle safety. Missing make/model/year stops lookup and asks for clarification.",
            "evidence": "Observation: 2026-09-27T14:21:16Z\nRun: " + live["answer"]["run_id"],
        },
        {
            "seconds": 18,
            "title": "A real production regression",
            "label": "Local red test; hosted red PR pending",
            "body": "Mutation: can_access(role, doc.visibility) → can_access(role, 'shared')\n\n"
            "Unchanged retrieval test: FAILED\n"
            "Technician results include manager_goodwill_review.\n\n"
            "Independent context guard: PASSED. Broken worktree removed.\n"
            "M6 hosted baseline: Windows + Ubuntu PASSED.",
            "evidence": "Passing M5 base: 6ec238d • Hosted M6 base: 5df166d\n"
            "The clearly labeled red-PR demonstration is not yet published.",
        },
        {
            "seconds": 12,
            "title": "Measured limits, retained failures",
            "label": "First held-out pass",
            "body": "Retrieval: 10/10 with all required sources.\n"
            "Mechanical graph checks: 20/24. Strict qualitative review: 14/24.\n"
            "Unauthorized evidence: 0 violations. Quality targets: NOT MET.\n\n"
            "A constrained demonstration, not a production-ready dealership assistant. "
            "No prompts or labels were tuned against these results.",
            "evidence": "Qualitative reviewer: Codex; independent human review pending.\n"
            "Full outputs, rubric, failures, hashes, and CI links are in docs/evidence/.",
        },
    ]
    assert sum(s["seconds"] for s in scenes) == 110
    cards = "\n".join(
        f'<section data-seconds="{s["seconds"]}" hidden><p class="label">'
        f"{html.escape(s['label'])}</p><h1>{html.escape(s['title'])}</h1>"
        f'<div class="body">{html.escape(s["body"])}</div>'
        f'<p class="evidence">{html.escape(s["evidence"])}</p></section>'
        for s in scenes
    )
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dealer Evidence Agent — captured execution replay</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#101924;color:#e7eff7;font:18px/1.45 system-ui}
main{max-width:1200px;margin:3vh auto;padding:28px 44px;background:#172637;border-radius:14px}
.top{display:flex;gap:20px;align-items:center;justify-content:space-between;color:#b6c7d8}
button{border:0;padding:10px 18px;border-radius:5px;font:inherit;cursor:pointer;
background:#7edbc4;color:#10202c}
.label{color:#7edbc4;text-transform:uppercase;letter-spacing:.08em;font-size:15px}
h1{font-size:38px;line-height:1.15;margin:18px 0}.body{white-space:pre-wrap;font-size:22px}
section{min-height:600px;padding:28px 0}
.evidence{white-space:pre-wrap;font:15px/1.5 monospace;color:#aac0d5;margin-top:30px}
progress{width:100%;height:8px;accent-color:#7edbc4}.note{font-size:14px;color:#aac0d5}
@media(max-width:700px){main{padding:18px}.body{font-size:18px}h1{font-size:28px}section{min-height:650px}}
</style><main><div class="top"><span>DEALER EVIDENCE AGENT · REVIEWED REPLAY</span>
<div><button id="play">Play 110 seconds</button> <button id="reset">Reset</button></div></div>
<div id="cards">CARDS</div><progress id="progress" max="110" value="0"></progress>
<p class="note"><span id="clock">0 / 110 s</span> · Prepared recording surface,
not a live execution. Public recording needs the authorized red-PR segment.
<a style="color:#7edbc4" href="m7-results.md">Results</a></p>
</main><script>
const cards=[...document.querySelectorAll('section')];let elapsed=0,last=0,running=false;
const play=document.getElementById('play');function render(){let start=0;
cards.forEach((card,index)=>{const end=start+Number(card.dataset.seconds);
card.hidden=!(elapsed>=start&&(elapsed<end||(elapsed>=110&&index===cards.length-1)));start=end;});
document.getElementById('progress').value=elapsed;
document.getElementById('clock').textContent=Math.floor(elapsed)+' / 110 s';}
function frame(now){if(!running)return;
elapsed=Math.min(110,elapsed+(now-last)/1000);last=now;render();
if(elapsed>=110){running=false;play.textContent='Replay';return;}requestAnimationFrame(frame);}
play.onclick=()=>{if(running){running=false;play.textContent='Resume';return;}
if(elapsed>=110)elapsed=0;running=true;last=performance.now();play.textContent='Pause';requestAnimationFrame(frame);};
document.getElementById('reset').onclick=()=>{running=false;elapsed=0;
play.textContent='Play 110 seconds';render();};render();
</script></html>"""
    Path("docs/demo.html").write_text(page.replace("CARDS", cards), encoding="utf-8")
    print("Prepared docs/demo.html: 7 scenes, 110 seconds, no network dependencies.")


if __name__ == "__main__":
    main()
