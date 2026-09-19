"""Dream-tree visualisation: self-contained interactive HTML from the live graph.

    PYTHONPATH=python python python/viz.py <subject> [--out docs/dream-tree.html] [--domain island|workshop]

Reads the OSTIS graph through the bridge — the page is generated data, never a
mock-up — and renders three views:

  1. Dream constellation — strategies as a graph (derived_from edges), node
     size = replay verdict, glow = deployed winners; hover for details.
  2. Score ascent — day-by-day online scores as an animated step line.
  3. Experience explorer — every recorded episode with its full step table.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge import OneiroBridge
from replay.engine import ExperienceTree


def gather(subject: str, domain: str) -> dict:
    bridge = OneiroBridge(
        os.environ.get("ONEIRO_HOST", "localhost"), int(os.environ.get("ONEIRO_PORT", "8090"))
    )
    bridge.connect()
    try:
        records = bridge.retrieve_attempts(subject)
        signature = None
        if domain == "workshop":
            from strategy_workshop import workshop_signature

            signature = workshop_signature
        tree = ExperienceTree.from_records(records, signature_fn=signature)
        consistency = tree.verify_consistency()
        strategies = bridge.load_strategies()
    finally:
        bridge.close()

    episodes: dict[str, list] = {}
    for rec in records:
        if rec.episode:
            episodes.setdefault(rec.episode, []).append(rec)

    return {
        "strategies": strategies,
        "episodes": episodes,
        "consistency": consistency,
        "conflicts": len(consistency["conflicts"]),
    }


def render(subject: str, out_path: str, domain: str = "island", title: str | None = None) -> str:
    data = gather(subject, domain)
    strategies = data["strategies"]
    episodes = data["episodes"]
    consistency = data["consistency"]

    # ---- derived numbers for the page ----
    max_replay = max((s["replay_score"] or 0.0) for s in strategies) if strategies else 1.0
    deployed = [s for s in strategies if s["online_score"] is not None]
    deployed.sort(key=lambda s: s["dream_round"] or 0)
    ascent = [
        {"round": int(s["dream_round"] or 0), "name": s["name"], "online": round(s["online_score"], 2)}
        for s in deployed
    ]
    day1 = min((s["online_score"] for s in deployed), default=0.0)
    final = max((s["online_score"] for s in deployed), default=0.0)
    gain_pct = (100.0 * (final - day1) / day1) if day1 else 0.0

    page_title = title or f"Oneiro-OSTIS — {subject}"
    payload = {
        "subject": subject,
        "domain": domain,
        "title": page_title,
        "strategies": strategies,
        "maxReplay": max_replay,
        "ascent": ascent,
        "day1": round(day1, 2),
        "final": round(final, 2),
        "gainPct": round(gain_pct, 1),
        "episodes": {
            ep: [
                {
                    "i": r.step_index,
                    "action": r.action or "",
                    "object": r.object or "",
                    "outcome": (r.outcome or "").replace("concept_", ""),
                    "score": None if r.score is None else round(r.score, 3),
                    "strategy": r.strategy or "",
                    "note": r.note or "",
                }
                for r in steps
            ]
            for ep, steps in episodes.items()
        },
        "consistency": {
            "episodes": consistency["episodes"],
            "steps": consistency["steps"],
            "transitions": consistency["transitions"],
            "conflicts": data["conflicts"],
        },
    }

    document = HTML_SHELL.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(document)
    return out_path


HTML_SHELL = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Oneiro-OSTIS dream tree</title>
<style>
:root{
  --bg:#0b0e14; --panel:#11151f; --panel2:#161b28; --line:#232a3a;
  --txt:#d7dde8; --dim:#7b8598; --acc:#5b8cff; --good:#3ecf8e; --warn:#ffb454; --bad:#ff6b6b;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 700px at 70% -10%,#141b2e 0%,var(--bg) 55%);
  color:var(--txt);font-family:'Segoe UI',system-ui,sans-serif;}
header{padding:26px 34px 10px;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
h1{font-size:1.45rem;margin:0;letter-spacing:.4px}
h1 .hglow{color:var(--acc);text-shadow:0 0 18px rgba(91,140,255,.55)}
.sub{color:var(--dim);font-size:.86rem}
.stats{display:flex;gap:14px;padding:14px 34px 4px;flex-wrap:wrap}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 18px;min-width:130px}
.stat .v{font-size:1.5rem;font-weight:700}
.stat .l{color:var(--dim);font-size:.72rem;text-transform:uppercase;letter-spacing:1px;margin-top:2px}
.stat.good .v{color:var(--good)} .stat.acc .v{color:var(--acc)}
.wrap{display:grid;grid-template-columns:1.25fr 1fr;gap:18px;padding:16px 34px 8px}
@media(max-width:1100px){.wrap{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.card h2{margin:0;padding:12px 18px;font-size:.95rem;border-bottom:1px solid var(--line);color:var(--txt)}
.card .body{padding:12px 16px}
svg{display:block;width:100%}
#constellation svg{cursor:grab}
.node{cursor:pointer}
.node circle{transition:filter .15s}
.node:hover circle{filter:drop-shadow(0 0 8px rgba(91,140,255,.9))}
.node text{fill:var(--dim);font-size:10px;pointer-events:none}
.node.sel text{fill:var(--txt);font-weight:600}
.tip{position:fixed;pointer-events:none;background:#1a2132;border:1px solid var(--line);
  border-radius:10px;padding:10px 12px;font-size:.78rem;max-width:320px;z-index:10;display:none;
  box-shadow:0 8px 30px rgba(0,0,0,.5);line-height:1.5}
.tip b{color:var(--acc)}
.tip .num{color:var(--good)}
.edge{stroke:#2a3350;stroke-width:1.2;fill:none;opacity:.7}
.legend{display:flex;gap:16px;padding:8px 34px 2px;color:var(--dim);font-size:.74rem;flex-wrap:wrap}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
table{border-collapse:collapse;width:100%;font-size:.8rem}
th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left}
th{color:var(--dim);font-weight:600;font-size:.7rem;text-transform:uppercase;letter-spacing:.8px}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.68rem}
.b-dep{background:rgba(91,140,255,.16);color:var(--acc)}
.b-win{background:rgba(62,207,142,.16);color:var(--good)}
.bar{display:inline-block;height:8px;border-radius:3px;background:linear-gradient(90deg,var(--acc),#8fb0ff);vertical-align:middle}
tr.winrow td{background:rgba(62,207,142,.05)}
#episodes{grid-column:1/-1}
.ep-tab{display:inline-block;margin:3px 6px 3px 0;padding:5px 12px;background:var(--panel2);
  border:1px solid var(--line);border-radius:9px;cursor:pointer;font-size:.78rem;color:var(--dim)}
.ep-tab.active{color:var(--txt);border-color:var(--acc);background:rgba(91,140,255,.08)}
.outcome-success{color:var(--good)} .outcome-failure,.outcome-illegal{color:var(--bad)}
.note{color:var(--dim);font-size:.72rem}
footer{padding:16px 34px 30px;color:var(--dim);font-size:.74rem}
code{background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:.8em}
</style>
</head>
<body>
<header>
  <h1><span class="hglow">Oneiro-OSTIS</span> — dream tree</h1>
  <span class="sub" id="hdrmeta"></span>
</header>
<div class="stats" id="stats"></div>
<div class="legend" id="legend"></div>
<div class="wrap">
  <div class="card" id="constellation">
    <h2>Dream constellation — every strategy the dreams ever proposed</h2>
    <div class="body" id="constBody"></div>
  </div>
  <div class="card">
    <h2>Score ascent — measured online, day after day</h2>
    <div class="body" id="ascentBody"></div>
    <div class="body" id="dreamTable"></div>
  </div>
  <div class="card" id="episodes">
    <h2>Recorded experience — what the judge replays</h2>
    <div class="body" id="epTabs"></div>
    <div class="body" id="epBody" style="max-height:420px;overflow:auto"></div>
  </div>
</div>
<footer>
  Generated from the live OSTIS knowledge base (sc-machine agents) — every node on this page
  is a graph element, every number was read back through the graph. Interactive: hover nodes,
  click episodes. <span id="footmeta"></span>
</footer>
<div class="tip" id="tip"></div>
<script>
const D = __PAYLOAD__;
const $ = id => document.getElementById(id);

/* ---------- header & stats ---------- */
$("hdrmeta").textContent = `subject ${D.subject} · domain ${D.domain} · ${D.consistency.episodes} episodes · ${D.consistency.steps} recorded steps`;
$("footmeta").textContent = `replay transitions: ${D.consistency.transitions} · recording conflicts: ${D.consistency.conflicts}`;
const gain = D.day1 ? `+${D.gainPct}%` : "—";
$("stats").innerHTML = [
  ["strategies in graph", D.strategies.length, "acc"],
  ["day 1 online", D.day1, ""],
  ["final online", D.final, "good"],
  ["ascent", gain, "good"],
  ["replay conflicts", D.consistency.conflicts, D.consistency.conflicts ? "" : "good"],
].map(([l,v,c])=>`<div class="stat ${c}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
$("legend").innerHTML = `
 <span><span class="dot" style="background:#5b8cff"></span>incumbent / candidate</span>
 <span><span class="dot" style="background:#3ecf8e;box-shadow:0 0 8px #3ecf8e"></span>deployed winner</span>
 <span>node size = replay verdict · arrow = derived from</span>`;

/* ---------- dream constellation (SVG) ---------- */
const STRATS = D.strategies;
const byName = Object.fromEntries(STRATS.map(s=>[s.name||`(unnamed)`,s]));
const names = Object.keys(byName);
const W = 640, H = 760;
// layout: parent left, children right; root-ish incumbents on the left column
const pos = {};
const roots = names.filter(n => !byName[n].derived_from || !byName[byName[n].derived_from]);
const childrenOf = {};
names.forEach(n=>{
  const p = byName[n].derived_from;
  if (p && byName[p]) (childrenOf[p] ||= []).push(n);
});
(function layout(){
  const colW = [80, 300, 500, 610];
  // vertical sweep per column so leaves never collide
  const yc = {0:60, 1:60, 2:60, 3:60};
  const place = (n, col) => {
    if (pos[n]) return;
    const kids = childrenOf[n] || [];
    if (!kids.length){
      pos[n] = {x: colW[Math.min(col,3)], y: yc[col]};
      yc[col] += 34;
    } else {
      kids.forEach(k=>place(k, Math.min(col+1,3)));
      const ys = kids.map(k=>pos[k].y);
      pos[n] = {x: colW[Math.min(col,3)], y: ys.reduce((a,b)=>a+b,0)/ys.length};
    }
  };
  roots.forEach(r=>place(r,0));
  // clamp into the viewBox
  names.forEach(n=>{ pos[n].y = Math.max(30, Math.min(H-30, pos[n].y)); });
})();

const maxR = D.maxReplay || 1;
function nodeR(s){ const v=(s.replay_score||0)/maxR; return 6+16*Math.pow(v,0.4); }
function nodeColor(s){
  if (s.online_score!=null && s.online_score>=D.final-0.01) return "#3ecf8e";
  if (s.online_score!=null) return "#5b8cff";
  return "#3a4666";
}
let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
names.forEach(n=>{
  const p = byName[n].derived_from;
  if (p && pos[p] && pos[n]){
    svg += `<path class="edge" d="M${pos[p].x+nodeR(byName[p])+2},${pos[p].y} C ${(pos[p].x+pos[n].x)/2},${pos[p].y} ${(pos[p].x+pos[n].x)/2},${pos[n].y} ${pos[n].x-nodeR(byName[n])-2},${pos[n].y}"/>`;
  }
});
names.forEach(n=>{
  const s = byName[n], p = pos[n] || {x:W-60,y:H-30};
  const deployed = s.online_score!=null;
  const glow = (deployed && s.online_score>=D.final-0.01)
    ? `<circle cx="${p.x}" cy="${p.y}" r="${nodeR(s)+5}" fill="none" stroke="#3ecf8e" stroke-opacity=".35" stroke-width="2"/>` : "";
  svg += `<g class="node" data-n="${n.replace(/"/g,'&quot;')}">
    ${glow}
    <circle cx="${p.x}" cy="${p.y}" r="${nodeR(s)}" fill="${nodeColor(s)}" fill-opacity="${deployed?0.9:0.55}" stroke="${deployed?'#8fb0ff':'#57648a'}"/>
    <text x="${p.x}" y="${p.y-nodeR(s)-5}" text-anchor="middle">${n.length>16?n.slice(0,15)+'…':n}</text>
  </g>`;
});
svg += `</svg>`;
$("constBody").innerHTML = svg;

const tip = $("tip");
document.querySelectorAll(".node").forEach(g=>{
  g.addEventListener("mousemove", ev=>{
    const s = byName[g.dataset.n];
    tip.style.display="block";
    tip.style.left=(ev.clientX+14)+"px"; tip.style.top=(ev.clientY+14)+"px";
    tip.innerHTML = `<b>${g.dataset.n}</b><br>
      dream round: ${s.dream_round ?? "—"}<br>
      replay verdict: <span class="num">${s.replay_score!=null?Math.round(s.replay_score*10)/10:"—"}</span><br>
      measured online: <span class="num">${s.online_score!=null?Math.round(s.online_score*100)/100:"not deployed"}</span><br>
      derived from: ${s.derived_from||"—"}<br>
      ${s.descriptor?`<span style="color:var(--dim)">${JSON.stringify(s.descriptor).slice(0,140)}</span>`:""}`;
  });
  g.addEventListener("mouseleave", ()=>tip.style.display="none");
});

/* ---------- score ascent ---------- */
(function(){
  const pts = D.ascent;
  if (!pts.length){ $("ascentBody").innerHTML = `<div class="note">no deployed strategies in the graph for this subject</div>`; return; }
  const W2=560,H2=200,P=36;
  const vals = [D.day1, ...pts.map(p=>p.online), D.final];
  const lo = Math.min(...vals)*0.92, hi = Math.max(...vals)*1.06;
  const X = i => P + i*( (W2-2*P) / Math.max(pts.length,1) );
  const Y = v => H2-P - (v-lo)/(hi-lo)*(H2-2*P);
  let s2 = `<svg viewBox="0 0 ${W2} ${H2}">`;
  // grid
  for(let g=0; g<=4; g++){
    const y = P + g*(H2-2*P)/4, v = hi - g*(hi-lo)/4;
    s2 += `<line x1="${P}" y1="${y}" x2="${W2-P}" y2="${y}" stroke="#1c2334"/><text x="${W2-P+4}" y="${y+4}" fill="#7b8598" font-size="9">${Math.round(v)}</text>`;
  }
  // baseline day1 dotted
  s2 += `<line x1="${P}" y1="${Y(D.day1)}" x2="${W2-P}" y2="${Y(D.day1)}" stroke="#7b8598" stroke-dasharray="4 4" opacity=".4"/>`;
  // path
  let d=`M ${X(0)} ${Y(D.day1)}`;
  pts.forEach((p,i)=> d+=` L ${X(i)} ${Y(p.online)}`);
  if (pts.length) d+=` L ${W2-P} ${Y(D.final)}`;
  s2 += `<path d="${d}" fill="none" stroke="#3ecf8e" stroke-width="2.4" style="filter:drop-shadow(0 0 6px rgba(62,207,142,.6))"/>`;
  pts.forEach((p,i)=>{
    s2 += `<circle cx="${X(i)}" cy="${Y(p.online)}" r="4.5" fill="#3ecf8e"><title>round ${p.round}: ${p.name} → ${p.online}</title></circle>`;
    s2 += `<text x="${X(i)}" y="${Y(p.online)-10}" fill="#d7dde8" font-size="10" text-anchor="middle">${p.online}</text>`;
    s2 += `<text x="${X(i)}" y="${H2-10}" fill="#7b8598" font-size="9" text-anchor="middle">r${p.round}</text>`;
  });
  s2 += `</svg>`;
  $("ascentBody").innerHTML = s2 + `<div class="note" style="margin-top:6px">dotted line = day-1 incumbent; every point was <b>measured in the world</b>, not estimated.</div>`;
})();

/* ---------- dream table ---------- */
(function(){
  const rows = [...STRATS].sort((a,b)=>(b.replay_score||0)-(a.replay_score||0));
  $("dreamTable").innerHTML = `<table>
   <tr><th>strategy</th><th>replay verdict</th><th>online</th><th>round</th></tr>` +
   rows.map(s=>{
     const w = s.online_score!=null && s.online_score>=D.final-0.01;
     const bar = s.replay_score!=null ? `<span class="bar" style="width:${Math.max(3,120*(s.replay_score/maxR))}px"></span> ${Math.round(s.replay_score*10)/10}` : "—";
     return `<tr class="${w?'winrow':''}"><td>${s.name||"(unnamed)"} ${s.online_score!=null?'<span class="badge b-dep">deployed</span>':''} ${w?'<span class="badge b-win">winner</span>':''}</td>
       <td>${bar}</td><td>${s.online_score!=null?Math.round(s.online_score*100)/100:"—"}</td><td>${s.dream_round??"—"}</td></tr>`;
   }).join("") + `</table>`;
})();

/* ---------- episodes explorer ---------- */
(function(){
  const eps = Object.keys(D.episodes);
  if (!eps.length){ $("epTabs").textContent = "no episodes recorded for this subject"; return; }
  $("epTabs").innerHTML = eps.map((e,i)=>`<span class="ep-tab ${i===0?'active':''}" data-e="${e}">${e}</span>`).join("");
  function show(ep){
    const steps = D.episodes[ep];
    const total = steps.reduce((a,s)=>a+(s.score||0),0);
    $("epBody").innerHTML = `<table><tr><th>#</th><th>action</th><th>object</th><th>outcome</th><th>score</th><th>note</th></tr>`+
      steps.map(s=>`<tr><td>${s.i}</td><td><code>${s.action}</code></td><td>${s.object}</td>
        <td class="outcome-${s.outcome}">${s.outcome}</td>
        <td>${s.score!=null?Math.round(s.score*100)/100:""}</td>
        <td class="note">${s.note}</td></tr>`).join("") +
      `</table><div class="note" style="margin-top:8px">episode total: <b>${Math.round(total*100)/100}</b> over ${steps.length} steps</div>`;
  }
  document.querySelectorAll(".ep-tab").forEach(t=>t.addEventListener("click",()=>{
    document.querySelectorAll(".ep-tab").forEach(x=>x.classList.remove("active"));
    t.classList.add("active"); show(t.dataset.e);
  }));
  show(eps[0]);
})();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the interactive dream tree of a subject from the live graph.")
    parser.add_argument("subject")
    parser.add_argument("--out", default=os.path.join("docs", "dream-tree.html"))
    parser.add_argument("--domain", default="island", choices=["island", "workshop"])
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    path = render(args.subject, args.out, domain=args.domain, title=args.title)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
