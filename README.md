# 🥇 PSI08 — Proof-Carrying Data Analyst

An AI agent that answers questions about messy, multi-table data and attaches
**re-runnable code as the proof** of every number. If the code doesn't run, or
reproduces a different number, the answer scores 0. When the data can't support
an answer, it says so instead of guessing.

## Quick start (no API key needed)

```bash
pip install -r requirements.txt

python data/generate.py        # generate the messy dataset + gold answers
python eval/run_eval.py        # score all 18 questions (replay mode)
python verify.py               # judge check: re-run every proof script
python -m streamlit run streamlit_app.py
```

`verify.py` is the "someone else can run the code" check: it re-executes every
`answers/*.py` twice in a sandbox and compares the output to the agent's claim.

## Live / recording mode (needs a key once)

Put a key in `.env` (never committed):

```
LLM_PROVIDER=gemini            # or openai
LLM_API_KEY=...                # default model: gemini-3.5-flash-lite
AGENT_MODEL=gemini-3.5-flash-lite
```

```bash
$env:AGENT_MODE="record"; python eval/run_eval.py          # PowerShell
$env:AGENT_MODE="record"; python eval\record_extras.py     # extra demo phrasings
```

Every LLM response is cached under `cache/` keyed by prompt hash (153 calls
recorded). After one recording session the whole demo runs **keyless**
(`AGENT_MODE=replay`) - verified with `.env` removed entirely.

## Data Quality Auditor (`audit.html`, standalone browser tool)

Drop any CSV/TSV/XLSX on `audit.html` and it reports, 100% client-side:

- **missing data** (NA-like tokens, % per column, all-empty columns/rows)
- **wrong data** (non-numeric values in numeric columns, ambiguous DD/MM vs
  MM/DD dates, mixed date formats, out-of-range ages/percents, invalid emails,
  negatives where the name says positive, multi-currency amounts)
- **unwanted data** (exact duplicate rows, duplicate primary keys, constant
  columns, stray whitespace, category casing variants, IQR outliers)

Each issue shows severity, exact count, and example rows; plus a health score,
column profile, and data sample. The sticky bar has local search, and AI
(provider selectable in ⚙ settings):

- **Enter** — instant local search over the findings (works offline)
- **Ask AI** — an LLM answers using *only* a compact JSON digest of the
  findings (never the raw rows), either a tiny model on your PC or Gemini
- **🔬 AI second opinion** — after the deterministic rules scan, asks the same
  LLM to hunt for errors the rules missed ("rules + model second opinion")
- **💾 Save report** — downloads the whole report as a standalone `.html`

### Local model (free, private, offline) — recommended

```bash
# 1. install Ollama and pull a small model once
winget install Ollama.Ollama          # or from ollama.com
ollama pull qwen2.5:3b                # "smallest & best" sweet spot (~2 GB)

# 2. serve this page through the tiny proxy (avoids browser CORS)
python local_server.py                # → http://127.0.0.1:8000/audit.html
```

The browser then discovers your Ollama models automatically (`/local/tags`);
`local_server.py` is stdlib-only, binds 127.0.0.1, and forwards `/local/chat`
→ Ollama `/api/chat` (stream forced off, sane temperature/token defaults).
Ollama not installed? The page degrades gracefully and explains what to do.

Gemini remains an option (provider = Gemini in ⚙ settings, key → `localStorage`).

```bash
node audit_test.js                    # engine tests (40 checks, no deps)
node audit_ui_test.js                 # DOM smoke test (needs: npm i jsdom)
python local_server.py                # serve + proxy
# proxy plumbing test (fake Ollama):  python server_test.py
```

## How it works

```
question ─▶ dataset profile ─▶ [LLM #1] plan: answerable? traps? ambiguities?
                    │                     │
                    │                     ├─▶ refusal (category + reason, no code)
                    ▼                     ▼
              [LLM #2] codegen ──▶ answers/<ID>.py  (prints ANSWER: <json>)
                                        ▼
                     sandbox: AST import whitelist, timeout,
                              run twice → outputs must be identical
                                        ▼
                     Answer + Evidence + Code + Confidence + Traps
```

## The dataset (`data/raw/`, synthetic, modeled on real retail exports)

| file | mess planted |
|---|---|
| `sales_transactions.csv` | 3 date formats (legacy rows are forced-DD/MM), USD/EUR/INR per row, 120 exact duplicate rows, 74 missing amounts, 15 missing regions, negative returns |
| `products.csv` | category casing/padding inconsistency, missing categories |
| `product_catalog_export.csv` | contradicts `products.csv` on 8 products |
| `fx_rates.csv` | INR rates missing 2024-06-10..20 (unconvertible window) |
| `quarterly_targets.csv` | fiscal vs calendar quarter labels |
| `finance_memo.txt` | business rules: revenue def, FX policy, fiscal year starts April |

Gold answers live in `data/gold.json`, computed from ground truth before the
mess was applied.

## The 18 questions (`eval/questions.yaml`)

- **E1–E4** easy answerable (counts, means, distinct values)
- **M1–M6** messy answerable — require dedupe + null handling + date parsing + FX conversion
- **R1–R5** must refuse — `no_data` (2023), `missing_column` (profit), `unit_mismatch` (JPY, FX gap), `contradiction` (two catalogs)
- **A1–A3** must flag ambiguity — "Q3" (fiscal vs calendar), "Europe" vs EMEA, `03/04/2024` (DD/MM vs MM/DD)

## Scoring (`eval/run_eval.py`)

| type | award |
|---|---|
| answer | 55 correct + 25 proof reproduces + 20 evidence quality (rows, dupes, nulls, FX noted) |
| refuse | 60 right category (40 near-miss) + 25 reason quality (must cite evidence) |
| ambiguous | 40 flagged + 40 correct under a stated assumption + 20 proof |

Overall = points ÷ max points. Prints a per-question scoreboard and writes
`eval/last_score.json`.

## Current results (replay mode, no API key, data regenerated from seed)

| category | score |
|---|---|
| answers (E1–E4, M1–M6) | 980/980 (100%) — all correct, all proofs reproduce |
| refusals (R1–R5) | 500/500 (100%) — right category + evidence-citing reason |
| ambiguity (A1–A3) | 300/300 (100%) — flagged *and* answered under a stated assumption |
| proof reproducibility | 13/13 in eval, 20/20 in `verify.py` |
| **overall** | **100.0/100** |

The first recorded run scored 83.6; the deltas were an empty-scope fiscal
quarter (planner couldn't see the date span), a null answer printed instead of
a refusal, and two over-refusals. Fixes: monthly row counts + FX coverage in
the dataset profile, worked refusal/ambiguity examples in the planner prompt,
and a repair-then-degrade safety net in the pipeline.

## Rules encoded in the system

1. Every number must have re-runnable code — `verify.py` enforces it.
2. A confident wrong answer is worse than "I can't determine this" + a good reason.
3. Ambiguity must be surfaced (fiscal quarters, currency, date notation), not silently resolved.
