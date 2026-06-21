"""
Furniture Auto Count - deployable PoC (Streamlit).

Two ways to count, in one app:

  A.  Vector tag auto-count  - for drawings whose items carry text tags
      (CH.01, WS.04, TB.11 ...). Reads the PDF's embedded text layer directly,
      so the per-code count is near-exact (no OCR, no training). Best for
      drawings like `sample layout.pdf`.

  B.  Visual symbol count  - CostX-style. Capture ONE symbol with a box, search
      the sheet, tune the tolerance, accept/reject, count. Training-free. Best
      for symbol-only drawings with no usable text tags.

Run locally:   streamlit run app.py
Run in Docker: see Dockerfile  (docker build -t autocount . && docker run -p 8501:8501 autocount)
"""
from __future__ import annotations

import io
import re
from collections import Counter

import cv2
import fitz
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_cropper import st_cropper
from streamlit_image_coordinates import streamlit_image_coordinates

import autocount as ac

st.set_page_config(page_title="Furniture Auto Count", layout="wide")

# --------------------------------------------------------------------------- #
#  Session state
# --------------------------------------------------------------------------- #
ss = st.session_state
ss.setdefault("drawing", None)        # full-res BGR np.array (current page)
ss.setdefault("drawing_name", None)
ss.setdefault("template", None)       # last captured BGR np.array
ss.setdefault("templates", [])        # set of captured symbols to search together
ss.setdefault("matches", [])          # list[ac.Match] (auto + manual)
ss.setdefault("sel", None)            # index of the currently-selected detection
ss.setdefault("_last_click", None)    # dedupe image clicks across reruns
ss.setdefault("tally", [])            # saved item counts


def bgr_to_pil(img):
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


# --------------------------------------------------------------------------- #
#  Tag reading (Method A)
# --------------------------------------------------------------------------- #
KNOWN = {
    "CH": ("Chair",       (0, 170, 0)),
    "WS": ("Workstation", (220, 120, 0)),
    "TB": ("Table",       (0, 140, 255)),
}
CODE_RE = re.compile(r"^([A-Z]{1,3})[.,_\- ]?(\d{1,2})$")


def normalize_tag(word: str):
    m = CODE_RE.match(word.upper().strip())
    return f"{m.group(1)}.{int(m.group(2)):02d}" if m else None


def family_of(code: str):
    pfx = code.split(".")[0]
    return KNOWN[pfx][0] if pfx in KNOWN else f"{pfx} (confirm w/ catalog)"


def color_of(code: str):
    return KNOWN.get(code.split(".")[0], (None, (130, 130, 130)))[1]


# --------------------------------------------------------------------------- #
#  Sidebar - load drawing
# --------------------------------------------------------------------------- #
st.sidebar.title("📐 Furniture Auto Count")
st.sidebar.caption("Tag auto-count + CostX-style symbol counting — training-free")

up = st.sidebar.file_uploader("Drawing (PDF / PNG / JPG / TIF)",
                              type=["pdf", "png", "jpg", "jpeg", "tif", "tiff"])
dpi = st.sidebar.slider("PDF render DPI", 100, 400, 200, 50,
                        help="Higher = thin CAD lines survive. 200 is a good default.")

ss.setdefault("_pdf_bytes", None)

if up is not None and up.name != ss.drawing_name:
    data = up.read()
    ss._pdf_bytes = data if up.name.lower().endswith("pdf") else None
    if up.name.lower().endswith("pdf"):
        zoom = dpi / 72.0
        with fitz.open(stream=data, filetype="pdf") as doc:
            pages = []
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
                pages.append(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        ss._pages = pages
    else:
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        ss._pages = [arr]
    ss.drawing_name = up.name
    ss.matches = []

if "_pages" in ss:
    pg = 0
    if len(ss._pages) > 1:
        pg = st.sidebar.number_input("Page", 1, len(ss._pages), 1) - 1
    ss.drawing = ss._pages[pg]
    ss._page_idx = pg

if ss.drawing is None:
    st.info("⬅️  Upload a drawing to begin.")
    st.stop()

H, W = ss.drawing.shape[:2]
st.sidebar.success(f"Loaded: {ss.drawing_name}  ({W}×{H}px)")

method = st.sidebar.radio(
    "Counting method",
    ["A · Vector tag auto-count", "B · Visual symbol count"],
    help="A reads text tags from a vector PDF (near-exact). B captures a symbol "
         "and finds every match visually (for symbol-only drawings).")

# =========================================================================== #
#  METHOD A — vector tag auto-count
# =========================================================================== #
if method.startswith("A"):
    st.header("Vector tag auto-count")
    st.caption("Reads the product tags straight from the PDF's text layer — no OCR, "
               "no training. Near-exact for tagged drawings.")

    if ss._pdf_bytes is None:
        st.warning("This method needs a **vector PDF** (the uploaded file isn't one). "
                   "Upload a PDF, or use Method B for images / scans.")
        st.stop()

    with fitz.open(stream=ss._pdf_bytes, filetype="pdf") as doc:
        page = doc[ss._page_idx]
        page.set_rotation(0)                       # align text + render
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        tags = []
        for x0, y0, x1, y1, w, *_ in page.get_text("words"):
            code = normalize_tag(w)
            if code:
                tags.append((code, (x0 + x1) / 2 * zoom, (y0 + y1) / 2 * zoom))

    if not tags:
        st.warning("No text tags found on this page — it's likely a symbol-only "
                   "drawing. Switch to **Method B · Visual symbol count**.")
        st.stop()

    per_code = Counter(c for c, _, _ in tags)
    fam = Counter()
    for code, n in per_code.items():
        fam[family_of(code)] += n

    vis = img.copy()
    for code, cx, cy in tags:
        cv2.circle(vis, (int(cx), int(cy)), 13, color_of(code), 3)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.image(bgr_to_pil(vis), caption=f"{len(tags)} tagged items on this page",
                 use_container_width=True)
        ok, buf = cv2.imencode(".png", vis)
        st.download_button("⬇️ Annotated page (PNG)", buf.tobytes(),
                           "tag_count_annotated.png", "image/png")
    with c2:
        st.subheader("By family")
        st.dataframe(pd.DataFrame(sorted(fam.items(), key=lambda k: -k[1]),
                                  columns=["family", "count"]),
                     hide_index=True, use_container_width=True)
        st.subheader("By product code")
        code_df = pd.DataFrame(
            [(c, family_of(c), n) for c, n in
             sorted(per_code.items(), key=lambda k: -k[1])],
            columns=["code", "family", "count"])
        st.dataframe(code_df, hide_index=True, use_container_width=True, height=320)
        st.download_button("⬇️ Per-code CSV", code_df.to_csv(index=False),
                           "tag_count.csv", "text/csv")
    st.metric("Total tagged items (this page)", len(tags))
    st.stop()

# =========================================================================== #
#  METHOD B — visual symbol count (capture a box → find all)
# =========================================================================== #
st.header("1 · Capture a symbol")
st.caption("**Zoom in** with the sliders until one symbol is large, then drag a tight "
           "box around it. The mini-map on the right shows where you are.")

zc1, zc2, zc3 = st.columns(3)
with zc1:
    zoom = st.slider("🔍 Zoom", 1.0, 12.0, 4.0, 0.5,
                     help="Higher = closer. Zoom so the symbol is big and easy to box.")
with zc2:
    pan_x = st.slider("⬌ Pan X", 0, 100, 50)
with zc3:
    pan_y = st.slider("⬍ Pan Y", 0, 100, 50)

view_w = max(8, int(W / zoom))
view_h = max(8, int(H / zoom))
vx = max(0, min(int((W - view_w) * pan_x / 100), W - view_w))
vy = max(0, min(int((H - view_h) * pan_y / 100), H - view_h))
viewport = ss.drawing[vy:vy + view_h, vx:vx + view_w]

DISP = 820
dscale = DISP / view_w
interp = cv2.INTER_LINEAR if dscale > 1 else cv2.INTER_AREA
disp = cv2.resize(viewport, (DISP, max(1, int(view_h * dscale))), interpolation=interp)

cap_l, cap_r = st.columns([4, 1])
with cap_l:
    box = st_cropper(bgr_to_pil(disp), realtime_update=True, box_color="#e10600",
                     aspect_ratio=None, return_type="box")
    if box and box["width"] > 2 and box["height"] > 2:
        x = max(0, int(vx + box["left"] / dscale))
        y = max(0, int(vy + box["top"] / dscale))
        w = int(box["width"] / dscale)
        h = int(box["height"] / dscale)
        if w > 1 and h > 1:
            ss.template = ss.drawing[y:y + h, x:x + w].copy()

with cap_r:
    mini_w = 220
    msc = mini_w / W
    mini = cv2.resize(ss.drawing, (mini_w, max(1, int(H * msc))),
                      interpolation=cv2.INTER_AREA).copy()
    cv2.rectangle(mini, (int(vx * msc), int(vy * msc)),
                  (int((vx + view_w) * msc), int((vy + view_h) * msc)), (0, 0, 255), 2)
    st.image(bgr_to_pil(mini), caption="viewport on full sheet", use_container_width=True)
    if ss.template is not None and ss.template.size:
        st.image(bgr_to_pil(ss.template),
                 caption=f"captured {ss.template.shape[1]}×{ss.template.shape[0]}px",
                 use_container_width=True)

st.caption("Symbols come in a few styles / orientations. Capture a **few examples** "
           "and search them together for better coverage.")
ac1, ac2, ac3 = st.columns([2, 2, 6])
with ac1:
    if st.button("➕ Add symbol to set", disabled=ss.template is None):
        if ss.template is not None and ss.template.size:
            ss.templates.append(ss.template.copy())
with ac2:
    if st.button("🗑️ Clear set", disabled=not ss.templates):
        ss.templates = []
with ac3:
    st.write(f"**{len(ss.templates)}** symbol(s) in the search set")
if ss.templates:
    thumbs = st.columns(min(8, len(ss.templates)))
    for i, t in enumerate(ss.templates):
        with thumbs[i % len(thumbs)]:
            st.image(bgr_to_pil(t), width=70, caption=f"#{i+1}")

# --------------------------------------------------------------------------- #
#  Step 2 — search settings + run
# --------------------------------------------------------------------------- #
st.header("2 · Search settings")
item_name = st.text_input("Item / category name", "Chair")

sc1, sc2, sc3 = st.columns(3)
with sc1:
    show_above = st.slider("Show matches above %", 30, 99, 50,
                           help="Lower = finds more (and more false positives).") / 100.0
    auto_accept = st.slider("Auto-accept above %", 30, 99, 62) / 100.0
with sc2:
    rot_mode = st.select_slider("Rotation handling",
                                ["none", "90° steps", "every 30°", "every 15°"],
                                "90° steps")
    scale_tol = st.select_slider("Size tolerance", ["±0%", "±10%", "±20%"], "±10%")
with sc3:
    iou = st.slider("Overlap merge (IoU)", 10, 60, 30) / 100.0

angles = {"none": (0,), "90° steps": tuple(range(0, 360, 90)),
          "every 30°": tuple(range(0, 360, 30)),
          "every 15°": tuple(range(0, 360, 15))}[rot_mode]
scales = {"±0%": (1.0,), "±10%": (0.9, 1.0, 1.1),
          "±20%": (0.8, 0.9, 1.0, 1.1, 1.2)}[scale_tol]

search_set = ss.templates if ss.templates else (
    [ss.template] if ss.template is not None else [])

if st.button("🔍  Search drawing", type="primary", disabled=not search_set):
    with st.spinner(f"Matching {len(search_set)} symbol(s)…"):
        raw = []
        for t in search_set:
            raw += ac.search(ss.drawing, t, show_above=show_above,
                             scales=scales, angles=angles, iou_thresh=iou)
        ms = ac.non_max_suppression(raw, iou)
        for m in ms:
            m.accepted = m.score >= auto_accept
        ss.matches = ms
        ss.sel = None
        ss._last_click = None
    if not ms:
        st.warning("No matches. Try lowering 'Show matches above %', capturing a "
                   "tighter box, or adding a few more examples.")

# --------------------------------------------------------------------------- #
#  Step 3 — review & correct  (table <-> drawing are linked)
# --------------------------------------------------------------------------- #
def select(i):
    ss.sel = i
    st.rerun()


if ss.matches:
    st.header("3 · Review & correct")
    accepted = [m for m in ss.matches if m.accepted]
    n_manual = sum(1 for m in ss.matches if m.manual)
    sz = max(8, int(np.median([max(m.w, m.h) for m in ss.matches])))

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric(f"{item_name} — final count", len(accepted))
    mc2.metric("candidates", len(ss.matches))
    mc3.metric("added manually", n_manual)

    add_mode = st.toggle("➕ **Add mode** — click the drawing to add a symbol the "
                         "system missed (off: click a detection to inspect it)",
                         value=False)

    rc1, rc2 = st.columns([3, 2])

    # ---- draw all detections; selected = yellow, accepted = green, rejected = red
    vis = ss.drawing.copy()
    for i, m in enumerate(ss.matches):
        if i == ss.sel:
            col, th = (0, 255, 255), 4
        elif not m.accepted:
            col, th = (0, 0, 255), 2
        else:
            col, th = (0, 170, 0), 2
        cv2.rectangle(vis, (m.x, m.y), (m.x + m.w, m.y + m.h), col, th)
        if m.manual:
            cv2.drawMarker(vis, (m.cx, m.cy), (255, 0, 255), cv2.MARKER_CROSS,
                           max(14, m.w), 2)

    with rc1:
        # viewport: zoom to the selected detection, else show the whole sheet
        if ss.sel is not None and 0 <= ss.sel < len(ss.matches):
            ctx = st.slider("🔍 Zoom to selection", 2, 20, 7,
                            help="How much surrounding context to show.")
            m = ss.matches[ss.sel]
            half = int(max(m.w, m.h) * ctx)
            rx = max(0, min(m.cx - half, W - 2 * half)) if W > 2 * half else 0
            ry = max(0, min(m.cy - half, H - 2 * half)) if H > 2 * half else 0
            vw = min(2 * half, W)
            vh = min(2 * half, H)
        else:
            rx = ry = 0
            vw, vh = W, H

        crop = vis[ry:ry + vh, rx:rx + vw]
        DISPW = 760
        vscale = DISPW / vw
        small = cv2.resize(crop, (DISPW, max(1, int(vh * vscale))),
                           interpolation=cv2.INTER_AREA if vscale < 1 else cv2.INTER_LINEAR)
        st.caption("🟡 selected ・ 🟢 accepted ・ 🔴 rejected ・ ✚ manual"
                   + ("  —  click to **add**" if add_mode else "  —  click a box to **select**"))
        click = streamlit_image_coordinates(bgr_to_pil(small), key="reviewcanvas")
        if click is not None and click != ss._last_click:
            ss._last_click = click
            fx = int(rx + click["x"] / vscale)
            fy = int(ry + click["y"] / vscale)
            # nearest existing detection to the click
            ni, nd = None, 1e18
            for i, mm in enumerate(ss.matches):
                d = (mm.cx - fx) ** 2 + (mm.cy - fy) ** 2
                if d < nd:
                    ni, nd = i, d
            near = ni is not None and nd <= (sz * 1.5) ** 2
            if add_mode and not near:
                h = sz // 2
                ss.matches.append(ac.Match(fx - h, fy - h, sz, sz, 1.0, -1, True, True))
                select(len(ss.matches) - 1)
            elif ni is not None:
                select(ni)

        nav = st.columns([1, 1, 2, 1, 1])
        if nav[0].button("◀ Prev", use_container_width=True):
            select((0 if ss.sel is None else ss.sel - 1) % len(ss.matches))
        if nav[1].button("Next ▶", use_container_width=True):
            select((-1 if ss.sel is None else ss.sel + 1) % len(ss.matches))
        nav[2].markdown(
            f"<div style='text-align:center;padding-top:6px'>selected: "
            f"<b>{(ss.sel + 1) if ss.sel is not None else '–'}</b> / {len(ss.matches)}</div>",
            unsafe_allow_html=True)
        if nav[3].button("🔭 Full", use_container_width=True, help="Zoom out to full sheet"):
            select(None)

    with rc2:
        # ---- actions on the selected detection -----------------------------
        if ss.sel is not None and 0 <= ss.sel < len(ss.matches):
            m = ss.matches[ss.sel]
            tag = "manual" if m.manual else f"auto · score {m.score:.2f} · {m.angle}°"
            st.info(f"**Detection #{ss.sel + 1}** — {tag} — "
                    + ("✅ accepted" if m.accepted else "❌ rejected"))
            a1, a2, a3 = st.columns(3)
            if a1.button("✅ Accept", use_container_width=True):
                m.accepted = True
                st.rerun()
            if a2.button("❌ Reject", use_container_width=True):
                m.accepted = False
                st.rerun()
            if a3.button("🗑️ Delete", use_container_width=True,
                         help="Remove this detection entirely"):
                ss.matches.pop(ss.sel)
                select(None if not ss.matches else min(ss.sel, len(ss.matches) - 1))
        else:
            st.caption("Click a box on the drawing, a table row's checkbox, or use "
                       "Prev/Next to select a detection.")

        # ---- the table: untick 'accept' to reject AND jump to it -----------
        st.caption("Untick **accept** to reject a detection — the drawing jumps to it "
                   "so you can verify.")
        df = pd.DataFrame([{"#": i + 1, "score": round(m.score, 3), "angle": m.angle,
                            "source": "manual" if m.manual else "auto",
                            "accept": m.accepted}
                           for i, m in enumerate(ss.matches)])
        edited = st.data_editor(
            df, hide_index=True, height=300, use_container_width=True,
            disabled=["#", "score", "angle", "source"],
            column_config={"accept": st.column_config.CheckboxColumn()})
        if not edited["accept"].equals(df["accept"]):
            changed = None
            for i, val in enumerate(edited["accept"]):
                if bool(val) != ss.matches[i].accepted:
                    ss.matches[i].accepted = bool(val)
                    changed = i
            ss.sel = changed          # jump to the toggled detection
            st.rerun()

    # ---- save / export -----------------------------------------------------
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("✔️  Save to tally"):
            ss.tally = [t for t in ss.tally if t["item"] != item_name]
            ss.tally.append({"item": item_name, "count": len(accepted)})
            st.success(f"Saved {item_name}: {len(accepted)}")
    with b2:
        rows = [{"item": item_name, "source": "manual" if m.manual else "auto",
                 "center_x": m.cx, "center_y": m.cy,
                 "score": round(m.score, 4), "angle": m.angle}
                for m in accepted]
        st.download_button("⬇️  Export count CSV", pd.DataFrame(rows).to_csv(index=False),
                           f"{item_name}_matches.csv", "text/csv")
    with b3:
        ok, buf = cv2.imencode(".png", vis)
        st.download_button("⬇️  Export marked image", buf.tobytes(),
                           f"{item_name}_marked.png", "image/png")

# --------------------------------------------------------------------------- #
#  Step 4 — tally
# --------------------------------------------------------------------------- #
if ss.tally:
    st.header("4 · Estimation tally")
    tdf = pd.DataFrame(ss.tally)
    st.dataframe(tdf, hide_index=True, use_container_width=True)
    st.download_button("⬇️  Export estimation sheet (CSV)",
                       tdf.to_csv(index=False), "estimation_sheet.csv", "text/csv")
    if st.button("Clear tally"):
        ss.tally = []
        st.rerun()
