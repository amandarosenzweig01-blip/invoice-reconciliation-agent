"""Invoice reconciliation demo.

One page, laid out in the order a demo runs. The example-case dropdown lets
anyone see the system work without supplying their own documents.

    streamlit run app.py
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from pipeline.decide import DEFAULT_THRESHOLD
from pipeline.pipeline import run_pair
from pipeline.rules import Ledger

st.set_page_config(page_title="Invoice reconciliation", page_icon="📄", layout="wide")

SPEC_DIR = Path("data/specs")
VERDICT_STYLE = {
    "approve":  ("✅", "Approved", "#1a7f37"),
    "flag":     ("🚩", "Flagged for review", "#c0392b"),
    "escalate": ("⚠️", "Escalated to a person", "#b7791f"),
}

# One ledger per browser session, so a duplicate invoice number is caught
# across the cases run in a single sitting.
if "ledger" not in st.session_state:
    st.session_state.ledger = Ledger()


def example_cases() -> dict[str, dict]:
    """Label the dropdown by what each case demonstrates, not by case id."""
    out = {}
    for path in sorted(SPEC_DIR.glob("case_*.json")):
        spec = json.loads(path.read_text())
        defect = spec["defect"].replace("_", " ")
        scanned = " (scanned)" if spec["render"]["scanned"] else ""
        out[f"{spec['case_id']} — {defect}{scanned}"] = spec
    return out


def field_rows(model, checked: list[str], ungrounded: set[str], prefix: str):
    for name in checked:
        value = getattr(model, name, None)
        shown = "—" if value in (None, "") else str(value)
        flagged = f"{prefix}.{name}" in ungrounded
        mark = " ⟡" if flagged else ""
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:4px 0;"
            f"border-bottom:1px solid #eee;'>"
            f"<span style='color:#666;font-size:0.85rem'>{name}</span>"
            f"<span style='font-weight:600;{'color:#b7791f' if flagged else ''}'>"
            f"{shown}{mark}</span></div>",
            unsafe_allow_html=True)


st.title("Creator invoice reconciliation")
st.caption("Reads a partnership contract and an invoice, checks them against each other, "
           "and either approves, flags a specific discrepancy, or escalates when it "
           "cannot verify what it extracted.")

left, right = st.columns([2, 1])
with left:
    examples = example_cases()
    choice = st.selectbox("Load an example case", ["—"] + list(examples), index=1 if examples else 0)
with right:
    threshold = st.slider("Confidence threshold", 0.0, 1.0, DEFAULT_THRESHOLD, 0.05,
                          help="Below this share of verifiable extracted values, the case "
                               "escalates to a person instead of being judged.")

with st.expander("Or upload your own pair"):
    up_contract = st.file_uploader("Contract PDF", type="pdf", key="c")
    up_invoice = st.file_uploader("Invoice PDF", type="pdf", key="i")

contract_path = invoice_path = None
if up_contract and up_invoice:
    tmp = Path(tempfile.mkdtemp())
    contract_path = tmp / "uploaded_contract.pdf"
    invoice_path = tmp / "uploaded_invoice.pdf"
    contract_path.write_bytes(up_contract.getvalue())
    invoice_path.write_bytes(up_invoice.getvalue())
elif choice != "—":
    cid = examples[choice]["case_id"]
    contract_path = Path(f"data/contracts/{cid}_contract.pdf")
    invoice_path = Path(f"data/invoices/{cid}_invoice.pdf")

if st.button("Reconcile", type="primary", disabled=contract_path is None):
    with st.spinner("Reading both documents..."):
        started = time.perf_counter()
        result = run_pair(str(contract_path), str(invoice_path),
                          threshold=threshold, ledger=st.session_state.ledger)
        elapsed = time.perf_counter() - started

    icon, label, color = VERDICT_STYLE[result["verdict"]]
    st.markdown(
        f"<div style='border-left:5px solid {color};background:#fafafa;"
        f"padding:14px 18px;margin:18px 0;border-radius:4px;'>"
        f"<div style='font-size:1.15rem;font-weight:700;color:{color}'>{icon} {label}</div>"
        f"<div style='margin-top:6px;color:#333'>{result['explanation']}</div></div>",
        unsafe_allow_html=True)

    for finding in result["findings"]:
        if finding["message"] == result["explanation"]:
            continue
        if finding["severity"] == "blocker":
            st.error(finding["message"])
        else:
            st.warning(finding["message"])

    ungrounded = set(result["ungrounded_fields"])
    col_c, col_i = st.columns(2)
    with col_c:
        st.subheader("Contract")
        field_rows(result["contract"],
                   ["creator_name", "contract_id", "rate_usd",
                    "usage_window_start", "usage_window_end", "payment_terms_days"],
                   ungrounded, "contract")
    with col_i:
        st.subheader("Invoice")
        field_rows(result["invoice"],
                   ["vendor_name", "billing_on_behalf_of", "invoice_number",
                    "invoice_date", "contract_reference", "total_usd"],
                   ungrounded, "invoice")

    if ungrounded:
        st.caption("⟡ marks a value that could not be located in the source document. "
                   "These are the values worth checking by hand.")

    with st.expander("Run detail"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Latency", f"{elapsed:.1f}s")
        c2.metric("Cost", f"${result['cost_usd']:.4f}")
        c3.metric("Path", result["path"])
        grounding = result.get("grounding_rate")
        c4.metric("Grounding", "n/a" if grounding is None else f"{grounding:.0%}")
        st.caption("Cost shows $0.0000 on a cached run. Delete .cache/ to force a "
                   "genuine call.")
