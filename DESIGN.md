---
name: Trip Synthesizer
description: A verified one-day plan drawn as a railway time-space chart on cool timetable paper.
colors:
  timetable-paper: "#f5f6f7"
  sheet-white: "#ffffff"
  ink: "#1c1f24"
  ink-secondary: "#474e58"
  ink-tertiary: "#646c78"
  hairline: "#dfe3e7"
  hairline-strong: "#c3c9d0"
  opening-window: "#e4e8ec"
  row-wash: "#eef0f2"
  verified-teal: "#16726b"
  conflict-vermilion: "#c13a26"
  caution-amber: "#9a5b06"
  error-ink: "#8f2617"
  error-wash: "#fdf1ee"
typography:
  display:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "44px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.03em"
    fontVariation: "'wdth' 88"
  headline:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    letterSpacing: "-0.015em"
    fontVariation: "'wdth' 92"
  title:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    fontFeature: "'tnum' 1"
  body:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.08em"
    fontVariation: "'wdth' 75"
  chart-figure:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
    letterSpacing: "0.02em"
    fontVariation: "'wdth' 80"
    fontFeature: "'tnum' 1"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "12.5px"
    fontWeight: 400
rounded:
  none: "0px"
spacing:
  hair: "4px"
  xs: "6px"
  sm: "12px"
  md: "18px"
  layout-gap: "20px"
  lg: "28px"
  gutter: "32px"
  chart-row: "52px"
  chart-label-column: "244px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet-white}"
    rounded: "{rounded.none}"
    padding: "12px 22px"
  button-primary-hover:
    backgroundColor: "#000000"
    textColor: "{colors.sheet-white}"
  button-secondary:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "12px 22px"
  button-secondary-hover:
    backgroundColor: "{colors.row-wash}"
    textColor: "{colors.ink}"
  input-text:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "12px 14px"
  verdict-word-feasible:
    textColor: "{colors.verified-teal}"
    typography: "{typography.display}"
  verdict-word-infeasible:
    textColor: "{colors.conflict-vermilion}"
    typography: "{typography.display}"
  chart-visit-bar:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet-white}"
    rounded: "{rounded.none}"
    height: "22px"
    padding: "0 6px"
  chart-opening-window:
    backgroundColor: "{colors.opening-window}"
    height: "28px"
  tab-active:
    textColor: "{colors.ink}"
    padding: "10px 18px 10px 0"
  tab-inactive:
    textColor: "{colors.ink-tertiary}"
---

# Design System: Trip Synthesizer

## Overview

**Creative North Star: "The Graphic Timetable"**

The system is a railway timetable sheet. The day is drawn as a Marey time-space chart: time runs across, the places of the day run down in visiting order, each visit is a heavy ink bar and each journey is the diagonal hairline between rows. Everything else on the page (the request box, the verdict, the constraint list, the tabs) is drawn in the same drafting language: cool paper, one ink, hairline rules, square corners, tabular figures. The reader should be able to check the plan by eye against the grid, the way a timetable clerk checks a train path.

The sheet is light and stays light, including when the operating system is in dark mode; the theme copies every light value into its dark slot and declares `color-scheme: light`. Density is that of a printed reference table: tight rows, small condensed caps for column heads, generous horizontal rules instead of boxes. Colour is almost absent. Two saturated inks exist, and both belong to the solver's verdict.

This world rejects the card dashboard: no floating panels, no drop shadows on content, no rainbow-coded Gantt bars, no rounded chips.

**Key Characteristics:**
- One ink (#1c1f24) on cool timetable paper; hierarchy comes from weight, width and rules, not colour.
- Hairline grid: hour lines and row dividers in two greys, heavy ink rules framing each table or chart.
- Archivo across the whole sheet, its width axis condensed for column heads and chart figures; tabular numerals everywhere.
- Teal means verified, vermilion means conflict; nothing else is saturated.
- Zero radius on every rectangle.

## Colors

A near-monochrome drafting palette: cool grey paper, a blue-black ink in three strengths, two hairline greys, and two verdict inks used sparingly.

### Primary
- **Timetable Ink** (ink): All primary text, the visit bars, travel diagonals, the heavy rules that open and close the chart, constraint table and conflict list, the primary button fill, the active tab underline, focus outlines, text selection.

### Secondary
- **Verified Teal** (verified-teal): The solver said sat and the independent checker accepted. Used for the "Feasible" verdict word, its 3px top rule, the `sat` and `0 violations` proof values, and the "restores feasibility" mark on a fix.
- **Conflict Vermilion** (conflict-vermilion): The solver said unsat. Used for the "Infeasible" verdict word and its top rule, the `unsat` proof value, the cross-hatch swatch on each conflicting requirement, and the rows of the minimal conflict in the constraints table. Also the border and icon of Gradio's error toast.

### Tertiary
- **Caution Amber** (caution-amber): The "Needs clarification" verdict word and top rule only.

### Neutral
- **Timetable Paper** (timetable-paper): Page background, and the knock-out chip behind labels that sit over the chart (hatched-bar times, travel minutes, narrow-bar times).
- **Sheet White** (sheet-white): Input and code fields, the secondary button, the hovered chart row, even table rows. The only surface lighter than the paper.
- **Ink Secondary** (ink-secondary): Masthead deck, section heads, supporting summary line, chart travel labels, the explanation text.
- **Ink Tertiary** (ink-tertiary): Inactive tabs, axis hour labels, proof-row labels, row metadata, the dashed waiting line, showtime ticks, "not enough on its own".
- **Hairline** (hairline): Half-hour grid lines, row dividers, cell dividers in the proof row and tables.
- **Hairline Strong** (hairline-strong): Hour grid lines, the rule under each section head, input borders, the neutral verdict rule, scrollbar thumb.
- **Opening Window** (opening-window): The pale band in each chart lane showing when a place is open.
- **Row Wash** (row-wash): Hover fill for the secondary button and focused table rows.
- **Error Ink / Error Wash** (error-ink, error-wash): Text and fill of Gradio's error toast only.

### Named Rules
**The Verdict Ink Rule.** Teal and vermilion are spent only on what the solver decided: the verdict, its proof values, the conflict and whether a fix restores feasibility. Buttons, tabs, links and chart bars stay ink.

**The Not-Only-Red Rule.** A conflict is always marked by shape as well as colour: the vermilion cross-hatch swatch sits beside every conflicting requirement, and core rows in the constraints table carry the same swatch plus bold weight.

## Typography

**Display Font:** Archivo (variable, width 62–125, weight 300–800), with ui-sans-serif, system-ui, sans-serif
**Body Font:** Archivo
**Label/Mono Font:** JetBrains Mono (400, 500), with ui-monospace, monospace

**Character:** A grotesque with a real width axis, so one family supplies both the compact verdict word and the narrow timetable column heads. Mono is reserved for machine text so the reader can tell at a glance what the LLM or Z3 produced.

### Hierarchy
- **Display** (700, 44px, line-height 1, -0.03em, width 88%): The verdict word only ("Feasible", "Infeasible"). Drops to 34px under 760px. The empty state "No plan yet" uses 600 at 28px in ink.
- **Headline** (700, 26px, -0.015em, width 92%): The masthead title; the city follows in weight 400, ink tertiary.
- **Title** (400, 17px): The one-line verdict summary (visits, span, spend).
- **Body** (400, 15px; 1.55 in long text): Inputs, conflict descriptions, fixes, error messages. Long text is held to 62–70ch.
- **Label** (600, 11–12px, 0.08em, uppercase, width 75%): Section heads (12px) and proof-row, tag and table column heads (11px). These are column heads naming the block beneath them, never decorative lines above a headline.
- **Chart Figure** (400, 12.5px, 0.02em, width 80%): Hour labels on the axis; row metadata uses the same width at 11px; visit-bar times are 600 at 12px.
- **Mono** (400, 12.5px): Constraint ids, place ids (10.5px under row names), the extracted IR, SMT-LIB.

### Named Rules
**The Tabular Figures Rule.** Every number on the sheet is tabular (`font-variant-numeric: tabular-nums` on the container, inputs and textareas) so times and money align down a column.

**The Machine Text Rule.** JetBrains Mono marks text a machine produced or consumes (cids, place ids, IR JSON, SMT-LIB) and nothing else.

## Layout

A single centred sheet, max 1320px wide with 32px side gutters and 48px bottom margin (16px gutters and 32px bottom under 760px). A masthead row (title left, deck right, flex-wrapped) closes with a 1px ink rule. Below it a two-column row in a 5:7 ratio: the request column (textbox, mode radio, primary button) on the left, the verdict on the right, each with a 320px minimum width so they stack on narrow screens. Tabs then run full width under both, followed by the examples.

Vertical rhythm comes from rules and a small set of gaps: 20px between Gradio blocks, 14px under a section head, 18px before the proof row and the explanation accordion, 22px above tab content, 28px before a following section. Blocks carry no padding or background of their own; the paper shows through everywhere.

The chart uses a 244px label column (132px under 760px, where the label column also becomes sticky so place names stay visible while the lanes scroll) and a lane area in percent of the day horizon. Rows are a fixed 52px. Hour lines are major; half-hour lines appear when the horizon is 10 hours or less, and the hour step doubles past 12 hours. The chart keeps a 760px minimum width and scrolls horizontally inside its own view rather than compressing.

Small-screen rules for the page shell live in the HEAD `<style>` block, because Gradio 6 scopes the `css=` string under `.gradio-container` and page-level selectors written there never reach the body (open item, see Do's and Don'ts).

## Elevation & Depth

The sheet is flat. Blocks, buttons, inputs and checkboxes all set their shadows to none, and depth is expressed by ink weight: heavy 1px ink rules frame tables and the chart, lighter hairlines divide inside them. The only lift on the sheet is the hovered chart row, which turns white while the other rows, the route and the travel labels fade to 30% opacity.

### Shadow Vocabulary
- **Overlay** (`box-shadow: 0 8px 24px rgba(28,31,36,.12)`): Gradio's large drop shadow, for floating overlays such as dropdown menus. Never on content.

### Named Rules
**The Rule-Not-Box Rule.** Group content with horizontal rules, not with bordered or shadowed containers. A bordered box is for an editable field or raw output (`pre`), not for grouping.

## Shapes

Every rectangle is square-cornered (radius 0 through Gradio's `radius_none` and explicit overrides on example items). Borders are 1px; emphasis rules are 3px (verdict top rule, active tab underline). Chart strokes are 1.5px: travel diagonals solid ink, waiting segments ink tertiary dashed 4/4, showtime ticks ink tertiary. The one curved form is the station dot: a 10px circle with a 2px ink ring on paper, marking leave and return points. It is a timetable symbol, not a softened corner, and stays the only circle.

Two hatches carry meaning. A 135-degree single hatch (ink 2px, white 3px) fills a visit fixed to a showtime. A crossed 45/-45 degree hatch in vermilion marks a conflicting requirement.

## Components

### Buttons
Ink slabs, flat and square.
- **Shape:** square (0px).
- **Primary:** ink fill, white 600 15px label, 1px ink border, 12px 22px padding ("Plan my day", "Apply and re-solve").
- **Hover / Focus:** fill deepens to pure black over 0.15s; no lift, no transform, no shadow. Focus is the global 2px ink outline at 2px offset.
- **Secondary:** white fill, ink text and 1px ink border; hover washes to row-wash ("Re-solve with this form").

### Inputs / Fields
- **Style:** white field, 1px hairline-strong border, 12px 14px padding, 15px text, no shadow.
- **Focus:** border goes ink and gains a 1px ink ring (`0 0 0 1px`), reading as a 2px ink stroke.
- **Read-only answer text:** no box at all: transparent, a 1px left hairline-strong rule, 14px indent, ink secondary at 1.55 line height.

### Navigation (tabs)
Text tabs on a 1px ink baseline. Inactive: 600 14px ink tertiary, no background. Active: ink with a 3px inset ink underline. Under 760px tabs tighten to 13px with 14px spacing.

### Radio and checkbox
Transparent labels with no chip; a white control with ink tertiary border that fills ink when selected.

### Verdict block
The signature reading point. A 3px top rule in the verdict colour (hairline-strong when neutral), the display-size verdict word, a title-size summary, an optional ink secondary second line, then a proof row: a definition list in an auto-fit grid (150px minimum cells) separated by hairlines, each cell a condensed label over a 600 15px value. Values that carry the verdict take its colour.

### Time-space chart
The signature component. Axis of hour labels (edge hours in ink 600), framed top and bottom by 1px ink rules, hairline hour grid, one 52px row per stop. Each lane may show the opening window (pale 28px band), showtime ticks, and the visit as a 22px ink bar with its times in white. Showtime visits use the single hatch with their times on a paper chip. Bars too narrow for their label push it outside (right, or left near the end of the day). An SVG layer draws travel diagonals and dashed waits; travel minutes float on paper chips. Hovering a visit row whitens it and dims everything else to 30%. A key under the chart names every mark in the same drawing.

### Conflict list
A numbered list under an ink rule: crossed vermilion hatch, mono constraint id, plain-language description, and a condensed tag ("your requirement" or "fact about the place"), divided by hairlines. Below, a section-headed list of fixes, each with a teal "restores feasibility" or ink tertiary "not enough on its own".

### Constraints table
Full-width collapsed table: condensed 11px column heads over a 1px ink rule, hairline row dividers, mono ids. Rows in the minimal conflict are vermilion 600 with the hatch swatch.

### Accordions
Plain 600 14px label on the paper, no box. The intended marker is an 8px ink chevron drawn with two 1.5px borders.

## Do's and Don'ts

### Do:
- **Do** keep every rectangle at 0px radius; the only circle is the 10px station dot.
- **Do** spend verified-teal and conflict-vermilion only on solver verdicts, proof values, the conflict and fix outcomes.
- **Do** pair every vermilion conflict mark with the crossed hatch swatch.
- **Do** use the condensed uppercase label style (11–12px, 600, 0.08em, width 75%) only as a column head that names the block or column directly beneath it.
- **Do** separate groups with 1px rules (ink to frame, hairline to divide) instead of boxes or shadows.
- **Do** set numbers in tabular figures and reserve JetBrains Mono for ids, IR and SMT-LIB.
- **Do** keep the light sheet in OS dark mode by copying every theme value into its `_dark` slot.

### Don't:
- **Don't** build card dashboards: no floating panels, no drop shadows on content, no rounded chips.
- **Don't** colour-code chart bars by category; visits are ink, showtime visits are hatched ink.
- **Don't** fill the primary button with teal or vermilion; pressable things are ink.
- **Don't** add lift, scale or shadow on hover; state changes are fill or opacity only, and all transitions switch off under `prefers-reduced-motion`.

### Open items (recorded, not decided)
- Fonts are bundled (`src/nstrip/app/fonts/`, SIL OFL) and inlined into the page head, so the UI looks the same offline.
- Gradio 6 scopes the `css=` block under `.gradio-container`, so the page-level small-screen rules currently live in the HEAD `<style>` block. This is a workaround for the framework, not a styling convention.
