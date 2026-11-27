"""Gradio UI (FR-16..19): request -> extracted IR | constraints | timeline or conflict, with an editable IR
and one-click fixes. The LLM only extracts; everything shown as reasoning comes from Z3.

The plan is drawn as a time-space chart (Marey's railway timetable): time runs across, the places of the day
run down in visiting order, visits are heavy bars and travel is the diagonal between them.

    python -m nstrip.app.gradio_app [--share] [--port 7860]
"""

import argparse
import base64
import html
import json
from pathlib import Path

import gradio as gr
from pydantic import ValidationError

from nstrip.explain.templates import describe, describe_fix, money
from nstrip.extract.extractor import ir_model, short_errors
from nstrip.extract.llm_client import make_client
from nstrip.kb.loader import KB, load_kb
from nstrip.models import to_hhmm
from nstrip.models.constraints import parse_cid
from nstrip.models.ir import TripRequestIR
from nstrip.models.plan import PipelineResult, Relaxation, Status
from nstrip.pipeline import run_pipeline

EXAMPLES = Path(__file__).resolve().parents[3] / "data" / "examples" / "demo_requests.json"
CATEGORY = {"theme_park": "Theme park", "attraction": "Attraction", "show": "Show", "museum": "Museum",
            "nature": "Nature", "food": "Food", "shopping": "Shopping"}
VERDICT = {Status.SAT: ("Feasible", "sat"), Status.UNSAT: ("Infeasible", "unsat"),
           Status.NEEDS_CLARIFICATION: ("Needs clarification", "warn"),
           Status.EXTRACTION_FAILED: ("Extraction failed", "muted"),
           Status.SOLVER_TIMEOUT: ("Solver timeout", "muted"), Status.INTERNAL_ERROR: ("Internal error", "muted")}
ROW_H = 52  # px per place row in the chart

FONTS = Path(__file__).parent / "fonts"  # Archivo and JetBrains Mono (SIL OFL), latin subset, variable


def _font_face(family: str, file: str, weight: str, stretch: str = "100%") -> str:
    data = base64.b64encode((FONTS / file).read_bytes()).decode()
    return (f"@font-face {{ font-family: '{family}'; src: url(data:font/woff2;base64,{data}) format('woff2'); "
            f"font-weight: {weight}; font-stretch: {stretch}; font-display: swap; }}")


# Fonts are inlined so the UI looks the same offline (a viva laptop without internet).
# Gradio scopes the css= block under .gradio-container, so page-level rules for small screens live here too.
HEAD = ("<style>" + _font_face("Archivo", "Archivo-latin.woff2", "300 800", "62% 125%")
        + _font_face("JetBrains Mono", "JetBrainsMono-latin.woff2", "400 500")
        + "@media (max-width: 760px) { body .gradio-container { padding: 0 16px 32px !important; }\n"
        "  body .gradio-container .main { padding-left: 0 !important; padding-right: 0 !important; } }</style>")

PAPER, INK, INK_2, INK_3 = "#f5f6f7", "#1c1f24", "#474e58", "#646c78"
RULE, RULE_STRONG, WHITE = "#dfe3e7", "#c3c9d0", "#ffffff"


def theme() -> gr.themes.Base:
    t = gr.themes.Base(font=["Archivo", "ui-sans-serif", "system-ui", "sans-serif"],
                       font_mono=["JetBrains Mono", "ui-monospace", "monospace"],
                       radius_size=gr.themes.sizes.radius_none, text_size=gr.themes.sizes.text_md)
    v = dict(  # noqa: C408 - keyword form mirrors the theme.set() arguments
        body_background_fill=PAPER, body_text_color=INK, body_text_color_subdued=INK_3,
        background_fill_primary=WHITE, background_fill_secondary=PAPER,
        border_color_primary=RULE_STRONG, border_color_accent=INK, border_color_accent_subdued=RULE_STRONG,
        color_accent=INK, color_accent_soft="#e9ecef", link_text_color=INK, link_text_color_hover=INK_2,
        link_text_color_visited=INK, link_text_color_active=INK,
        block_background_fill="transparent", block_border_width="0px", block_shadow="none",
        block_padding="0px", block_label_background_fill="transparent", block_label_border_width="0px",
        block_label_text_color=INK_2, block_label_text_size="13px", block_label_text_weight="600",
        block_label_padding="0 0 6px 0", block_title_text_color=INK_2, block_title_text_size="13px",
        block_title_text_weight="600", block_title_padding="0 0 6px 0", block_info_text_color=INK_3,
        panel_background_fill="transparent", panel_border_width="0px", layout_gap="20px", form_gap_width="0px",
        input_background_fill=WHITE, input_background_fill_focus=WHITE, input_background_fill_hover=WHITE,
        input_border_color=RULE_STRONG, input_border_color_hover=INK_3, input_border_color_focus=INK,
        input_border_width="1px", input_shadow="none", input_shadow_focus=f"0 0 0 1px {INK}",
        input_placeholder_color="#7a828d", input_padding="12px 14px", input_text_size="15px",
        button_primary_background_fill=INK, button_primary_background_fill_hover="#000000",
        button_primary_text_color=WHITE, button_primary_text_color_hover=WHITE,
        button_primary_border_color=INK, button_primary_border_color_hover="#000000",
        button_primary_shadow="none", button_primary_shadow_hover="none", button_primary_shadow_active="none",
        button_secondary_background_fill=WHITE, button_secondary_background_fill_hover="#eef0f2",
        button_secondary_text_color=INK, button_secondary_text_color_hover=INK,
        button_secondary_border_color=INK, button_secondary_border_color_hover=INK,
        button_secondary_shadow="none", button_secondary_shadow_hover="none", button_secondary_shadow_active="none",
        button_border_width="1px", button_large_text_size="15px", button_large_text_weight="600",
        button_large_padding="12px 22px", button_medium_text_weight="600", button_transform_hover="none",
        button_transform_active="none", button_transition="background-color .15s ease",
        checkbox_background_color=WHITE, checkbox_border_color=INK_3, checkbox_border_color_selected=INK,
        checkbox_background_color_selected=INK, checkbox_border_color_focus=INK,
        checkbox_label_background_fill="transparent", checkbox_label_background_fill_hover="transparent",
        checkbox_label_background_fill_selected="transparent", checkbox_label_border_width="0px",
        checkbox_label_shadow="none", checkbox_label_padding="4px 12px 4px 0", checkbox_label_text_size="14px",
        checkbox_label_text_color=INK, checkbox_label_text_color_selected=INK,
        table_border_color=RULE, table_even_background_fill=WHITE, table_odd_background_fill="#fafbfb",
        table_row_focus="#eef0f2", table_text_color=INK, code_background_fill=WHITE,
        shadow_drop="none", shadow_drop_lg="0 8px 24px rgba(28,31,36,.12)", shadow_spread="0px",
        error_background_fill="#fdf1ee", error_border_color="#c13a26", error_text_color="#8f2617",
        error_icon_color="#c13a26", loader_color=INK, slider_color=INK, stat_background_fill=INK,
    )
    # The room is lit and the reading is close: one light sheet, also when the OS is in dark mode.
    return t.set(**v, **{k + "_dark": x for k, x in v.items() if hasattr(t, k + "_dark")})


CSS = """
:root, .dark {
  --ns-paper:#f5f6f7; --ns-ink:#1c1f24; --ns-ink-2:#474e58; --ns-ink-3:#646c78;
  --ns-rule:#dfe3e7; --ns-rule-strong:#c3c9d0; --ns-sat:#16726b; --ns-unsat:#c13a26; --ns-warn:#9a5b06;
  --ns-label:244px; color-scheme: light;
}
body, gradio-app, .gradio-container { background: var(--ns-paper) !important; }
.gradio-container { max-width: 1320px !important; margin: 0 auto !important; padding: 0 32px 48px !important;
  font-variant-numeric: tabular-nums; }
::selection { background: #1c1f24; color: #fff; }
* { scrollbar-color: #c3c9d0 transparent; scrollbar-width: thin; }
:focus-visible { outline: 2px solid var(--ns-ink) !important; outline-offset: 2px; }
footer { display: none !important; }

/* masthead */
.ns-mast { display:flex; align-items:baseline; justify-content:space-between; gap:24px; flex-wrap:wrap;
  padding: 28px 0 14px; border-bottom: 1px solid var(--ns-ink); margin-bottom: 8px; }
.ns-mast h1 { margin:0; font-size: 26px; font-weight: 700; letter-spacing: -0.015em; font-stretch: 92%; }
.ns-mast h1 span { font-weight: 400; color: var(--ns-ink-3); }
.ns-mast p { margin:0; color: var(--ns-ink-2); font-size: 14px; max-width: 62ch; }
.ns-mast b { color: var(--ns-ink); font-weight: 600; }

/* section heads drawn like timetable column heads */
.ns-head { font-stretch: 75%; text-transform: uppercase; letter-spacing: .08em; font-size: 12px;
  font-weight: 600; color: var(--ns-ink-2); border-bottom: 1px solid var(--ns-rule-strong);
  padding-bottom: 6px; margin: 0 0 14px; }

/* verdict */
.ns-verdict { border-top: 3px solid var(--ns-rule-strong); padding-top: 14px; }
.ns-verdict.sat { border-top-color: var(--ns-sat); } .ns-verdict.unsat { border-top-color: var(--ns-unsat); }
.ns-verdict.warn { border-top-color: var(--ns-warn); }
.ns-word { font-size: 44px; line-height: 1; font-weight: 700; letter-spacing: -0.03em; font-stretch: 88%; margin: 0; }
.sat .ns-word { color: var(--ns-sat); } .unsat .ns-word { color: var(--ns-unsat); }
.warn .ns-word { color: var(--ns-warn); } .muted .ns-word, .empty .ns-word { color: var(--ns-ink); }
.empty .ns-word { font-size: 28px; font-weight: 600; letter-spacing: -0.015em; }
.ns-sum { margin: 10px 0 0; font-size: 17px; color: var(--ns-ink); }
.ns-sum + .ns-sum { margin-top: 4px; font-size: 15px; color: var(--ns-ink-2); max-width: 64ch; }
.ns-proof { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin: 18px 0 0;
  border-top: 1px solid var(--ns-rule-strong); }
.ns-proof div { padding: 10px 12px 2px 0; border-right: 1px solid var(--ns-rule); margin-right: 12px; }
.ns-proof div:last-child { border-right: 0; }
.ns-proof dt { font-stretch: 75%; text-transform: uppercase; letter-spacing: .08em; font-size: 11px;
  font-weight: 600; color: var(--ns-ink-3); }
.ns-proof dd { margin: 3px 0 0; font-size: 15px; font-weight: 600; }
.ns-proof dd.sat { color: var(--ns-sat); } .ns-proof dd.unsat { color: var(--ns-unsat); }

/* chart */
.ns-view { overflow-x: auto; max-width: calc(100vw - 32px); }
.ns-chart { position: relative; margin-top: 4px; min-width: 760px; }
.ns-axis { position: relative; height: 22px; margin-left: var(--ns-label); font-size: 12.5px; color: var(--ns-ink-3);
  font-stretch: 80%; letter-spacing: .02em; }
.ns-axis span { position:absolute; top:0; transform: translateX(-50%); }
.ns-axis span.edge { color: var(--ns-ink); font-weight: 600; }
.ns-axis span.first { transform: none; } .ns-axis span.last { transform: translateX(-100%); }
.ns-body { position: relative; border-top: 1px solid var(--ns-ink); border-bottom: 1px solid var(--ns-ink); }
.ns-grid { position:absolute; top:0; bottom:0; left: var(--ns-label); right:0; pointer-events:none; }
.ns-grid i { position:absolute; top:0; bottom:0; width:0; border-left: 1px solid var(--ns-rule); }
.ns-grid i.major { border-left-color: var(--ns-rule-strong); }
.ns-route { position:absolute; top:0; left: var(--ns-label); width: calc(100% - var(--ns-label)); height:100%;
  overflow: visible; pointer-events:none; transition: opacity .2s ease; }
.ns-row { position: relative; display: grid; grid-template-columns: var(--ns-label) 1fr; height: 52px;
  border-bottom: 1px solid var(--ns-rule); transition: opacity .2s ease; }
.ns-row:last-child { border-bottom: 0; }
.ns-name { padding: 8px 12px 0 0; overflow: hidden; }
.ns-name b { display:block; font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.ns-name small { display:block; font-size: 11px; color: var(--ns-ink-3); white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; font-stretch: 80%; letter-spacing: .02em; margin-top: 2px; }
.ns-name small code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 10.5px; color: var(--ns-ink-2);
  margin-right: 4px; letter-spacing: 0; }
.ns-name em { font-style: normal; border: 1px solid var(--ns-ink-3); padding: 0 4px; margin-left: 4px;
  font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--ns-ink-2); }
.ns-lane { position: relative; }
.ns-open { position:absolute; top: 12px; height: 28px; background: #e4e8ec; }
.ns-tick { position:absolute; top: 9px; height: 34px; width: 0; border-left: 1.5px solid var(--ns-ink-3); }
.ns-bar { position:absolute; top: 15px; height: 22px; background: var(--ns-ink); color:#fff; font-size: 12px;
  font-weight: 600; line-height: 22px; padding: 0 6px; white-space: nowrap; overflow: visible; z-index: 1; }
.ns-bar.show { background: repeating-linear-gradient(135deg, var(--ns-ink) 0 2px, #fff 2px 5px);
  outline: 1px solid var(--ns-ink); outline-offset: -1px; }
.ns-chart .ns-bar > span { position: relative; color: #fff; }
.ns-chart .ns-bar.show > span, .ns-chart .ns-bar.narrow > span { background: var(--ns-paper); color: var(--ns-ink);
  padding: 0 4px; }
.ns-chart .ns-bar.narrow > span { position:absolute; left: 100%; margin-left: 4px; top: 0; }
.ns-chart .ns-bar.narrow.flip > span { left: auto; right: 100%; margin: 0 4px 0 0; }
.ns-dot { position:absolute; top: 21px; width: 10px; height: 10px; margin-left: -5px; border: 2px solid var(--ns-ink);
  background: var(--ns-paper); border-radius: 50%; z-index: 1; }
.ns-tt { position:absolute; font-size: 11px; color: var(--ns-ink-2); background: var(--ns-paper); padding: 0 3px;
  transform: translate(6px, -50%); white-space: nowrap; z-index: 2; pointer-events: none; }
.ns-chart:has(.ns-row.v:hover) .ns-row.v:not(:hover),
.ns-chart:has(.ns-row.v:hover) .ns-route, .ns-chart:has(.ns-row.v:hover) .ns-tt { opacity: .3; }
.ns-row.v:hover { background: #fff; }
.ns-key { display:flex; flex-wrap:wrap; gap: 6px 22px; margin: 12px 0 0 var(--ns-label); font-size: 12px;
  color: var(--ns-ink-2); }
.ns-key span { display:inline-flex; align-items:center; gap: 8px; }
.ns-key i { display:inline-block; width: 22px; height: 10px; background: var(--ns-ink); }
.ns-key i.show { background: repeating-linear-gradient(135deg, var(--ns-ink) 0 2px, #fff 2px 5px);
  outline: 1px solid var(--ns-ink); outline-offset: -1px; }
.ns-key i.travel { height: 0; border-top: 1.5px solid var(--ns-ink); transform: rotate(24deg); background: none; }
.ns-key i.wait { height: 0; border-top: 1.5px dashed var(--ns-ink-3); background: none; }
.ns-key i.open { background: #e4e8ec; height: 14px; }
.ns-key i.tick { width: 0; height: 14px; border-left: 1.5px solid var(--ns-ink-3); background: none; }
.ns-apply { align-items: flex-end !important; }
.ns-explain { margin-top: 18px; }
.ns-model { font-size: 12.5px; color: var(--ns-ink-3); margin: 4px 0 0; }
.ns-model code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; color: var(--ns-ink-2); }
/* accordions: an ink chevron drawn in CSS in place of Gradio's text triangle */
.label-wrap { font-weight: 600 !important; font-size: 14px !important; }
.label-wrap .icon { font-size: 0 !important; width: 8px; height: 8px; border-right: 1.5px solid var(--ns-ink);
  border-bottom: 1.5px solid var(--ns-ink); margin: 0 4px 3px 0; }
.ns-apply button { min-height: 34px !important; height: 34px !important; padding-top: 0 !important;
  padding-bottom: 0 !important; }

/* conflict */
.ns-hatch { display:inline-block; width: 14px; height: 14px; flex: none; margin-top: 3px;
  background: repeating-linear-gradient(45deg, var(--ns-unsat) 0 1.5px, transparent 1.5px 4px),
              repeating-linear-gradient(-45deg, var(--ns-unsat) 0 1.5px, transparent 1.5px 4px);
  outline: 1px solid var(--ns-unsat); outline-offset: -1px; }
.ns-lede { font-size: 16px; margin: 0 0 12px; max-width: 70ch; }
.ns-core { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--ns-ink); }
.ns-core li { display:grid; grid-template-columns: 14px minmax(140px, 220px) 1fr auto; gap: 14px; align-items: start;
  padding: 11px 0; border-bottom: 1px solid var(--ns-rule); }
.ns-core code, .ns-ctab code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12.5px;
  color: var(--ns-ink); background: none; padding: 0; overflow-wrap: anywhere; }
.ns-core p { margin: 0; font-size: 15px; }
.ns-tag { font-stretch: 75%; text-transform: uppercase; letter-spacing: .08em; font-size: 11px; font-weight: 600;
  color: var(--ns-ink-3); white-space: nowrap; padding-top: 2px; }
.ns-meta { font-size: 13px; color: var(--ns-ink-3); margin: 10px 0 0; }
.ns-fixes { margin: 28px 0 0; }
.ns-fixes ul { list-style: none; margin: 0; padding: 0; }
.ns-fixes li { display:flex; gap: 12px; align-items: baseline; padding: 8px 0; border-bottom: 1px solid var(--ns-rule);
  font-size: 15px; }
.ns-fixes li s { color: var(--ns-ink-3); }
.ns-fixes li .ok { color: var(--ns-sat); font-weight: 600; font-size: 13px; white-space: nowrap; }
.ns-fixes li .no { color: var(--ns-ink-3); font-size: 13px; white-space: nowrap; }
.ns-fixes li > span:first-child { flex: 1; }
.ns-msg { font-size: 16px; max-width: 70ch; margin: 0; }
.ns-msg + pre { margin-top: 12px; font-size: 12.5px; white-space: pre-wrap; border: 1px solid var(--ns-rule-strong);
  background:#fff; padding: 12px; }
.ns-blank { color: var(--ns-ink-3); font-size: 15px; padding: 28px 0; border-top: 1px solid var(--ns-rule-strong);
  border-bottom: 1px solid var(--ns-rule-strong); }

/* constraints table */
.ns-ctab { width: 100%; border-collapse: collapse; font-size: 14px; }
.ns-ctab th { text-align: left; font-stretch: 75%; text-transform: uppercase; letter-spacing: .08em; font-size: 11px;
  font-weight: 600; color: var(--ns-ink-3); border-bottom: 1px solid var(--ns-ink); padding: 6px 12px 6px 0; }
.ns-ctab td { border-bottom: 1px solid var(--ns-rule); padding: 9px 12px 9px 0; vertical-align: top; }
.ns-ctab td:first-child { width: 18px; } .ns-ctab td:nth-child(2) { width: 30%; }
.ns-ctab tr.core td { color: var(--ns-unsat); font-weight: 600; } .ns-ctab tr.core code { color: var(--ns-unsat); }
.ns-ctab td.fact { color: var(--ns-ink-3); font-size: 12px; white-space: nowrap; }
.ns-hard { font-size: 13px; color: var(--ns-ink-2); margin: 14px 0 0; }

/* gradio furniture in the same drawing language */
.tab-wrapper { border-bottom: 1px solid var(--ns-ink) !important; }
.tab-container, .tab-container::after { border: 0 !important; background: none !important; }
.form { background: transparent !important; border: 0 !important; }
#ns-ex > .label { display: none !important; }
button[role="tab"] { font-weight: 600 !important; font-size: 14px !important; color: var(--ns-ink-3) !important;
  border: 0 !important; background: none !important; padding: 10px 18px 10px 0 !important; margin-right: 18px; }
button[role="tab"][aria-selected="true"] { color: var(--ns-ink) !important; box-shadow: inset 0 -3px 0 var(--ns-ink); }
button[role="tab"][aria-selected="true"]::after { display: none !important; }
.tabitem { padding: 22px 0 0 !important; border: 0 !important; background: none !important; }
textarea, input { font-variant-numeric: tabular-nums; }
.ns-answer textarea { background: transparent !important; border: 0 !important; border-left: 1px solid var(--ns-rule-strong) !important;
  padding: 2px 0 2px 14px !important; font-size: 15px !important; line-height: 1.55 !important; color: var(--ns-ink-2) !important;
  box-shadow: none !important; }
#ns-ex .gallery-item { border-radius: 0 !important; max-width: 100%; text-align: left; }
#ns-ex .gallery-item > div { white-space: normal !important; }
.prose h3 { font-size: 15px; }
@media (max-width: 760px) {
  .ns-word { font-size: 34px; }
  .ns-chart { --ns-label: 132px; }
  .ns-name { position: sticky; left: 0; z-index: 3; background: var(--ns-paper); }
  .ns-row.v:hover .ns-name { background: #fff; }
  .ns-proof div { border-right: 0; }
  .ns-name { padding-top: 6px; }
  .ns-name b { white-space: normal; font-size: 13px; line-height: 1.2; }
  .ns-name small { font-size: 0; } .ns-name small code { font-size: 10px; }
  .ns-name em { font-size: 0; padding: 0; border: 0; }
  .ns-name em::before { content: 'opt'; font-size: 10px; font-family: 'JetBrains Mono', monospace;
    color: var(--ns-ink-3); text-transform: none; }
  button[role="tab"] { padding: 10px 0 !important; margin-right: 14px !important; font-size: 13px !important; }
  .ns-core li { grid-template-columns: 14px 1fr; } .ns-core li p, .ns-core li .ns-tag { grid-column: 2; }
  .ns-ctab td:nth-child(2) { width: auto; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""


# ---------------------------------------------------------------- rendering (pure, tested)

def esc(x) -> str:
    return html.escape(str(x))


def _duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d}" if h and m else f"{h} h" if h else f"{m} min"


def verdict_html(r: PipelineResult | None, kb: KB) -> str:
    """The verdict and the evidence behind it, in the order an examiner checks it."""
    if r is None:
        return ('<div class="ns-verdict empty"><p class="ns-word">No plan yet</p>'
                '<p class="ns-sum">Describe your day, or pick an example below, then press Plan my day.</p>'
                '<p class="ns-sum">Examples also fill the extracted form, so Re-solve works without an LLM.</p></div>')
    word, cls = VERDICT[r.status]
    proof: list[tuple[str, str, str]] = []
    lines: list[str] = []
    solve_ms = r.timings_ms.get("solve")
    if r.status == Status.SAT:
        p, plan = r.problem, r.plan
        n = len(plan.visits)
        spend = money(plan.total_cost, kb.currency) + (f" of {money(p.budget, kb.currency)}" if p.budget is not None
                                                       else "")
        lines.append(f"{n} visit{'s' * (n != 1)} · {to_hhmm(plan.visits[0].start)}–{to_hhmm(plan.visits[-1].end)}"
                     f" · {spend}")
        proof = [("Z3", "sat", "sat"), ("Independent checker", "0 violations", "sat"),
                 ("Optimisation", "proven optimal" if plan.optimal else "valid, not proven optimal", "")]
    elif r.status == Status.UNSAT:
        d = r.diagnosis
        fixes = sum(x.restores_feasibility for x in d.relaxations)
        lines.append(f"{len(d.core)} requirements conflict · {fixes} single change{'s' * (fixes != 1)} "
                     "would fix it")
        size = f"{'minimal' if d.is_minimal else 'possibly not minimal'}, {d.raw_core_size} → {len(d.core)}"
        proof = [("Z3", "unsat", "unsat"), ("Conflict", size, ""),
                 ("Solver calls", str(d.solver_calls), "")]
    else:
        lines.append(r.explanation.split("\n")[0])
    if solve_ms is not None:
        proof.append(("Solve time", f"{solve_ms:.0f} ms", ""))
    if "extract" in r.timings_ms:
        proof.append(("LLM extraction", f"{r.llm_attempts} attempt{'s' * (r.llm_attempts != 1)}", ""))
    dl = "".join(f'<div><dt>{esc(k)}</dt><dd class="{c}">{esc(v)}</dd></div>' for k, v, c in proof)
    return (f'<div class="ns-verdict {cls}"><p class="ns-word">{esc(word)}</p>'
            + "".join(f'<p class="ns-sum">{esc(x)}</p>' for x in lines)
            + (f'<dl class="ns-proof">{dl}</dl>' if dl else "") + "</div>")


def timeline_html(r: PipelineResult, kb: KB) -> str:
    """Time-space chart: one row per stop in visiting order, travel drawn as the diagonal between rows."""
    p, plan = r.problem, r.plan
    acts = {a.id: a for a in p.activities}
    h0, h1 = p.horizon_start, p.horizon_end
    span = max(1, h1 - h0)

    def x(t: int) -> float:
        return 100 * (t - h0) / span

    def place_name(pid: str) -> str:
        return kb.places[pid].name if pid in kb.places else pid

    # rows: optional start, each visit, optional return
    rows: list[dict] = []
    if p.start_location:
        rows.append({"kind": "start", "id": p.start_location})
    rows += [{"kind": "visit", "v": v} for v in plan.visits]
    if p.return_to_start and p.start_location:
        rows.append({"kind": "return", "id": p.start_location})
    height = len(rows) * ROW_H

    def y(i: int) -> float:
        return i * ROW_H + ROW_H / 2

    # route: travel diagonals and waiting segments, in the chart's own coordinates (x in %, y in px)
    segs, labels = [], []
    first = 1 if p.start_location else 0
    prev_id, prev_end = (p.start_location, None) if p.start_location else (None, None)
    for k, v in enumerate(plan.visits):
        i = first + k
        if prev_id is not None:
            t = p.travel(prev_id, v.location_id)
            leave = prev_end if prev_end is not None else v.start - t
            arrive = leave + t
            segs.append(f'<line x1="{x(leave):.3f}%" y1="{y(i - 1)}" x2="{x(arrive):.3f}%" y2="{y(i)}" '
                        'stroke="#1c1f24" stroke-width="1.5"/>')
            if t:
                labels.append((x((leave + arrive) / 2), (y(i - 1) + y(i)) / 2, f"{t} min"))
            if v.start > arrive:
                segs.append(f'<line x1="{x(arrive):.3f}%" y1="{y(i)}" x2="{x(v.start):.3f}%" y2="{y(i)}" '
                            'stroke="#646c78" stroke-width="1.5" stroke-dasharray="4 4"/>')
        prev_id, prev_end = v.location_id, v.end
    if p.return_to_start and p.start_location and plan.visits:
        last = plan.visits[-1]
        t = p.travel(last.location_id, p.start_location)
        segs.append(f'<line x1="{x(last.end):.3f}%" y1="{y(len(rows) - 2)}" x2="{x(last.end + t):.3f}%" '
                    f'y2="{y(len(rows) - 1)}" stroke="#1c1f24" stroke-width="1.5"/>')
        if t:
            labels.append((x(last.end + t / 2), y(len(rows) - 1.5), f"{t} min"))

    # rows
    out = []
    for row in rows:
        if row["kind"] == "visit":
            v = row["v"]
            a, place = acts.get(v.location_id), kb.places.get(v.location_id)
            name = esc(a.name if a else place_name(v.location_id))
            show = bool(a and a.showtimes)
            meta = [CATEGORY.get(place.category, place.category) if place else "",
                    money(a.cost, kb.currency) if a else "", _duration(v.end - v.start)]
            lane = ""
            if a:  # the facts the bar must respect, drawn in its lane: opening window and showtimes
                o, c = max(a.open, h0), min(a.close, h1)
                if c > o:
                    lane += f'<i class="ns-open" style="left:{x(o):.3f}%;width:{x(c) - x(o):.3f}%"></i>'
                lane += "".join(f'<i class="ns-tick" style="left:{x(t):.3f}%"></i>' for t in a.showtimes
                                if h0 <= t <= h1)
            opt = "" if (a is None or a.must_visit) else "<em>optional</em>"
            left, width = x(v.start), max(x(v.end) - x(v.start), 0.6)
            narrow = width < 9
            cls = " ".join(c for c in ("ns-bar", "show" if show else "", "narrow" if narrow else "",
                                       "flip" if narrow and left + width > 82 else "") if c)
            tip = f"{name}: {to_hhmm(v.start)}–{to_hhmm(v.end)}" + (
                f" · open {to_hhmm(a.open)}–{to_hhmm(a.close)}" if a else "") + (
                " · shows " + ", ".join(map(to_hhmm, a.showtimes)) if show else "")
            out.append(f'<div class="ns-row v" title="{tip}"><div class="ns-name"><b>{name}{opt}</b>'
                       f'<small><code>{esc(v.location_id)}</code> {esc(" · ".join(m for m in meta if m))}</small>'
                       f'</div><div class="ns-lane">{lane}<div class="{cls}" style="left:{left:.3f}%;width:{width:.3f}%">'
                       f'<span>{to_hhmm(v.start)}–{to_hhmm(v.end)}</span></div></div></div>')
        else:
            v = plan.visits[0] if row["kind"] == "start" else plan.visits[-1]
            t = p.travel(row["id"], v.location_id)
            label, at = ("Leave", v.start - t) if row["kind"] == "start" else ("Back", v.end + t)
            out.append(f'<div class="ns-row"><div class="ns-name"><b>{esc(place_name(row["id"]))}</b>'
                       f'<small>{label} {to_hhmm(at)}</small></div>'
                       f'<div class="ns-lane"><i class="ns-dot" style="left:{x(at):.3f}%"></i></div></div>')

    step = 60 if span <= 720 else 120
    ticks = list(range((h0 // 60 + 1) * 60, h1, step))
    grid = "".join(f'<i class="major" style="left:{x(t):.3f}%"></i>' for t in ticks)
    if span <= 600:
        grid += "".join(f'<i style="left:{x(t + 30):.3f}%"></i>' for t in [h0 // 60 * 60, *ticks]
                        if h0 < t + 30 < h1)
    axis = (f'<span class="edge first" style="left:0">{to_hhmm(h0)}</span>'
            + "".join(f'<span style="left:{x(t):.3f}%">{to_hhmm(t)}</span>' for t in ticks
                      if 5 < x(t) < 93)
            + f'<span class="edge last" style="left:100%">{to_hhmm(h1)}</span>')
    tt = "".join(f'<span class="ns-tt" style="left:calc(var(--ns-label) + (100% - var(--ns-label)) * {lx / 100:.5f});'
                 f'top:{ly}px">{esc(s)}</span>' for lx, ly, s in labels)
    key = ('<div class="ns-key"><span><i></i>Visit</span><span><i class="show"></i>Fixed showtime</span>'
           '<span><i class="travel"></i>Travel</span><span><i class="wait"></i>Waiting</span>'
           '<span><i class="open"></i>Opening hours</span><span><i class="tick"></i>Showtime</span>'
           '<span>Hover a row to isolate it</span></div>')
    return (f'<div class="ns-chart"><div class="ns-axis">{axis}</div>'
            f'<div class="ns-body" style="height:{height}px"><div class="ns-grid">{grid}</div>'
            f'<svg class="ns-route" aria-hidden="true">{"".join(segs)}</svg>{"".join(out)}{tt}</div>'
            f'{key}</div>')


def conflict_html(r: PipelineResult, kb: KB) -> str:
    d = r.diagnosis
    items = []
    for c in d.core:
        fact = parse_cid(c)[0] in ("opening", "showtime")
        items.append(f'<li><span class="ns-hatch" aria-hidden="true"></span><code>{esc(c)}</code>'
                     f'<p>{esc(describe(c, r.problem, kb.currency))}</p>'
                     f'<span class="ns-tag">{"fact about the place" if fact else "your requirement"}</span></li>')
    lede = (f"These {len(d.core)} requirements cannot all hold together. The conflict is minimal: remove any one "
            "and the rest can be satisfied." if d.is_minimal else
            f"These {len(d.core)} requirements cannot all hold together (a minimality check timed out, so the "
            "set may be larger than necessary).")
    fixes = []
    for x in d.relaxations:
        text = describe_fix(x, r.problem, kb.currency).replace(" (not enough on its own: another conflict remains)",
                                                                "")
        state = ('<span class="ok">restores feasibility</span>' if x.restores_feasibility
                 else '<span class="no">not enough on its own</span>')
        fixes.append(f"<li><span>{esc(text[:1].upper() + text[1:])}</span>{state}</li>")
    fix_block = (f'<div class="ns-fixes"><h3 class="ns-head">Smallest changes, each re-solved on the full problem'
                 f'</h3><ul>{"".join(fixes)}</ul></div>' if fixes else "")
    return (f'<p class="ns-lede">{esc(lede)}</p><ol class="ns-core">{"".join(items)}</ol>'
            f'<p class="ns-meta">Z3 returned {d.raw_core_size} labelled constraints; deletion reduced them to '
            f'{len(d.core)} in {d.solver_calls} solver calls.</p>{fix_block}')


def result_html(r: PipelineResult | None, kb: KB) -> str:
    if r is None:
        return '<p class="ns-blank">The plan chart or the conflict appears here.</p>'
    if r.status == Status.SAT:
        return timeline_html(r, kb)
    if r.status == Status.UNSAT:
        return conflict_html(r, kb)
    return f'<p class="ns-msg">{esc(r.explanation)}</p>' + (f"<pre>{esc(r.error)}</pre>" if r.error else "")


def constraints_html(r: PipelineResult) -> str:
    if not r.constraints_readable:
        return '<p class="ns-blank">No constraints were encoded.</p>'
    core = set(r.diagnosis.core) if r.diagnosis else set()
    rows = []
    for c in r.constraints_readable:
        cid, text = c.split(": ", 1)
        hit = cid in core
        fact = parse_cid(cid)[0] in ("opening", "showtime")
        rows.append(f'<tr class="{"core" if hit else ""}"><td>'
                    f'{"<span class=ns-hatch></span>" if hit else ""}</td><td><code>{esc(cid)}</code></td>'
                    f'<td>{esc(text)}</td><td class="fact">{"fact" if fact else ""}</td></tr>')
    legend = ' Rows marked in red form the minimal conflict.' if core else ""
    return ('<table class="ns-ctab"><thead><tr><th></th><th>Label (assumption literal)</th><th>Constraint</th>'
            f'<th></th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            '<p class="ns-hard">Also hard, and not labelled: every pair of visits is ordered with travel time between '
            f'them, and every start lies within 00:00–24:00.{legend}</p>')


def notes_md(r: PipelineResult) -> str:
    out = []
    if r.problem and r.problem.assumed_defaults:
        out.append("**Assumed:** " + "; ".join(r.problem.assumed_defaults))
    if r.ir and r.ir.ignored_preferences:
        out.append("**Noted but not encoded:** " + "; ".join(r.ir.ignored_preferences))
    if r.ir and r.ir.unresolved_mentions:
        out.append("**Not in the knowledge base:** " + "; ".join(r.ir.unresolved_mentions))
    if r.verify_changes:
        out.append("**Corrected after re-reading the request:** " + "; ".join(r.verify_changes))
    elif r.verify_changes == []:
        out.append("**Re-read the request against the conflict:** the extracted form was confirmed.")
    if r.llm_attempts:
        out.append(f"LLM attempts: {r.llm_attempts}")
    if r.timings_ms:
        out.append("Timings: " + ", ".join(f"{k} {v:.0f} ms" for k, v in r.timings_ms.items()))
    return "  \n".join(out) or "_Nothing assumed._"


def apply_relaxation(ir: TripRequestIR, r: Relaxation, horizon_start: int, kb: KB) -> TripRequestIR:
    """Turn a suggested fix into an edited IR (FR-19)."""
    data = ir.model_dump()
    _, ids = parse_cid(r.cid)
    act = next((a for a in data["activities"] if ids and a["location_id"] == ids[0]), None)
    if r.action == "raise_budget":
        data["budget"] = r.new_value
    elif r.action == "extend_horizon_end":
        data |= {"day_start": to_hhmm(horizon_start), "day_end": to_hhmm(min(r.new_value, 1439)),
                 "duration_limit_min": None}
    elif r.action == "widen_window":
        key = "latest_end" if act["latest_end"] and r.old_value == _minutes(act["latest_end"]) else "earliest_start"
        act[key] = to_hhmm(min(r.new_value, 1439))
    elif r.action == "drop_must_visit":
        act["must_visit"] = False
    else:
        data["precedences"] = [p for p in data["precedences"] if (p["before"], p["after"]) != ids]
    return ir_model(tuple(kb.ids)).model_validate(data)


def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def fix_choices(r: PipelineResult, kb: KB) -> list[tuple[str, int]]:
    if not r.diagnosis:
        return []
    usable = [(n, x) for n, x in enumerate(r.diagnosis.relaxations)
              if x.new_value is not None or x.action.startswith("drop")]
    return [(describe_fix(x, r.problem, kb.currency), n) for n, x in usable]


# ---------------------------------------------------------------- app

def model_line() -> str:
    """FR-16: which model the request will go to (read from .env, never hard-coded)."""
    try:
        c = make_client("extract")
    except RuntimeError:
        return "No LLM configured: set NSTRIP_MODEL in .env, or use an example and Re-solve."
    host = c.base_url.split("//")[-1].split("/")[0]
    return f"Extraction model: <code>{esc(c.model)}</code> at {esc(host)}"


def build(kb: KB | None = None) -> gr.Blocks:
    kb = kb or load_kb()
    IR = ir_model(tuple(kb.ids))
    examples = json.loads(EXAMPLES.read_text())
    places = [[p.name, p.id, CATEGORY.get(p.category, p.category), p.cost, f"{to_hhmm(p.open)}–{to_hhmm(p.close)}",
               ", ".join(map(to_hhmm, p.showtimes))] for p in kb.places.values()]

    def outputs(r: PipelineResult):
        ir_text = json.dumps(r.ir.model_dump(exclude_defaults=True), indent=1) if r.ir else ""
        choices = fix_choices(r, kb)
        return (verdict_html(r, kb), r.explanation, result_html(r, kb), ir_text, notes_md(r), constraints_html(r),
                r.smtlib or "", gr.update(choices=choices, value=choices[0][1] if choices else None,
                                          visible=bool(choices)),
                gr.update(visible=bool(choices)), r)

    def on_plan(text: str, mode: str, double_check: bool, reword: bool):
        if not text.strip():
            raise gr.Error("Type a request first.")
        try:
            client = make_client("extract", live=mode == "Live LLM")
        except RuntimeError as e:
            raise gr.Error(f"{e}. Or open Extracted form, edit it and press Re-solve (no LLM needed).") from e
        rephraser = make_client("rephrase", live=mode == "Live LLM") if reword else None
        return outputs(run_pipeline(text, kb, client, verify_client=client if double_check else None,
                                    rephrase_client=rephraser))

    def on_resolve(ir_text: str):
        try:
            ir = IR.model_validate_json(ir_text or "{}")
        except ValidationError as e:
            raise gr.Error("The form is not valid:\n" + short_errors(e)) from e
        return outputs(run_pipeline(None, kb, ir=ir))

    def on_apply(choice, last: PipelineResult | None):
        if last is None or choice is None or last.ir is None:
            raise gr.Error("Nothing to apply.")
        ir = apply_relaxation(last.ir, last.diagnosis.relaxations[choice], last.problem.horizon_start, kb)
        return outputs(run_pipeline(None, kb, ir=ir))

    with gr.Blocks(title="Trip Synthesizer · Singapore") as demo:
        last = gr.State(None)
        gr.HTML(f'<header class="ns-mast"><h1>Trip Synthesizer <span>{esc(kb.city)}</span></h1>'
                "<p>The LLM only fills a typed form from your words. <b>Z3 decides</b> whether the day is "
                "possible, picks the schedule, and finds the minimal conflict and the smallest fixes. An "
                "independent checker verifies every plan.</p></header>")
        with gr.Row(equal_height=False):
            with gr.Column(scale=5, min_width=320):
                gr.HTML('<h2 class="ns-head">Request</h2>')
                request = gr.Textbox(show_label=False, lines=5, max_lines=10,
                                     placeholder="e.g. 10am to 6pm with S$80. National Museum, lunch at Maxwell, "
                                                 "then the ArtScience Museum if there is time.")
                with gr.Row(equal_height=True):
                    mode = gr.Radio(["Live LLM", "Cache only"], value="Live LLM", show_label=False,
                                    container=False, scale=3, min_width=200)
                    go = gr.Button("Plan my day", variant="primary", scale=2, min_width=140)
                check = gr.Checkbox(False, label="If infeasible, let the LLM re-read the request against the conflict "
                                           "(it may correct its own extraction, never the facts)")
                reword = gr.Checkbox(False, label="Let the LLM reword the explanation (kept only if every number "
                                            "and place name survives)")
                gr.HTML(f'<p class="ns-model">{model_line()}</p>')
            with gr.Column(scale=7, min_width=320):
                status = gr.HTML(verdict_html(None, kb))
        with gr.Tabs():
            with gr.Tab("Plan"):
                view = gr.HTML(result_html(None, kb), elem_classes="ns-view")
                with gr.Row(equal_height=False, elem_classes="ns-apply"):
                    fixes = gr.Dropdown(label="Apply one fix", choices=[], visible=False, scale=4)
                    apply = gr.Button("Apply and re-solve", variant="primary", visible=False, scale=1, min_width=180)
                with gr.Accordion("Explanation in words", open=False, elem_classes="ns-explain"):
                    explanation = gr.Textbox(show_label=False, lines=4, max_lines=14, interactive=False,
                                             elem_classes="ns-answer", placeholder="The explanation appears here.")
            with gr.Tab("Extracted form"):
                ir_box = gr.Code(language="json", interactive=True, show_label=True,
                                 label="TripRequestIR: the only thing the LLM produces. Edit and re-solve.")
                resolve = gr.Button("Re-solve with this form", variant="secondary")
                notes = gr.Markdown()
            with gr.Tab("Constraints"):
                cons = gr.HTML('<p class="ns-blank">The labelled constraints sent to Z3 appear here.</p>')
                with gr.Accordion("SMT-LIB sent to Z3", open=False):
                    smt = gr.Code(show_label=False)
            with gr.Tab(f"Places ({len(places)})"):
                gr.Dataframe(value=places, headers=["Name", "Id", "Category", f"Cost ({kb.currency})", "Open",
                                                    "Showtimes"], interactive=False, wrap=True)
        gr.HTML('<h2 class="ns-head" style="margin-top:28px">Examples</h2>')
        gr.Examples([[e["text"], json.dumps(e["ir"], indent=1)] for e in examples], inputs=[request, ir_box],
                    example_labels=[e["title"] for e in examples], visible_columns=[0], label=None,
                    elem_id="ns-ex")

        outs = [status, explanation, view, ir_box, notes, cons, smt, fixes, apply, last]
        go.click(on_plan, [request, mode, check, reword], outs)
        request.submit(on_plan, [request, mode, check, reword], outs)
        resolve.click(on_resolve, [ir_box], outs)
        apply.click(on_apply, [fixes, last], outs)
    return demo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--share", action="store_true", help="public gradio.live link")
    ap.add_argument("--port", type=int, default=7860)
    args = ap.parse_args()
    build().launch(share=args.share, server_port=args.port, css=CSS, theme=theme(), head=HEAD)


if __name__ == "__main__":
    main()
