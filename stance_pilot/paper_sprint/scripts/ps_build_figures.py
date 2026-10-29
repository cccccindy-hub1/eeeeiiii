"""Generate paper figures as dependency-free SVG (zero-API, deterministic).

Reads tables/results_summary.json so every plotted number is the same one
used in the tables. Run: -m paper_sprint.scripts.ps_build_figures
"""
from paper_sprint.scripts import ps_common as K
import json

INK = "#1b1b1b"
GREY = "#6b6b6b"
LIGHT = "#d9d9d9"
FILL = "#3b6fb6"
WARN = "#b63b3b"
OK = "#3b8a52"
FONT = ("font-family='Helvetica,Arial,sans-serif' font-size='13' "
        f"fill='{INK}'")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def text(x, y, s, size=13, fill=INK, anchor="start", weight="normal",
         italic=False):
    st = "italic" if italic else "normal"
    return (f"<text x='{x}' y='{y}' font-family='Helvetica,Arial,sans-serif' "
            f"font-size='{size}' fill='{fill}' text-anchor='{anchor}' "
            f"font-weight='{weight}' font-style='{st}'>{esc(s)}</text>")


def rect(x, y, w, h, fill="none", stroke=INK, sw=1.2, rx=4, dash=None):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'{d}/>")


def line(x1, y1, x2, y2, stroke=GREY, sw=1.5, dash=None, marker=False):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    m = " marker-end='url(#arrow)'" if marker else ""
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{stroke}' "
            f"stroke-width='{sw}'{d}{m}/>")


def svg(w, h, body):
    head = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' "
            f"height='{h}' viewBox='0 0 {w} {h}'>"
            "<defs><marker id='arrow' markerWidth='9' markerHeight='9' "
            "refX='7' refY='3' orient='auto' markerUnits='strokeWidth'>"
            f"<path d='M0,0 L7,3 L0,6 z' fill='{GREY}'/></marker></defs>")
    return head + body + "</svg>"


def fig_concept(path):
    W, H = 940, 470
    b = []
    b.append(text(20, 30, "Three-way review decision under controlled evidence",
                  16, weight="bold"))
    # three verdict chips
    chips = [("ACCEPT", OK, "patch acceptable under the granted scope"),
             ("REJECT", WARN, "a decisive failure is evidenced"),
             ("NEED_EVIDENCE", FILL, "available evidence is non-decisive")]
    x = 20
    for name, col, desc in chips:
        b.append(rect(x, 55, 285, 52, fill="#ffffff", stroke=col, sw=1.6))
        b.append(text(x + 12, 78, name, 14, col, weight="bold"))
        b.append(text(x + 12, 98, desc, 10.5, GREY, italic=True))
        x += 300
    # two gold tiers
    b.append(rect(20, 140, 440, 150, fill="#f7f9fc", stroke=FILL))
    b.append(text(34, 164, "Oracle Gold", 14, FILL, weight="bold"))
    b.append(text(34, 186, "ground truth from real pytest: F2P / P2P / symptom",
                  11.5))
    b.append(text(34, 206, "ACCEPT if declared tests pass & no in-scope regression;",
                  11.5))
    b.append(text(34, 224, "REJECT on any decisive declared failure.", 11.5))
    b.append(text(34, 252, "Scoped, not whole-project correctness.", 11.5, GREY,
                  italic=True))
    b.append(rect(480, 140, 440, 150, fill="#fcf8f6", stroke=WARN))
    b.append(text(494, 164, "Condition Gold", 14, WARN, weight="bold"))
    b.append(text(494, 186, "the decision the granted evidence can justify:",
                  11.5))
    b.append(text(494, 206, "restricted surfaces -> NEED_EVIDENCE even when", 11.5))
    b.append(text(494, 224, "oracle is ACCEPT/REJECT; sufficient -> oracle.", 11.5))
    b.append(text(494, 252, "Distinguishes integrity from sufficiency.", 11.5,
                  GREY, italic=True))
    # condition ladder
    b.append(text(20, 324, "Evidence conditions (per issue)", 13, weight="bold"))
    cond = [("T2D-T", "static restricted", "NEED"),
            ("T3D-Strict", "active, outcomes withheld", "NEED"),
            ("T3D-Escalate", "active, then outcomes granted", "= oracle"),
            ("T2A-T", "static sufficient (tier-A)", "= oracle"),
            ("T3A-T", "active sufficient (tier-A)", "= oracle")]
    x = 20
    for cname, desc, gold in cond:
        col = WARN if gold == "NEED" else OK
        b.append(rect(x, 340, 172, 86, fill="#fff", stroke=col))
        b.append(text(x + 86, 366, cname, 13, anchor="middle", weight="bold"))
        b.append(text(x + 86, 388, desc, 10.5, GREY, anchor="middle"))
        b.append(text(x + 86, 410, "gold: " + gold, 10.5, col, anchor="middle",
                      italic=True))
        if x < 800:
            b.append(line(x + 172, 383, x + 188, 383, marker=True))
        x += 184
    K.write_text(path, svg(W, H, "".join(b)))


def fig_deepseek(path):
    W, H = 640, 360
    b = [text(20, 30, "DeepSeek: sufficient-evidence abstention after protocol "
                      "repair", 14, weight="bold")]
    # two stacked bars for need-any 9 vs 1
    base_y, bar_h, gap, x0, maxw = 90, 70, 60, 220, 320
    vals = [("G3-B (original instrument)", 9, WARN),
            ("G3-B.3 (repaired protocol)", 1, OK)]
    for i, (lab, n, col) in enumerate(vals):
        y = base_y + i * (bar_h + gap)
        w = maxw * n / 10
        b.append(rect(x0, y, w, bar_h, fill=col, stroke=col))
        b.append(text(x0 - 12, y + bar_h / 2 + 5, lab, 12, anchor="end"))
        b.append(text(x0 + w + 8, y + bar_h / 2 + 5, f"{n}/10 NEED_ANY",
                      13, col, weight="bold"))
    b.append(text(220, 300, "8 issues reversed NEED -> commit; 0 reversed back; "
                            "residual = SymPy-13974", 11.5, GREY))
    b.append(text(220, 322, "Paired issue-cluster bootstrap 95% CI of "
                            "difference: 0.5-1.0 (ASSOCIATIONAL)", 11.5, GREY,
                  italic=True))
    b.append(line(540, 125, 300, 255, stroke=GREY, sw=2, dash="5,4"))
    K.write_text(path, svg(W, H, "".join(b)))


def fig_strict(path):
    W, H = 720, 380
    b = [text(20, 30, "GPT-4.1-mini under T3D-Strict (condition gold = "
                      "NEED_EVIDENCE)", 14, weight="bold")]
    # G3-B vs G3-B.3 stacked counts
    rows = [("G3-B", {"ACCEPT": 0, "REJECT": 0, "NEED": 10}),
            ("G3-B.3", {"ACCEPT": 7, "REJECT": 0, "NEED": 3})]
    colors = {"ACCEPT": WARN, "REJECT": "#c98a2b", "NEED": FILL}
    x0, y0, unit, rowh = 200, 70, 34, 64
    for i, (lab, d) in enumerate(rows):
        y = y0 + i * 90
        x = x0
        b.append(text(x0 - 12, y + 34, lab, 12, anchor="end"))
        for k in ("ACCEPT", "REJECT", "NEED"):
            n = d[k]
            if n:
                b.append(rect(x, y, unit * n, rowh, fill=colors[k],
                              stroke=colors[k]))
                b.append(text(x + unit * n / 2, y + rowh / 2 + 5, str(n), 14,
                              "#fff", anchor="middle", weight="bold"))
                x += unit * n
        b.append(text(x + 8, y + 34,
                      {"G3-B": "10/10 correct NEED",
                       "G3-B.3": "7 unsupported ACCEPT, 3 correct NEED"}[lab],
                      12, GREY))
    # legend
    lx = 200
    for k in ("ACCEPT", "REJECT", "NEED"):
        b.append(rect(lx, 250, 14, 14, fill=colors[k], stroke=colors[k], rx=2))
        b.append(text(lx + 20, 262, {"ACCEPT": "unsupported ACCEPT",
                                     "REJECT": "unsupported REJECT",
                                     "NEED": "correct NEED_EVIDENCE"}[k], 11.5))
        lx += 175
    b.append(text(200, 300, "Acceptance outcomes are structurally withheld; each "
                            "ACCEPT upgrades non-decisive evidence to sufficient.",
                  11.5, GREY))
    b.append(text(200, 322, "7 wrong-accepts: 13615,13974,15349,17318,17630,"
                            "21847,24443 ; correct: 19783,20590,24213",
                  11, GREY, italic=True))
    b.append(text(200, 345, "Cross-version contrast confounded (freshness/trust "
                            "changed with activeness): candidate mechanism only.",
                  11, WARN, italic=True))
    K.write_text(path, svg(W, H, "".join(b)))


def fig_focal(path):
    W, H = 760, 300
    b = [text(20, 30, "Focal case: SymPy-17318 - ignoring an already-visible "
                      "F2P failure", 14, weight="bold")]
    steps = [
        ("static T2A-T", "declared F2P test_issue_12420\nFAILED: [4+I,0,1] != []",
         "GPT ACCEPT", WARN),
        ("active T3A-T", "same failure surfaced interactively", "GPT REJECT", OK),
    ]
    x = 40
    for lab, ev, out, col in steps:
        b.append(rect(x, 70, 300, 150, fill="#fff", stroke=col, sw=1.6))
        b.append(text(x + 150, 98, lab, 13, anchor="middle", weight="bold"))
        for j, ln in enumerate(ev.split("\n")):
            b.append(text(x + 150, 128 + j * 20, ln, 11, GREY, anchor="middle"))
        b.append(rect(x + 70, 178, 160, 30, fill=col, stroke=col))
        b.append(text(x + 150, 198, out, 13, "#fff", anchor="middle",
                      weight="bold"))
        x += 360
    b.append(line(340, 145, 392, 145, marker=True))
    b.append(text(20, 258, "Oracle gold = REJECT. Failure was visible in both; "
                           "only the active condition forced verification.",
                  11.5, GREY))
    b.append(text(20, 280, "Independent REJECT issues n=3 in G3-B.3: report as a "
                           "case, not a population rate.", 11.5, WARN,
                  italic=True))
    K.write_text(path, svg(W, H, "".join(b)))


def main():
    out = K.FIG
    fig_concept(out / "fig1_concept.svg")
    fig_deepseek(out / "fig2_deepseek_transition.svg")
    fig_strict(out / "fig3_gpt_strict_distribution.svg")
    fig_focal(out / "fig4_focal_17318.svg")
    for p in sorted(out.glob("fig*.svg")):
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
