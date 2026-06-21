# Furniture Auto Count

Training-free furniture counting from architectural drawings.

- **Method A — Vector tag auto-count:** reads product tags (CH.01, WS.04, TB.11…)
  straight from a vector PDF's text layer. Near-exact, no OCR, no training.
- **Method B — Visual symbol count:** CostX-style. Capture one symbol, search the
  sheet, tune tolerance, accept/reject, count.

See `PARAMETERS_GUIDE.md` for a full explanation of every setting.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

Two sample drawings (`sample_layout.pdf`, `sample2.pdf`) are included for testing.
