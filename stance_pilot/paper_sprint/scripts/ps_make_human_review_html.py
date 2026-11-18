"""Build a SINGLE self-contained offline HTML human-review workbench (zero API).

It packages the 18 blind packets (G3-C.1 P01-P08, G3-A P01-P10), the frozen
human rubric, and the GLM *pre-labels* into one HTML file that enforces the
independence protocol:

  Stage A  the human gives a BLIND verdict (GLM answer, issue id and PROVISIONAL
           gold are all hidden) and LOCKS it;
  Stage B  GLM pre-label is revealed and the human records agree/disagree;
  Stage C  identity / PROVISIONAL gold can optionally be unsealed afterwards;
  FR1/FR2 and the specific 19346 disagreement get dedicated adjudication cards.

All human input is saved in browser localStorage and exportable as JSON or as
the coordinator tracking CSV. GLM is decision support only: this file never
writes annotator2 labels itself and never upgrades gold.

Run (cwd = stance_pilot):
    uv run --offline --python 3.11 -m paper_sprint.scripts.ps_make_human_review_html
"""
import json
from pathlib import Path

from paper_sprint.scripts import ps_common as K

ROOT = K.ROOT
HUMAN = K.PS / "human"

PACKET_FILES = [
    "01_problem_statement.txt",
    "02_candidate_patch.diff",
    "03_maintainer_test_patch.diff",
    "04_declared_test_ids.json",
    "05_ci_fail_to_pass.log",
    "06_ci_pass_to_pass_scoped.log",
    "07_ci_pass_to_pass_base_commit.log",
    "08_issue_symptom_probe.log",
]

PROTOCOL = (
    ROOT / "evidence_store_g3c1" / "human_annotation" / "00_annotator_protocol.md"
).read_text(encoding="utf-8")

COHORTS = [
    {
        "key": "G3C1",
        "set": "G3-C.1",
        "n": 8,
        "packet_root": ROOT / "evidence_store_glm_aux",  # GLM records here
        "packets": ROOT / "evidence_store_g3c1" / "human_annotation" / "packets",
        "sealed": ROOT
        / "evidence_store_g3c1"
        / "human_annotation"
        / "SEALED_packet_mapping.json",
    },
    {
        "key": "G3A",
        "set": "G3-A",
        "n": 10,
        "packet_root": ROOT / "evidence_store_glm_aux_g3a",
        "packets": ROOT / "evidence_store_g3c0" / "human_annotation" / "packets",
        "sealed": ROOT
        / "evidence_store_g3c0"
        / "human_annotation"
        / "SEALED_packet_mapping.json",
    },
]

OUT_HTML = HUMAN / "human_review_workbench.html"


def read_packet_files(pdir: Path) -> list[dict]:
    files = []
    for fname in PACKET_FILES:
        fp = pdir / fname
        files.append(
            {
                "name": fname,
                "text": fp.read_text(encoding="utf-8", errors="replace"),
                "sha256": K.sha256_file(fp),
            }
        )
    return files


def collect() -> dict:
    packets = []
    for c in COHORTS:
        sealed = json.loads(c["sealed"].read_text(encoding="utf-8"))
        mapping = sealed["mapping_packet_to_instance"]
        for i in range(1, c["n"] + 1):
            pid = f"P{i:02d}"
            instance = mapping[pid]
            rec = json.loads(
                (c["packet_root"] / "records" / f"{pid}.json").read_text(
                    encoding="utf-8"
                )
            )
            v = rec["verdict"]
            packets.append(
                {
                    "id": f'{c["set"]}::{pid}',
                    "set": c["set"],
                    "packet": pid,
                    "order": len(packets),
                    "instance": instance,
                    "issue": instance.replace("sympy__sympy-", ""),
                    "files": read_packet_files(c["packets"] / pid),
                    "glm": {
                        "label": v.get("label", ""),
                        "confidence": v.get("confidence", ""),
                        "reason": v.get("applicability_reason", ""),
                        "trap": v.get("xfail_flaky_self_added_concern", ""),
                        "notes": v.get("labeling_notes", ""),
                        "decisive": v.get("decisive_failing_test_ids", []) or [],
                        "summaries": v.get("evidence_summary", {}) or {},
                        "tokens_in": rec.get("prompt_tokens"),
                        "tokens_out": rec.get("completion_tokens"),
                        "cost_rmb": rec.get("estimated_cost_rmb"),
                    },
                }
            )
    fr_path = ROOT / "evidence_store_glm_aux" / "glm_focused_review_fr1_fr2.json"
    fr = json.loads(fr_path.read_text(encoding="utf-8"))["focused_review"]
    return {"packets": packets, "fr": fr, "protocol": PROTOCOL}


def build_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=True).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GroundedReview 真人第二标注 / 仲裁工作台（18 盲包）</title>
<style>
:root{
  --bg:#0f1420; --panel:#171e2c; --panel2:#1e2738; --ink:#e7ecf5; --mut:#93a0b8;
  --line:#2a3548; --acc:#4f8cff; --ok:#2fbf71; --rej:#ff5d5d; --need:#f5a524;
  --glm:#9b7bff; --warn:#ffd166; --mono:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,Segoe UI,Roboto,"PingFang SC","Microsoft YaHei",sans-serif}
button{font:inherit;cursor:pointer}
.app{display:grid;grid-template-columns:300px 1fr;grid-template-rows:58px 1fr;height:100vh}
header.top{grid-column:1/3;display:flex;align-items:center;gap:14px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--line)}
header.top h1{font-size:15px;margin:0;font-weight:650;white-space:nowrap}
.progress-wrap{flex:1;max-width:520px}
.progress{height:8px;background:#0c111b;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.progress > i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--acc),var(--ok));transition:width .25s}
.ptext{font-size:12px;color:var(--mut);margin-top:3px}
.top .btns{display:flex;gap:8px;margin-left:auto}
.btn{background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 11px}
.btn:hover{border-color:var(--acc)}
.btn.primary{background:var(--acc);border-color:var(--acc);color:#fff}
.btn.good{background:var(--ok);border-color:var(--ok);color:#062314}
.btn:disabled{opacity:.45;cursor:not-allowed}
aside{background:var(--panel);border-right:1px solid var(--line);overflow-y:auto;padding:10px}
.navgroup{margin-bottom:14px}
.navgroup h3{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:6px 8px}
.navitem{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:8px;color:var(--ink);width:100%;text-align:left;background:transparent;border:1px solid transparent}
.navitem:hover{background:var(--panel2)}
.navitem.active{background:var(--panel2);border-color:var(--line)}
.dot{width:9px;height:9px;border-radius:50%;background:#46536a;flex:0 0 auto}
.dot.locked{background:var(--acc)} .dot.reviewed{background:var(--ok)}
.dot.arb{background:var(--need)}
.navitem .nm{flex:1} .navitem .mini{font-size:11px;color:var(--mut)}
.badge{font-size:11px;font-weight:700;padding:1px 7px;border-radius:20px;border:1px solid var(--line)}
.badge.ACCEPT{color:var(--ok);border-color:var(--ok)}
.badge.REJECT{color:var(--rej);border-color:var(--rej)}
.badge.NEEDS_REVIEW{color:var(--need);border-color:var(--need)}
.badge.glm{color:var(--glm);border-color:var(--glm)}
main{overflow-y:auto;padding:22px 26px 80px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:16px}
.card h2{margin:0 0 4px;font-size:18px}
.sub{color:var(--mut);font-size:13px;margin:0 0 14px}
.note{background:#14203a;border:1px solid #2c4a85;color:#cfe0ff;border-radius:10px;padding:10px 13px;font-size:13px;margin:10px 0}
.warnbox{background:#33291a;border:1px solid #6b5320;color:var(--warn);border-radius:10px;padding:10px 13px;font-size:13px;margin:10px 0}
.glmcard{background:#211a33;border:1px solid #4a3a7a;border-radius:10px;padding:13px 15px;margin-top:12px}
.glmcard h4{margin:0 0 8px;color:#c9b6ff}
.kv{display:grid;grid-template-columns:130px 1fr;gap:6px 12px;font-size:13px;margin:8px 0}
.kv b{color:var(--mut);font-weight:600}
/* evidence viewer */
.evtabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.evtab{background:var(--panel2);border:1px solid var(--line);color:var(--mut);border-radius:7px;padding:5px 9px;font-size:12px}
.evtab.active{color:var(--ink);border-color:var(--acc);background:#1b2740}
.evtools{display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
.evtools input[type=text]{background:#0c111b;border:1px solid var(--line);color:var(--ink);border-radius:7px;padding:5px 9px;font-size:12px}
.evbody{background:#0b0f17;border:1px solid var(--line);border-radius:9px;max-height:430px;overflow:auto}
pre.code{margin:0;font-family:var(--mono);font-size:12px;line-height:1.5;white-space:pre;padding:10px 0}
.ln{display:grid;grid-template-columns:52px 1fr}
.ln > i{color:#3d4a63;font-style:normal;text-align:right;padding-right:12px;user-select:none}
.ln > span{padding-right:14px;white-space:pre}
.l-fail{background:#3a1718;color:#ffb3b3;display:block}
.l-pass{color:#86d9a8}
.l-err{background:#3a1718;color:#ff9b9b;display:block}
.l-warn{color:var(--warn)}
.diff-add{color:#86d9a8}.diff-del{color:#ff9b9b}.diff-hunk{color:#7db0ff}
.evmeta{font-size:11px;color:var(--mut);margin-top:6px;font-family:var(--mono);word-break:break-all}
/* forms */
fieldset{border:1px solid var(--line);border-radius:10px;margin:12px 0;padding:12px 14px}
legend{padding:0 6px;color:var(--mut);font-size:12px}
label.opt{display:inline-flex;align-items:center;gap:7px;margin:4px 16px 4px 0;padding:8px 12px;border:1px solid var(--line);border-radius:9px;cursor:pointer;min-width:120px}
label.opt.sel{border-color:var(--acc);background:#16233c}
textarea,input[type=text],input[type=date],input[type=number],select{width:100%;background:#0c111b;border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:8px 10px;font:inherit}
textarea{min-height:64px;resize:vertical;font-family:var(--mono);font-size:12.5px}
.fld{margin:10px 0}.fld label{display:block;font-size:12px;color:var(--mut);margin-bottom:4px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.chk{display:flex;gap:9px;align-items:flex-start;font-size:13px;margin:10px 0}
.locked-overlay{position:relative}
.locked-overlay.locked .lockable{pointer-events:none;opacity:.92}
.tag{font-size:11px;padding:2px 8px;border-radius:6px;background:#132a20;color:var(--ok);border:1px solid var(--ok)}
table.grid{width:100%;border-collapse:collapse;font-size:12.5px}
table.grid th,table.grid td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
table.grid th{background:var(--panel2);color:var(--mut);font-weight:600}
.muted{color:var(--mut)} .mono{font-family:var(--mono)}
.stagebar{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 14px}
.stagebar .s{font-size:12px;color:var(--mut);border:1px solid var(--line);border-radius:20px;padding:3px 12px}
.stagebar .s.on{color:#fff;border-color:var(--acc);background:var(--acc)}
.sigbox{border:1px dashed #4f8cff;border-radius:10px;padding:14px;margin-top:10px}
@media print{aside,header.top .btns,.evtools,.no-print{display:none!important}
.app{display:block;height:auto}.app main{overflow:visible;padding:0}body{background:#fff;color:#000}}
</style>
</head>
<body>
<div class="app">
<header class="top">
  <h1>GroundedReview · 真人第二标注/仲裁工作台</h1>
  <div class="progress-wrap">
    <div class="progress"><i id="pbar"></i></div>
    <div class="ptext" id="ptext">进度加载中…</div>
  </div>
  <div class="btns no-print">
    <button class="btn" id="btnImport">导入 JSON</button>
    <button class="btn" id="btnExportJson">导出 JSON</button>
    <button class="btn" id="btnExportCsv">导出 tracking CSV</button>
    <button class="btn primary" id="btnPrint">打印 / 存 PDF</button>
  </div>
</header>
<aside id="nav"></aside>
<main id="main"></main>
</div>
<input type="file" id="fileInput" accept="application/json" style="display:none"/>
<script>
const DATA = __DATA__;
const LSKEY = "gr_human_workbench_v1";
const LABELS = ["ACCEPT","REJECT","NEEDS_REVIEW"];
let state = load();
let view = "overview";

function blankPacket(){return {draft:{},blind:null, glmReview:null, unblinded:false, arb:null};}
function blankFR(){return {blind:null, glmReview:null};}
function load(){
  let s;
  try{s = JSON.parse(localStorage.getItem(LSKEY));}catch(e){s=null;}
  if(!s){s={packets:{}, fr:{FR1:blankFR(),FR2:blankFR()}, c19346:null, sign:null, note:""};}
  DATA.packets.forEach(p=>{ if(!s.packets[p.id]) s.packets[p.id]=blankPacket(); });
  ["FR1","FR2"].forEach(k=>{ if(!s.fr[k]) s.fr[k]=blankFR(); });
  if(!s.c19346) s.c19346=null; if(!s.sign) s.sign=null;
  return s;
}
function save(){localStorage.setItem(LSKEY, JSON.stringify(state)); refreshProgress();}
function pById(id){return DATA.packets.find(p=>p.id===id);}
function st(id){return state.packets[id];}
function esc(t){return (t==null?"":String(t)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

function refreshProgress(){
  const ps=DATA.packets;
  const locked=ps.filter(p=>st(p.id).blind).length;
  const reviewed=ps.filter(p=>st(p.id).glmReview).length;
  const arb=ps.filter(p=>needsArb(p.id)).length;
  document.getElementById("pbar").style.width=(locked/ps.length*100)+"%";
  document.getElementById("ptext").textContent=
    `盲判锁定 ${locked}/${ps.length} · GLM核对 ${reviewed}/${ps.length} · 待第三人仲裁 ${arb}`;
}
function needsArb(id){const p=pById(id),s=st(id); if(!s.blind||!s.glmReview)return false;
  return s.blind.label!==p.glm.label || s.glmReview.agree!=="yes";}

/* ---------------- navigation ---------------- */
function renderNav(){
  const groups={};
  DATA.packets.forEach(p=>{(groups[p.set]=groups[p.set]||[]).push(p);});
  let h="";
  h+=`<button class="navitem ${view==="overview"?"active":""}" data-go="overview"><span class="dot reviewed"></span><span class="nm">总览 / 签名 / 导出</span></button>`;
  h+=`<button class="navitem ${view==="fr"?"active":""}" data-go="fr"><span class="dot ${state.fr.FR1.blind&&state.fr.FR2.blind?"reviewed":""}"></span><span class="nm">FR1 / FR2 专项判定</span></button>`;
  h+=`<button class="navitem ${view==="c19346"?"active":""}" data-go="c19346"><span class="dot ${state.c19346&&state.c19346.blind?"reviewed":""}"></span><span class="nm">19346 专项仲裁</span><span class="mini">分歧</span></button>`;
  for(const set of Object.keys(groups)){
    h+=`<div class="navgroup"><h3>${set}</h3>`;
    groups[set].forEach(p=>{
      const s=st(p.id); let cls="",mini="待盲判";
      if(s.glmReview){cls="reviewed";mini="已核对GLM";} else if(s.blind){cls="locked";mini="待揭示GLM";}
      if(needsArb(p.id)){cls="arb";if(s.glmReview)mini="待仲裁";}
      h+=`<button class="navitem ${view===p.id?"active":""}" data-go="${p.id}">
        <span class="dot ${cls}"></span><span class="nm">${p.packet}</span>
        <span class="mini">${mini}</span></button>`;
    });
    h+=`</div>`;
  }
  const nav=document.getElementById("nav"); nav.innerHTML=h;
  nav.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>{view=b.dataset.go;render();window.scrollTo(0,0);});
}

/* ---------------- evidence viewer ---------------- */
let evState={};
function renderEvidence(p){
  const ev=evState[p.id]||(evState[p.id]={tab:p.files[0].name, failOnly:false, q:""});
  const tabs=p.files.map(f=>`<button class="evtab ${ev.tab===f.name?"active":""}" data-f="${f.name}">${f.name.replace(/^0[0-9]_/,"").slice(0,26)}</button>`).join("");
  const f=p.files.find(x=>x.name===ev.tab)||p.files[0];
  const isLog=f.name.endsWith(".log"); const isDiff=f.name.endsWith(".diff");
  let lines=f.text.split(/\r?\n/);
  if(ev.failOnly&&isLog){lines=lines.filter(l=>/FAILED|ERROR|AssertionError|=== FAILURES|^E  |xfail/i.test(l));}
  if(ev.q.trim()){const q=ev.q.toLowerCase();lines=lines.filter(l=>l.toLowerCase().includes(q));}
  const html=lines.map((l,i)=>{
    let c="";
    if(isLog){ if(/FAILED|^FAILED|AssertionError|=== FAILURES/.test(l))c="l-fail";
      else if(/\bERROR\b|^E  /.test(l))c="l-err";
      else if(/PASSED|\d+ passed/.test(l))c="l-pass"; else if(/warning/i.test(l))c="l-warn";
    } else if(isDiff){ if(l.startsWith("+"))c="diff-add"; else if(l.startsWith("-"))c="diff-del"; else if(l.startsWith("@@"))c="diff-hunk"; }
    return `<div class="ln"><i>${i+1}</i><span class="${c}">${esc(l)||" "}</span></div>`;
  }).join("");
  return `<div class="evtabs">${tabs}</div>
    <div class="evtools">
      <input type="text" placeholder="在本文件内过滤（如 FAILED / test_set）" value="${esc(ev.q)}" data-q style="width:300px"/>
      ${isLog?`<label class="chk" style="margin:0"><input type="checkbox" data-fail ${ev.failOnly?"checked":""}/>只看失败/错误行</label>`:""}
      <span class="muted" style="font-size:12px">${lines.length} 行</span>
    </div>
    <div class="evbody"><pre class="code">${html}</pre></div>
    <div class="evmeta">${f.name} · sha256 ${f.sha256}</div>`;
}

/* ---------------- packet view ---------------- */
function opt(name,val,cur,disabled){return `<label class="opt ${cur===val?"sel":""}">
  <input type="radio" name="${name}" value="${val}" ${cur===val?"checked":""} ${disabled?"disabled":""}/>${val==="ACCEPT"?"接受 (ACCEPT)":val==="REJECT"?"拒绝 (REJECT)":"证据不足 (NEEDS_REVIEW)"}</label>`;}

function renderPacket(p){
  const s=st(p.id), locked=!!s.blind, reviewed=!!s.glmReview;
  const b=s.blind||s.draft||{};
  let h=`<div class="card"><h2>${p.set} · ${p.packet} <span class="muted" style="font-size:13px">盲包证据评审</span></h2>
    <div class="stagebar">
      <span class="s ${!locked?"on":""}">① 盲态独立判定${locked?" ✓":""}</span>
      <span class="s ${locked&&!reviewed?"on":""}">② 揭示并核对 GLM${reviewed?" ✓":""}</span>
      <span class="s ${s.unblinded?"on":""}">③ 解封身份/gold（可选）${s.unblinded?" ✓":""}</span>
    </div>
    ${!locked?`<div class="note"><b>盲态要求：</b>此时不显示 GLM 答案、真实 issue 号与 PROVISIONAL gold。请只依据下列 9 个证据文件，按 rubric 独立判断。完成后点“锁定”，锁定后 GLM 答案才会出现，且你的盲判不可再改（保证第二标注独立性）。</div>`
      :`<div class="warnbox">盲判已于 ${esc(b.ts)} 锁定。第二标注 = <b>${esc(b.label)}</b>。锁定后的判定不会因看到 GLM 而改变；若你发现自己看错证据，请在核对区说明并提交第三人仲裁，而不是回改。</div>`}
    <details ${locked?"":"open"} style="margin-bottom:6px"><summary class="muted" style="cursor:pointer">判定 rubric（与 GLM、annotator#1 同一标准）</summary>
      <pre class="code" style="white-space:pre-wrap;background:#0b0f17;border:1px solid var(--line);border-radius:9px;padding:10px;font-size:12px">${esc(DATA.protocol)}</pre></details>
    <h4 style="margin:14px 0 6px">证据文件（点击切换；红色=失败，绿色=通过）</h4>
    <div id="ev">${renderEvidence(p)}</div>
  </div>`;

  // stage A blind form
  h+=`<div class="card"><h2>① 我的独立（盲态）判定</h2>
   <div class="lockable ${locked?"locked":""}">
   <fieldset><legend>结论</legend>${LABELS.map(l=>opt("blind_"+p.id,l,b.label,locked)).join("")}</fieldset>
   <div class="fld"><label>决定性失败测试 id（逐条；无则留空）</label>
     <textarea data-k="decisive" ${locked?"disabled":""}>${esc(b.decisive||"")}</textarea></div>
   <div class="fld"><label>判定理由（REJECT 须说明每个失败为何“适用”，而非预存/xfail/flaky/自加测试）</label>
     <textarea data-k="reason" ${locked?"disabled":""}>${esc(b.reason||"")}</textarea></div>
   <div class="row2">
     <div class="fld"><label>xfail / flaky / 自加测试 顾虑</label>
       <select data-k="trapyn" ${locked?"disabled":""}>
         <option value="" ${!b.trapyn?"selected":""}>—</option>
         <option value="no" ${b.trapyn==="no"?"selected":""}>无</option>
         <option value="yes" ${b.trapyn==="yes"?"selected":""}>有（说明）</option></select></div>
     <div class="fld"><label>置信度 / 用时(分钟)</label>
       <div style="display:flex;gap:8px">
       <select data-k="conf" ${locked?"disabled":""} style="flex:1">
         ${["","high","medium","low"].map(x=>`<option ${b.conf===x?"selected":""}>${x}</option>`).join("")}</select>
       <input type="number" min="0" data-k="mins" placeholder="分钟" value="${esc(b.mins||"")}" ${locked?"disabled":""} style="width:110px"/></div></div>
   </div>
   <div class="fld"><label>顾虑说明 / 需要第三人关注的点</label><textarea data-k="trapnote" ${locked?"disabled":""}>${esc(b.trapnote||"")}</textarea></div>
   <label class="chk"><input type="checkbox" data-k="indep" ${b.indep?"checked":""} ${locked?"disabled":""}/>
     我确认：此判定为本人独立阅读冻结证据所得，未参考任何 LLM / GLM 输出、未查阅网络或 issue 跟踪器、未与流水线作者商量。</label>
   ${!locked?`<button class="btn good" id="lockBtn">锁定我的独立判定（随后显示 GLM）</button>`
     :`<span class="tag">已锁定 · annotator2 verdict = ${esc(b.label)}</span>`}
   </div></div>`;

  // stage B GLM reveal
  if(locked){
    const g=p.glm, r=s.glmReview||{};
    h+=`<div class="card"><h2>② 揭示并核对 GLM-4.6 预标注</h2>
      <div class="glmcard">
        <h4>GLM 预标注（AI，仅决策支持，不是 annotator#2） <span class="badge glm">${esc(g.label)}</span>
          <span class="muted" style="font-weight:400">置信 ${esc(g.confidence)} · ${g.tokens_in}/${g.tokens_out} tok · 约 ¥${esc(g.cost_rmb)}</span></h4>
        <div class="kv">
          <b>GLM 理由</b><span>${esc(g.reason)}</span>
          <b>决定性失败 id</b><span class="mono">${g.decisive.length?esc(g.decisive.join("; ")):"—"}</span>
          <b>xfail/flaky/自加</b><span>${esc(g.trap)}</span>
          <b>F2P 摘要(05)</b><span class="mono">${esc(g.summaries.f2p_after_summary_line||"")}</span>
          <b>P2P 摘要(06)</b><span class="mono">${esc(g.summaries.p2p_after_summary_line||"")}</span>
          <b>BASE 摘要(07)</b><span class="mono">${esc(g.summaries.p2p_base_summary_line||"")}</span>
          <b>给复核者备注</b><span>${esc(g.notes)}</span>
        </div>
      </div>
      ${reviewed?`<div class="warnbox">GLM 核对已记录：你<b>${r.agree==="yes"?"同意":r.agree==="no"?"不同意（认为 GLM 错）":"部分同意"}</b>。${needsArb(p.id)?`你的盲判(${esc(b.label)}) 与 GLM(${esc(g.label)}) 不一致 → 自动转入第三人仲裁。`:""}</div>`:""}
      <fieldset ${reviewed?"disabled":""}><legend>你的盲判与 GLM 是否一致？</legend>
        <label class="opt ${r.agree==="yes"?"sel":""}"><input type="radio" name="agr" value="yes" ${r.agree==="yes"?"checked":""}/>一致（GLM 正确）</label>
        <label class="opt ${r.agree==="partial"?"sel":""}"><input type="radio" name="agr" value="partial" ${r.agree==="partial"?"checked":""}/>结论同、理由有保留</label>
        <label class="opt ${r.agree==="no"?"sel":""}"><input type="radio" name="agr" value="no" ${r.agree==="no"?"checked":""}/>不一致（GLM 错）</label>
      </fieldset>
      <div class="fld" ${reviewed?"":""}><label>核对说明（不同意时务必指出 GLM 读错了哪个文件/哪一行）</label>
        <textarea data-gr ${reviewed?"disabled":""}>${esc(r.note||"")}</textarea></div>
      ${!reviewed?`<button class="btn primary" id="reviewBtn">记录对 GLM 的核对</button>`
        :`<span class="tag">已记录${needsArb(p.id)?" · 状态：NEEDS_ARBITRATION":""}</span>`}
      `;
    if(needsArb(p.id)){
      const a=s.arb||{};
      h+=`<fieldset style="margin-top:14px;border-color:#6b5320"><legend style="color:var(--warn)">第三人仲裁（须为另一名资深真人，不见模型输出；可留空待其本人填写）</legend>
        <div class="fld"><label>仲裁结论</label><select data-arb-k="verdict">
          <option value="" ${!a.verdict?"selected":""}>待仲裁</option>
          ${LABELS.map(l=>`<option ${a.verdict===l?"selected":""}>${l}</option>`).join("")}</select></div>
        <div class="fld"><label>仲裁理由（采纳哪一方、关键证据行）</label><textarea data-arb-k="reason">${esc(a.reason||"")}</textarea></div>
        <div class="row2"><div class="fld"><label>仲裁人姓名</label><input type="text" data-arb-k="name" value="${esc(a.name||"")}"/></div>
        <div class="fld"><label>日期</label><input type="date" data-arb-k="date" value="${esc(a.date||"")}"/></div></div></fieldset>`;
    }
    h+=`</div>`;
    // stage C unblind
    h+=`<div class="card"><h2>③ 解封真实身份与 PROVISIONAL gold（可选）</h2>
      <p class="sub">此操作仅用于核对，解封发生在你独立判定之后，不影响上面的 annotator2 盲判。</p>`;
    if(!s.unblinded){h+=`<button class="btn" id="unblindBtn">我已完成盲判与核对，解封 issue 身份 / gold</button>`;}
    else{
      h+=`<table class="grid"><tr><th>真实 issue</th><th>PROVISIONAL oracle gold</th><th>你的盲判(annotator2)</th><th>GLM</th>
            <th>你 vs gold</th><th>GLM vs gold</th></tr><tr>
        <td class="mono">sympy__sympy-${esc(p.issue)}</td><td><span class="badge ${p._oracle}">${esc(p._oracle)}</span></td>
        <td>${esc(b.label)}</td><td>${esc(g.label)}</td>
        <td>${b.label===p._oracle?"<span style='color:var(--ok)'>一致</span>":"<span style='color:var(--rej)'>不一致</span>"}</td>
        <td>${g.label===p._oracle?"<span style='color:var(--ok)'>一致</span>":"<span style='color:var(--rej)'>不一致</span>"}</td></tr></table>`;
    }
    h+=`</div>`;
  }
  return h;
}

/* ---------------- FR view ---------------- */
const FRMETA={
  FR1:{key:"FR1_19495",title:"FR1 · 19495：测试仪器修正 vs 事后重定义 oracle",
    q:"FAIL_TO_PASS 中 test_subs_CondSet 的变化，究竟只是对【测试仪器/旧断言】的修正，还是因为看到候选补丁能通过，就选择性地、事后重定义了可接受性标准？",
    choices:[["instrument_fix","仅测试仪器修正（oracle 标准未变）"],["oracle_redefinition","事后选择性重定义了 oracle"],["unclear","证据不足/无法判定"]]},
  FR2:{key:"FR2_14248_15875",title:"FR2 · 14248 与 15875：同一把尺子？",
    q:"两个 REJECT 是否适用同一条可接受性标准？还是不同失败模式其实意味着应在扩样前分别预注册的不同 oracle 规则？",
    choices:[["same_standard","同一标准"],["different_standards","应拆分为不同标准"],["unclear","证据不足"]]}
};
function renderFR(){
  let h=`<div class="card"><h2>FR1 / FR2 专项判定（G3-C.1）</h2>
    <p class="sub">与盲包相同：先在<b>看不到 GLM 意见</b>时独立选择并锁定，再揭示 GLM、记录同意与否。两项均需回答“是否需要修订 rubric”。</p></div>`;
  for(const fk of ["FR1","FR2"]){
    const m=FRMETA[fk], s=state.fr[fk], g=DATA.fr[m.key], b=s.blind, locked=!!b, rev=!!s.glmReview;
    h+=`<div class="card"><h2>${m.title}</h2><p class="sub">${m.q}</p>`;
    h+=`<fieldset ${locked?"":"open"}><legend>① 我的独立结论</legend>${m.choices.map(c=>
      `<label class="opt ${b&&b.choice===c[0]?"sel":""}"><input type="radio" name="fr_${fk}" value="${c[0]}" ${b&&b.choice===c[0]?"checked":""} ${locked?"disabled":""}/>${c[1]}</label>`).join("")}</fieldset>
      <div class="fld"><label>理由</label><textarea data-frblind="${fk}" ${locked?"disabled":""}>${esc(b?b.reason:"")}</textarea></div>
      <div class="fld"><label>是否需要修订 rubric？</label>
        <select data-framend="${fk}" ${locked?"disabled":""}><option value="" ${!b||!b.amend?"selected":""}>—</option>
        <option value="no" ${b&&b.amend==="no"?"selected":""}>否</option><option value="yes" ${b&&b.amend==="yes"?"selected":""}>是（说明）</option></select></div>
      ${!locked?`<button class="btn good" data-frlock="${fk}">锁定独立结论</button>`:`<span class="tag">已锁定：${esc(b.choice)} · 修订rubric=${esc(b.amend)}</span>`}`;
    if(locked){
      h+=`<div class="glmcard"><h4>GLM 专项意见（AI） <span class="badge glm">${esc(g.choice)}</span> <span class="muted">置信 ${esc(g.confidence)}</span></h4>
        <div class="kv"><b>理由</b><span>${esc(g.reason)}</span><b>需修订 rubric</b><span>${esc(g.rubric_amendment_needed)}</span></div></div>`;
      if(!rev){h+=`<fieldset><legend>② 是否同意 GLM</legend>
        <label class="opt"><input type="radio" name="fragr_${fk}" value="yes"/>同意</label>
        <label class="opt"><input type="radio" name="fragr_${fk}" value="partial"/>保留</label>
        <label class="opt"><input type="radio" name="fragr_${fk}" value="no"/>不同意</label></fieldset>
        <div class="fld"><label>说明</label><textarea data-frgr="${fk}"></textarea></div>
        <button class="btn primary" data-frreview="${fk}">记录核对</button>`;}
      else{h+=`<div class="warnbox">已记录：你${s.glmReview.agree==="yes"?"同意":s.glmReview.agree==="no"?"不同意":"保留"}。${esc(s.glmReview.note||"")}</div>`;}
    }
    h+=`</div>`;
  }
  return h;
}

/* ---------------- 19346 special ---------------- */
function render19346(){
  const p=pById("G3-C.1::P03"), s=state.c19346, g=p.glm, b=s?s.blind:null;
  const cats=[["declared_regression","在声明集内的真实回归（应 REJECT）"],
    ["undeclared_authoritative","未声明但属维护者权威验收测试失败（倾向 REJECT，需说明）"],
    ["preexisting","base 即失败/环境问题（非回归）"],
    ["xfail_flaky","xfail/flaky/自加测试陷阱"],
    ["other","其他（说明）"]];
  let h=`<div class="card"><h2>专项仲裁：19346（G3-C.1 P03）—— 全包唯一 GLM↔gold 分歧</h2>
   <p class="sub">GLM 给 <span class="badge glm">REJECT</span>，而 PROVISIONAL oracle 给 <span class="badge ACCEPT">ACCEPT</span>。请在解封状态下依据证据做最终归类。</p>
   <div class="warnbox"><b>分歧焦点：</b>候选补丁的 <code>_print_set</code> 对空集输出 <code>'{}'</code>，维护者测试补丁新增的权威 <code>test_set</code> 断言 <code>srepr(set())=='set()'</code>，在完整日志中确实 FAIL；但该 <code>test_set</code> <b>不在</b> <code>04_declared_test_ids.json</code> 的声明 F2P 集合内（声明 F2P 仅 <code>test_dict</code>，且通过），故 oracle 计 41 项检查 / 0 失败 → ACCEPT。GLM 还把它误称为“base 通过的 P2P 回归”，而该测试在 base 并不存在。</div>
   <div class="note">请依次核对：(a) <code>test_set</code> 是否在 04 声明集内？ (b) 它在 07 base 日志是否存在/是否失败？ (c) 它是 xfail/flaky/自加测试，还是维护者权威验收？可在下方按钮打开 P03 证据。</div>
   <button class="btn" id="goP03">打开 P03 证据包</button></div>
   <div class="card"><h2>仲裁结论</h2>
   <fieldset ${b?"disabled":""}><legend>最终人类裁决（建议由资深真人/仲裁者给出）</legend>
     ${LABELS.map(l=>`<label class="opt ${b&&b.label===l?"sel":""}"><input type="radio" name="a346label" value="${l}" ${b&&b.label===l?"checked":""}/>${l}</label>`).join("")}</fieldset>
   <div class="fld"><label>(a) test_set 是否在 04 声明集内？</label>
     <select data-c="declared" ${b?"disabled":""}><option value="" ${!b?"selected":""}>—</option><option ${b&&b.declared==="no"?"selected":""} value="no">否（未声明）</option><option ${b&&b.declared==="yes"?"selected":""} value="yes">是（已声明）</option></select></div>
   <div class="fld"><label>(b) 该测试在 base（07）的状态</label>
     <select data-c="basestate" ${b?"disabled":""}><option value="" ${!b?"selected":""}>—</option>
     <option ${b&&b.basestate==="absent"?"selected":""} value="absent">base 不存在该测试</option>
     <option ${b&&b.basestate==="fail"?"selected":""} value="fail">base 即失败（预存）</option>
     <option ${b&&b.basestate==="pass"?"selected":""} value="pass">base 通过（真回归）</option></select></div>
   <div class="fld"><label>(c) 归类</label><select data-c="category" ${b?"disabled":""}>
     <option value="">—</option>${cats.map(c=>`<option value="${c[0]}" ${b&&b.category===c[0]?"selected":""}>${c[1]}</option>`).join("")}</select></div>
   <div class="fld"><label>裁决理由（引用具体日志行/测试 id）</label><textarea data-c="reason" ${b?"disabled":""}>${esc(b?b.reason:"")}</textarea></div>
   <div class="row2"><div class="fld"><label>裁决人</label><input type="text" data-c="name" value="${esc(b?b.name:"")}" ${b?"disabled":""}/></div>
   <div class="fld"><label>日期</label><input type="date" data-c="date" value="${esc(b?b.date:"")}" ${b?"disabled":""}/></div></div>
   ${!b?`<button class="btn good" id="lock346">锁定 19346 仲裁</button>`:`<span class="tag">已锁定：${esc(b.label)} / ${esc(b.category)}</span>`}
   </div>`;
  return h;
}

/* ---------------- overview ---------------- */
function renderOverview(){
  const ps=DATA.packets; let agree=0,dis=0,lockN=0,arbN=0;
  const rows=ps.map(p=>{const s=st(p.id),b=s.blind,g=p.glm;
    const ok=!!(b&&s.glmReview&&b.label===g.label&&s.glmReview.agree!=="no");
    if(b){lockN++; if(s.glmReview){ok?agree++:dis++;}}
    if(needsArb(p.id))arbN++;
    return `<tr><td>${p.set}</td><td>${p.packet}</td>
      <td>${b?`<span class="badge ${b.label}">${b.label}</span>`:'<span class="muted">—</span>'}</td>
      <td><span class="badge glm">${g.label}</span></td>
      <td>${b?(s.glmReview?(ok?"<span style='color:var(--ok)'>一致</span>":"<span style='color:var(--rej)'>分歧</span>"):"<span class='muted'>待核对</span>"):"<span class='muted'>待盲判</span>"}</td>
      <td>${needsArb(p.id)?(s.arb&&s.arb.verdict?`<span class="badge ${s.arb.verdict}">${s.arb.verdict}</span>`:"<span style='color:var(--need)'>待仲裁</span>"):"—"}</td>
      <td>${s.unblinded?esc(p.issue):"<span class='muted'>未解封</span>"}</td></tr>`;}).join("");
  const frDone=(state.fr.FR1.blind&&state.fr.FR2.blind), cDone=!!(state.c19346&&state.c19346.blind);
  const sg=state.sign||{};
  let h=`<div class="card"><h2>总览</h2>
    <div class="kv" style="grid-template-columns:220px 1fr">
      <b>盲判已锁定</b><span>${lockN}/18</span>
      <b>与 GLM 结论一致(已核对)</b><span>${agree} ；分歧 ${dis}</span>
      <b>自动进入第三人仲裁</b><span>${arbN}</span>
      <b>FR1/FR2 专项</b><span>${frDone?"已完成":"未完成"}</span>
      <b>19346 专项仲裁</b><span>${cDone?("已锁定 "+state.c19346.blind.label):"未完成"}</span>
    </div>
    <p class="sub">提示：GLM 是 AI 预标注，仅用于降低人工核对成本；“一致/分歧”不改变 Gold，Gold 仍为 PROVISIONAL，直到真人第二标注 + 仲裁回填。</p>
    <table class="grid"><thead><tr><th>集合</th><th>盲包</th><th>你的盲判(A2)</th><th>GLM</th><th>核对</th><th>仲裁</th><th>issue(解封后)</th></tr></thead><tbody>${rows}</tbody></table>
  </div>
  <div class="card"><h2>签署与导出</h2>
    <div class="sigbox">
      <div class="fld"><label>第二标注人姓名（签名）</label><input type="text" id="signName" value="${esc(sg.name||"")}"/></div>
      <div class="row2"><div class="fld"><label>角色 / 资质</label><input type="text" id="signRole" value="${esc(sg.role||"")}"/></div>
      <div class="fld"><label>日期</label><input type="date" id="signDate" value="${esc(sg.date||"")}"/></div></div>
      <label class="chk"><input type="checkbox" id="signAttest" ${sg.attest?"checked":""}/>
        我声明以上 18 个盲包标签均为本人依据冻结 CI 独立做出，未参考任何模型输出；分歧项已按协议提交第三人仲裁；FR1/FR2 与 19346 专项意见为本人真实判断。</label>
      <button class="btn primary" id="saveSign">保存签署信息</button>
    </div>
    <p class="sub" style="margin-top:12px">数据仅保存在本机浏览器 localStorage。完成后请点右上角：<b>导出 JSON</b>（完整存档）与 <b>导出 tracking CSV</b>（可回填 human_review_tracking.csv）。用“打印/存 PDF”可生成线下签署版。</p>
  </div>`;
  return h;
}

/* ---------------- render & wire ---------------- */
function render(){
  const m=document.getElementById("main");
  if(view==="overview")m.innerHTML=renderOverview();
  else if(view==="fr")m.innerHTML=renderFR();
  else if(view==="c19346")m.innerHTML=render19346();
  else{const p=pById(view); m.innerHTML=renderPacket(p);}
  renderNav(); refreshProgress(); wire();
}

function wire(){
  // evidence tabs / filters (packet view)
  document.querySelectorAll("#ev .evtab").forEach(t=>t.onclick=()=>{const p=pById(view);evState[p.id].tab=t.dataset.f;render();});
  const q=document.querySelector("#ev [data-q]"); if(q)q.oninput=e=>{evState[view].q=e.target.value;scheduleEv();};
  const fo=document.querySelector("#ev [data-fail]"); if(fo)fo.onchange=e=>{evState[view].failOnly=e.target.checked;render();};

  if(view!=="overview"&&view!=="fr"&&view!=="c19346"){
    const p=pById(view),s=st(p.id);
    document.querySelectorAll("[data-k]").forEach(el=>{
      const handler=()=>{ if(s.blind)return; s.draft=s.draft||{};
        s.draft[el.dataset.k]=el.type==="checkbox"?el.checked:el.value; save();};
      el.oninput=handler; el.onchange=handler;
    });
    const lb=document.getElementById("lockBtn");
    if(lb)lb.onclick=()=>{
      const lab=document.querySelector(`input[name="blind_${p.id}"]:checked`);
      const reason=document.querySelector('[data-k="reason"]').value.trim();
      const indep=document.querySelector('[data-k="indep"]').checked;
      if(!lab)return alert("请先选择 ACCEPT / REJECT / NEEDS_REVIEW");
      if(!reason)return alert("请填写判定理由");
      if(!indep)return alert("请勾选独立性确认");
      const get=k=>{const e=document.querySelector(`[data-k="${k}"]`);return e?e.value:"";};
      const chk=document.querySelector('[data-k="indep"]').checked;
      s.blind={label:lab.value,decisive:get("decisive"),reason,trapyn:get("trapyn"),
        trapnote:get("trapnote"),conf:get("conf"),mins:get("mins"),indep:chk,ts:new Date().toISOString()};
      s.draft={};
      save();render();
    };
    const rb=document.getElementById("reviewBtn");
    if(rb)rb.onclick=()=>{const ag=document.querySelector(`input[name="agr"]:checked`);
      if(!ag)return alert("请选择是否同意 GLM");
      s.glmReview={agree:ag.value,note:document.querySelector("[data-gr]").value,ts:new Date().toISOString()};
      if(s.blind.label!==p.glm.label||ag.value!=="yes"){if(!s.arb)s.arb={};}
      save();render();};
    const ub=document.getElementById("unblindBtn");
    if(ub)ub.onclick=()=>{s.unblinded=true;save();render();};
  }

  if(view==="fr"){
    document.querySelectorAll("[data-frlock]").forEach(b=>b.onclick=()=>{const fk=b.dataset.frlock;
      const ch=document.querySelector(`input[name="fr_${fk}"]:checked`);
      const reason=document.querySelector(`[data-frblind="${fk}"]`).value.trim();
      if(!ch)return alert("请选择结论"); if(!reason)return alert("请填写理由");
      state.fr[fk].blind={choice:ch.value,reason,amend:document.querySelector(`[data-framend="${fk}"]`).value,ts:new Date().toISOString()};
      save();render();});
    document.querySelectorAll("[data-frreview]").forEach(b=>b.onclick=()=>{const fk=b.dataset.frreview;
      const ag=document.querySelector(`input[name="fragr_${fk}"]:checked`); if(!ag)return alert("请选择是否同意");
      state.fr[fk].glmReview={agree:ag.value,note:document.querySelector(`[data-frgr="${fk}"]`).value,ts:new Date().toISOString()};
      save();render();});
  }

  if(view==="c19346"){
    const go=document.getElementById("goP03"); if(go)go.onclick=()=>{view="G3-C.1::P03";render();};
    const lk=document.getElementById("lock346");
    if(lk)lk.onclick=()=>{const lab=document.querySelector(`input[name="a346label"]:checked`);
      if(!lab)return alert("请选择最终裁决");
      const reason=document.querySelector('[data-c="reason"]').value.trim(); if(!reason)return alert("请引用证据并写明理由");
      const g=k=>document.querySelector(`[data-c="${k}"]`).value;
      state.c19346={blind:{label:lab.value,declared:g("declared"),basestate:g("basestate"),
        category:g("category"),reason,name:g("name"),date:g("date"),ts:new Date().toISOString()}};
      save();render();};
  }

  if(view==="overview"){
    const sv=document.getElementById("saveSign");
    if(sv)sv.onclick=()=>{state.sign={name:signName.value,role:signRole.value,date:signDate.value,
      attest:document.getElementById("signAttest").checked,ts:new Date().toISOString()};save();alert("已保存签署信息");};
  }
  // arb live fields
  document.querySelectorAll("[data-arb-k]").forEach(el=>el.oninput=()=>{const p=pById(view);const s=st(p.id);
    if(!s.arb)s.arb={verdict:"",reason:"",name:"",date:""};s.arb[el.dataset.arbK]=el.value;save();});
}
let evTimer=null;function scheduleEv(){clearTimeout(evTimer);evTimer=setTimeout(()=>{
  // re-render only the evidence body cheaply: full render keeps scroll; acceptable
  const p=pById(view);const host=document.getElementById("ev");if(host)host.innerHTML=renderEvidence(p);wireEvOnly();},250);}
function wireEvOnly(){document.querySelectorAll("#ev .evtab").forEach(t=>t.onclick=()=>{const p=pById(view);evState[p.id].tab=t.dataset.f;render();});
  const q=document.querySelector("#ev [data-q]");if(q){q.focus();q.oninput=e=>{evState[view].q=e.target.value;scheduleEv();};}
  const fo=document.querySelector("#ev [data-fail]");if(fo)fo.onchange=e=>{evState[view].failOnly=e.target.checked;render();};}

/* ---------------- export / import ---------------- */
document.getElementById("btnExportJson").onclick=()=>download("human_review_workbench.json",JSON.stringify(state,null,2),"application/json");
document.getElementById("btnExportCsv").onclick=()=>{
  const oracle={};DATA.packets.forEach(p=>oracle[p.id]=p._oracle);
  let lines=["set,packet,issue_revealed_after_unblind,oracle_gold_provisional,annotator2_verdict,adjudicated,arbiter_verdict,date,glm_label,glm_agree"];
  DATA.packets.forEach(p=>{const s=st(p.id),b=s.blind,g=p.glm;
    const agr=b&&s.glmReview?(b.label===g.label&&s.glmReview.agree!=="no"?"YES":"NO"):"";
    const row=[p.set,p.packet,p.issue,b?(b.label==="NEEDS_REVIEW"?"NEED_EVIDENCE":b.label):"PENDING",
      needsArb(p.id)?(s.arb&&s.arb.verdict?"YES":"NO"):(b?"N/A":"NO"),
      s.arb&&s.arb.verdict?s.arb.verdict:"", b?s.blind.ts.slice(0,10):"", g.label, agr];
    lines.push(row.map(csvCell).join(","));});
  download("human_review_tracking_filled.csv",lines.join("\r\n"),"text/csv");
};
function csvCell(x){x=(x==null?"":String(x));return /[",\n]/.test(x)?'"'+x.replace(/"/g,'""')+'"':x;}
function download(name,text,mime){const bl=new Blob([text],{type:mime});const a=document.createElement("a");
  a.href=URL.createObjectURL(bl);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.url),800);}
document.getElementById("fileInput").onchange=e=>{const f=e.target.files[0];if(!f)return;const r=new FileReader();
  r.onload=()=>{try{const inp=JSON.parse(r.result);state=Object.assign(load(),inp);save();render();alert("导入成功");}catch(err){alert("导入失败："+err.message);}};r.readAsText(f);};
document.getElementById("btnImport").onclick=()=>document.getElementById("fileInput").click();
document.getElementById("btnPrint").onclick=()=>window.print();

render();
</script>
</body>
</html>
"""


def main() -> None:
    data = collect()
    # attach oracle gold (PROVISIONAL) per packet from tracking CSV
    tracking = {}
    for line in (HUMAN / "human_review_tracking.csv").read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        tracking[(parts[0], parts[1])] = parts[3]
    for p in data["packets"]:
        p["_oracle"] = tracking[(p["set"], p["packet"])]
    n_files = sum(len(p["files"]) for p in data["packets"])
    html = build_html(data)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(
        f"packets={len(data['packets'])} evidence_files={n_files} "
        f"bytes={len(html.encode('utf-8'))} -> {OUT_HTML.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
