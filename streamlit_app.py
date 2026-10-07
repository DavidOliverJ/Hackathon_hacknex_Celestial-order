"""PSI08 - Proof-Carrying Data Analyst.  Streamlit demo UI.

    python -m streamlit run streamlit_app.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent import llm  # noqa: E402
from agent.profile import build_profile  # noqa: E402
from agent.sandbox import SandboxError, execute  # noqa: E402
from verify import GREEN, RESET, RED, YELLOW  # noqa: E402

RAW = ROOT / "data" / "raw"
st.set_page_config(page_title="Proof-Carrying Data Analyst", page_icon="🥇", layout="wide")

QUESTIONS = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text(encoding="utf-8"))[
    "questions"
]

SAMPLES = {
    "Easy": [q for q in QUESTIONS if q["id"].startswith("E")],
    "Messy": [q for q in QUESTIONS if q["id"].startswith("M")],
    "Must refuse": [q for q in QUESTIONS if q["id"].startswith("R")],
    "Ambiguity": [q for q in QUESTIONS if q["id"].startswith("A")],
}


def fmt_answer(v) -> str:
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"${v:,.2f}"
    return str(v)


def sidebar() -> None:
    with st.sidebar:
        st.title("🥇 PSI08")
        st.caption("Proof-Carrying Data Analyst")
        mode = llm.mode()
        color = {"replay": "🟢", "record": "🟡", "live": "🔴", "off": "⚪"}.get(mode, "⚪")
        cache_n = len(list((ROOT / "cache").glob("*.json")))
        st.markdown(
            f"{color} **mode:** `{mode}` · model `{llm.model_name()}`  \n"
            f"📼 cached LLM calls: **{cache_n}**"
        )
        if mode == "replay" and cache_n == 0:
            st.warning("Cache empty. Run `AGENT_MODE=record python eval/run_eval.py` once.")
        st.divider()

        st.subheader("Dataset")
        tables = sorted(p.name for p in RAW.glob("*"))
        pick = st.selectbox("table / document", tables)
        path = RAW / pick
        if path.suffix == ".txt":
            st.text_area("content", path.read_text(encoding="utf-8"), height=320, disabled=True)
        else:
            import pandas as pd

            df = pd.read_csv(path)
            st.caption(f"{len(df):,} rows × {len(df.columns)} cols")
            st.dataframe(df.head(25), width="stretch", hide_index=True)
        with st.expander("Full dataset profile (sent to the agent)"):
            st.text(build_profile())

        st.divider()
        st.subheader("Try a question")
        for label, qs in SAMPLES.items():
            st.caption(label)
            for q in qs:
                if st.button(q["question"], key=f"btn_{q['id']}", width="stretch"):
                    st.session_state["pending"] = q["question"]
                    st.rerun()


def render_evidence(ev: dict) -> None:
    if not ev:
        return
    st.markdown("**Evidence**")
    cols = st.columns(min(len(ev), 4) or 1)
    for i, (k, v) in enumerate(ev.items()):
        with cols[i % len(cols)]:
            label = str(k).replace("_", " ")
            st.metric(label, f"{v:,}" if isinstance(v, (int, float)) else str(v))


def render_result(res: dict) -> None:
    st.divider()
    if not res["answerable"]:
        st.error("**I can't determine this from the data.**", icon="🚫")
        st.markdown(f"**Category:** `{res['refusal_category']}`")
        st.info(res["reason"])
    else:
        verified = res["verified"]
        left, right = st.columns([3, 1])
        with left:
            st.markdown(f"### Answer: {fmt_answer(res['answer'])}")
        with right:
            st.markdown(
                f"{'🟢' if verified else '🔴'} **{'VERIFIED' if verified else 'UNVERIFIED'}**  \n"
                f"confidence: **{res['confidence']}**  \n"
                f"ran in {res['latency_s']}s · {res['model']} · mode `{res['mode']}`"
            )
        render_evidence(res.get("evidence") or {})

    if res.get("ambiguities"):
        with st.expander(f"⚠️ Ambiguity flagged ({len(res['ambiguities'])})", expanded=True):
            for a in res["ambiguities"]:
                if isinstance(a, dict):
                    st.markdown(
                        f"- **{a.get('aspect', '')}** → {', '.join(map(str, a.get('interpretations', [])))}  \n"
                        f"  _assumption:_ {a.get('assumption', '')}"
                    )
                else:
                    st.markdown(f"- {a}")

    if res.get("traps"):
        st.caption("Traps detected: " + " · ".join(f"`{t}`" for t in res["traps"]))

    if res.get("code"):
        with st.expander("📄 Proof code (re-runnable)", expanded=True):
            st.code(res["code"], language="python")
            if res.get("code_file"):
                c1, c2, _ = st.columns([1, 1, 2])
                if c1.button("▶️ Re-run proof", key=f"rerun_{res['id']}"):
                    try:
                        out = execute(ROOT / res["code_file"])
                        match = json.dumps(out.answer, default=str) == json.dumps(
                            res["answer"], default=str
                        )
                        if match:
                            c2.markdown(f"{GREEN}✓ PASS{RESET} — reproduced {out.answer_json}")
                        else:
                            c2.markdown(
                                f"{RED}✗ MISMATCH{RESET} — got {out.answer_json}, "
                                f"claimed {json.dumps(res['answer'])}"
                            )
                    except SandboxError as exc:
                        c2.markdown(f"{RED}✗ ERROR{RESET} — {exc}")
                c2.caption("runs twice in a sandbox, compares to the claim")


def ask(question: str) -> None:
    from agent.pipeline import run

    with st.spinner("Profiling dataset → planning → generating proof → verifying ..."):
        try:
            res = run(question, write_claim=True)
        except Exception as exc:  # cache miss, API down, etc.
            st.error(f"Agent failed: {exc}")
            if "no cached response" in str(exc):
                st.info(
                    "Run once with a key to record the cache:\n\n"
                    "`AGENT_MODE=record python eval/run_eval.py`"
                )
            return
    st.session_state.setdefault("history", []).insert(0, res)
    st.session_state["history"] = st.session_state["history"][:6]


def main() -> None:
    sidebar()
    st.subheader("Ask a question about the data")

    pending = st.session_state.pop("pending", None)
    q = st.chat_input(
        "e.g. What was the average order value in Q3 2024 in USD?",
    )
    if pending:
        ask(pending)
    elif q:
        ask(q)

    for res in st.session_state.get("history", []):
        st.caption(f"Q: {res['question']}")
        render_result(res)


if __name__ == "__main__":
    main()
