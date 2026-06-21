# Furniture Auto Count — Parameters Guide

A simple, non-technical guide to every setting in the app, what it does, and how
to adjust it to get the result you want.

The app has **two counting methods**. Pick the one that matches your drawing:

- **Method A · Vector tag auto-count** — for drawings where items have text tags
  (e.g. `CH.01`, `WS.04`, `TB.11`). Most accurate, almost nothing to tune.
- **Method B · Visual symbol count** — for symbol-only drawings with no usable
  text. You capture one symbol and the app finds all the matching ones.

---

## Method A · Vector tag auto-count

This method reads the tag text directly out of the PDF, so the count is
near-exact and needs no tuning.

| Setting | What it does | When to change it |
|---|---|---|
| **PDF render DPI** (100–400, default 200) | Only controls how sharp the on-screen preview image looks. It does **not** affect the count — counting is done from the PDF's text, not the picture. | Raise to 300–400 only if the preview image looks blurry. |
| **Page** | Selects which sheet of a multi-page PDF to count. | When your PDF has more than one page. |

**Tip:** If the app says "No text tags found," the drawing has no readable text
tags — switch to Method B.

---

## Method B · Visual symbol count

How it works in one line: you draw a box around **one** symbol, and the app
slides that picture across the whole drawing, scoring every spot from 0–100% for
how closely it matches. You then review and confirm the results.

### Step 1 — Capturing the symbol

| Setting | What it does |
|---|---|
| **Zoom / Pan X / Pan Y** | Navigation only — they help you get close enough to draw a clean box. They have **no effect** on the results. |
| **The box you draw** | This is the symbol the app will search for. **It is the single most important input.** Draw it **tight**: include the symbol, leave out nearby text, dimension lines, and other clutter. A messy box gives messy results. |
| **➕ Add symbol to set** | Saves the current symbol into a set so you can search several examples at once (e.g. the same chair drawn at different angles or styles). |
| **🗑️ Clear set** | Empties the saved set so you can start over. |

### Step 2 — Search settings

| Setting | Range (default) | What it does |
|---|---|---|
| **Show matches above %** | 30–99 (50) | The detection threshold. A spot must score at least this much to show up at all. **Lower = finds more** (but more false matches). **Higher = fewer, cleaner** matches. |
| **Auto-accept above %** | 30–99 (62) | Any match scoring at least this is automatically ticked as accepted (shown green). Matches between "Show" and "Auto-accept" appear but wait for your review. |
| **Rotation handling** | none / 90° steps / every 30° / every 15° | How many rotated versions of your symbol to try. More angles catch rotated symbols but make the search **slower**. |
| **Size tolerance** | ±0% / ±10% / ±20% | Lets the app match symbols drawn slightly larger or smaller than your captured one. Wider tolerance catches more but is slower and can add false matches. |
| **Overlap merge (IoU)** | 10–60 (30) | After searching, boxes that overlap are merged so each symbol is counted once. **Lower = merges more aggressively** (use when one symbol gets several boxes). **Higher = keeps boxes that sit close together** (use when real symbols are packed tightly). |

### Step 3 — Review & correct (this is what makes the count exact)

- The drawing and the results table are linked. Click any box on the drawing,
  or any row in the table, to inspect a detection.
- **Accept / Reject / Delete** — confirm or remove any single detection.
- **Add mode** — turn this on and click directly on the drawing to add a symbol
  the app missed.
- **Untick "accept"** in the table to reject a detection; the drawing jumps to it
  so you can verify.

This manual cleanup step is how you turn an automatic estimate into an exact,
trustworthy count.

### Step 4 — Tally & export

- **Save to tally** — stores the count for this item so you can count several
  item types and build a full estimation sheet.
- **Export CSV / Export marked image** — download the counts and an annotated
  drawing for your records.

---

## Quick recipes

### "I need only the EXACT symbol" (no false matches)
1. **Show matches above %** → raise to **70–85**
2. **Auto-accept above %** → raise to **~80**
3. **Size tolerance** → **±0%**
4. **Rotation handling** → **none** (or **90° steps** if it can be rotated)
5. Capture a **very tight, clean box** of just that symbol
6. In Step 3, reject any leftover wrong boxes

### "Get the MAXIMUM number of shapes" (catch everything)
1. **Show matches above %** → lower to **40–45**
2. **Size tolerance** → **±20%**
3. **Rotation handling** → **every 30°** (or 15° for odd angles)
4. Capture **3–5 example symbols** with **➕ Add symbol to set** and search them
   together — this is the biggest improvement to coverage
5. **Overlap merge (IoU)** → lower (~15–20) so duplicate boxes collapse into one
6. In Step 3, use **Add mode** to click any missed symbols, and reject false ones

> Note: maximum coverage is **slower**, because the app tries every angle and
> size for every example symbol. Start with the defaults and widen the settings
> only if you are missing symbols.

---

## Recommended workflow

1. Start with the defaults (Show 50, Auto-accept 62, 90° steps, ±10%, IoU 30).
2. Run the search and look at the results.
3. **Missing symbols?** → lower "Show %", widen rotation/size, add more examples.
4. **Too many wrong matches?** → raise "Show %", set size to ±0%, reduce rotation.
5. Do the final clean-up by hand in Step 3 — this gives you an exact count.
