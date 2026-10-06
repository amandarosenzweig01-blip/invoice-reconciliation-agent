# Invoice reconciliation agent

> Reads a creator partnership contract and the invoice billed against it, checks
> them against each other, and either approves, flags a specific discrepancy, or
> escalates when it cannot verify what it extracted.

---

## The customer problem

A beauty brand runs dozens of creator partnerships a quarter. Each contract
specifies a creator, a fee, a set of deliverables, a usage window, and payment
terms. Weeks later an invoice arrives as a PDF from the creator or their agency,
in whatever format they happen to use. Someone on the marketing operations team
opens both documents and checks whether the invoice matches what was contracted.

**Who this is for:** a marketing operations manager who approves creator invoices
**What they do today:** open two PDFs side by side and compare them by hand
**What it costs:** a few minutes per invoice, and overpayments that nobody catches
because reading the contract carefully is the step that gets skipped when the
queue is long

## What it does

1. Reads the contract and the invoice, routing each to text extraction or vision
   depending on whether the PDF has a usable text layer
2. Pulls structured fields from both into a defined schema
3. Checks every extracted value against the source document to see whether it
   was actually read rather than reconstructed
4. Runs the reconciliation rules in plain Python: counterparty, fee, deliverable
   count, submission deadline, invoice scope, and duplicate detection
5. Returns one of three verdicts, with a plain-language reason

## The three verdicts

This is the design decision the whole project is built around.

| Verdict | Meaning |
| --- | --- |
| **approve** | The rules ran and found nothing |
| **flag** | The rules ran and something specific is wrong with the invoice |
| **escalate** | The rules did not run with enough confidence to be trusted |

A flag is a claim about the invoice. An escalation is an admission about the
extraction. Most systems collapse these into "something is wrong," which tells a
marketing ops manager that a perfectly good invoice is a problem. After that
happens a few times, people stop reading the flags.

The gate fires when too few extracted values can be located in the source, or
when a document has no text layer at all and there is nothing to check against.

## Architecture

```
contract.pdf ─┐
              ├─> router ─> extraction ─> grounding check ─┐
invoice.pdf ──┘   (text or    (schema)     (verifiable?)   │
                   vision)                                  v
                                                    confidence gate
                                                      │          │
                                              below   │          │ above
                                             threshold│          │threshold
                                                      v          v
                                                 escalate   reconciliation rules
                                                            (deterministic)
                                                                   │
                                                          approve ─┴─ flag
```

### Key design decisions

| Decision | What I chose | Why | What I gave up |
| --- | --- | --- | --- |
| Where the judgment happens | Plain Python rules, no model call in the decision layer | Reproducible, unit testable without spending a cent, and a finance team can read a rule and disagree with a specific line. Arithmetic is something computers have been reliably correct about for seventy years | Rules cannot handle a discrepancy nobody anticipated. A model might reason about a novel case; this will not |
| Confidence signal | Grounding: does the extracted value literally appear in the document | Self-reported model confidence is poorly calibrated. Grounding is cruder and checkable | A value can be grounded and still be the wrong field, for example picking up a subtotal that happens to match |
| Document routing | Text layer when there is one, vision only when there is not | Vision costs several times more per document. Paying it only when necessary is the difference between a demo and something that could run at volume | A 100-character threshold is a heuristic. An unusually sparse digital PDF would route to vision unnecessarily |
| Combining two grounding scores | Minimum, not mean | A scanned invoice paired with a clean digital contract would otherwise inherit the contract's confidence. The invoice is the document the verdict is about | The combined number is pessimistic on pairs where only one document is weak |
| Schema fields | Every field optional with a null default | A required field forces the model to produce something even when the document does not contain it, which is how you manufacture hallucinations | Downstream code has to handle None everywhere |
| Extraction caching | Payload-hashed disk cache | A threshold sweep re-runs the decision layer across the corpus without paying for extraction more than once | Cached runs report zero cost, so cost numbers must come from an uncached run |

## Results

Generated by `python run_eval.py --variant full-pipeline --compare-to extraction-only-v2`.
The baseline is the same 60 cases with the same extractions, scored with no
reconciliation layer (`--extraction-only`), so the delta is what the rules and
the confidence gate added and nothing else.

| Field | Extraction only | Full pipeline | Delta |
| --- | --- | --- | --- |
| creator_name | 100.0% | 100.0% | +0.0 pts |
| contract_rate_usd | 100.0% | 100.0% | +0.0 pts |
| invoice_total_usd | 98.3% | 98.3% | +0.0 pts |
| deliverable_count_contracted | 100.0% | 100.0% | +0.0 pts |
| deliverable_count_invoiced | 98.3% | 98.3% | +0.0 pts |
| is_exception | 53.3% | 91.7% | +38.3 pts |
| **mean** | **91.7%** | **98.1%** | **+6.4 pts** |

**Exception detection:** precision 100.0%, recall 82.1%, F1 90.2% (23 true
positives, 0 false positives, 5 missed). Every one of the 5 misses was an
escalation, not a wrong approval.

| Verdict | Cases | Share |
| --- | --- | --- |
| approve | 28 | 47% |
| flag | 23 | 38% |
| escalate | 9 | 15% |

**Latency and cost**, from an uncached run: p50 5.30s, p95 6.51s per pair,
$0.013 per pair, $0.78 for all 60. The reconciliation layer itself adds no
model calls.

**How the evaluation set was built.** 60 contract and invoice pairs across nine
defect types, split 20 dev and 40 test. The dev cases were inspected freely
while iterating. The test cases were run only at variant boundaries and never
examined individually, because patching a prompt against every failure fits the
prompt to the evaluation set and the number stops predicting anything.

**Three of the nine defect types are not exceptions.** A creator who signs as
"Ava Reyes" and bills as "Ava Reyes Creative LLC" has sent a correct invoice. So
has one whose contract writes the fee in words, or whose invoice omits the
contract reference. These cases exist so that precision means something: a
system that flags everything would score perfectly on recall and be useless.

| Defect | Count | Exception? | What it tests |
| --- | --- | --- | --- |
| clean | 20 | No | False positive rate on good invoices |
| vendor_name_variant | 5 | No | Whether the name matcher is too strict |
| rate_in_words | 4 | No | Extraction when the fee is written as prose |
| missing_reference | 3 | No | Whether the model invents a contract ID that is not there |
| rate_overcharge | 9 | Yes | The core arithmetic check |
| missing_deliverable | 7 | Yes | Counting across a nested structure |
| bundled_invoice | 4 | Yes | Noticing an invoice is out of scope rather than reconciling the half that matches |
| duplicate_invoice | 4 | Yes | State. Requires a ledger, not just the two documents in hand |
| late_invoice | 4 | Yes | Date arithmetic against the submission deadline |

Eight invoices have no text layer at all and are forced down the vision path.

**The decision layer is verified independently of the model.** One test feeds
ground truth straight into the rules, bypassing extraction entirely. It passes
at 28 true positives, 0 false positives and 0 false negatives across all 60
cases, which means any failure in a real run is an extraction failure rather
than a logic failure.

### The escalation tradeoff

Generated by `python -m tools.sweep_threshold`, conservative policy, all 60 cases.

| Threshold | Exception recall | Exception precision | Escalation rate | Auto-approved |
| --- | --- | --- | --- | --- |
| 0.50 | 82.1% | 100.0% | 15.0% | 46.7% |
| 0.65 | 82.1% | 100.0% | 15.0% | 46.7% |
| 0.75 | 82.1% | 100.0% | 15.0% | 46.7% |
| 0.85 | 82.1% | 100.0% | 21.7% | 40.0% |
| 0.95 | 82.1% | 100.0% | 21.7% | 40.0% |

The threshold barely matters on this corpus. Every text-path pair grounds at
100% except the four `rate_in_words` contracts, which ground at 83% because a
fee written as prose never appears as digits. Raising the threshold to 0.85
sends those four correct invoices to a person and catches nothing new.

Two escalation policies are available. The conservative one escalates any
document it cannot verify. The permissive one judges them anyway.

| Policy | Exception recall | Escalation rate |
| --- | --- | --- |
| Escalate unverifiable invoices | 82.1% | 15.0% |
| Judge them anyway | 96.4% | 0.0% |

**Chosen policy and threshold:** escalate unverifiable invoices, at 0.75. About
one invoice in seven reaches a person, which marketing ops can absorb. The
permissive policy catches four more exceptions, but its one miss is the reason
not to use it: it approved an overcharged invoice whose total it had never
read. A missed exception that goes to a person costs a few minutes. One that is
auto-approved costs the overpayment.

## Known failure modes

| Failure | Frequency | How it is handled today | What I would do with more time |
| --- | --- | --- | --- |
| No grounding signal on the vision path | Every scanned document, 8 of 60 cases | Escalated to a person rather than judged, which costs 4 genuine exceptions in recall (two late invoices, one overcharge, one missing deliverable) | Run OCR on the rendered page and ground against that text, which would give the vision path the same verification the text path has |
| Empty extraction from a clean digital invoice | 1 of 60 (case_017, an overcharge) | The model returned a tool call with every field null. With nothing to ground, the invoice escalates, so it reaches a person instead of being approved. The escalation message wrongly blames a missing text layer | Treat an all-null extraction as its own failure: retry once, then escalate with an accurate reason |
| Bundled invoices are flagged but not attributed | 4 of 60 | All 4 correctly flagged as out of scope, so a person reviews them | The schema assumes one contract per invoice. Supporting bundles means a different data model, not a better prompt |
| Grounded but wrong | Not observed in 60 cases. The only field errors were the nulls from the empty extraction | Undetected. A value can appear verbatim in the document and still be the wrong field | Ground against the specific region of the document a field was read from, not the whole text |
| Name matching threshold is empirical | 0 errors in 60. All 5 name variants passed and no different name was matched | Fuzzy match at 85, chosen by running the matcher over the dev set and finding where legitimate variants and genuinely different names separate | Validate against real creator and agency names rather than generated ones |

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY

python tools/generate_corpus.py   # 60 specs, 120 PDFs
python tools/specs_to_golden.py   # evals/golden.jsonl
python -m pytest tests/ -q        # 28 passed, no API calls

python run_eval.py --variant extraction-only-v2 --extraction-only
python run_eval.py --variant full-pipeline --compare-to extraction-only-v2
python -m tools.sweep_threshold
python -m tools.sweep_threshold --judge-unverifiable
streamlit run app.py
```

Corpus generation is deterministic given the seed, so anyone who clones this
repo reproduces the exact same 60 cases.

Regenerating the PDF corpus uses WeasyPrint, which needs Pango
(`brew install pango`). On Apple Silicon Macs, Homebrew's libraries aren't on
the default search path, so also run:

```bash
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH
```

## Repo layout

```
pipeline/
  routing.py     text layer or vision, the cost decision
  schemas.py     the extraction contract, also the tool schema sent to the model
  extract.py     forced tool use, retry on validation failure, payload cache
  grounding.py   does the extracted value appear in the source
  rules.py       the deterministic checks, no model calls
  decide.py      the three-way verdict and the confidence gate
tools/
  scenarios.py        spec generation and the nine defect injectors
  generate_corpus.py  renders specs to PDFs
  specs_to_golden.py  specs to the labeled evaluation set
  sweep_threshold.py  the escalation tradeoff table
evalkit/         the evaluation harness, shared across my portfolio projects
```

## What I would build next

- OCR-based grounding so the vision path gets a verification signal instead of a
  blanket escalation
- A ledger backed by storage rather than process memory, so duplicate detection
  survives a restart
- Field-level provenance, recording which region of which page each value came
  from, which would turn grounding from a yes or no into a location

---

**Data note.** The corpus is synthetic. Real creator contracts are confidential,
so I wrote a generator that produces a ground-truth spec, mutates it with one of
nine defect injectors, and renders contract and invoice PDFs from the result.
Because the mutation and the label are written in the same function, the labels
cannot drift from the documents. Eight invoices are re-rendered as rotated,
blurred, image-only PDFs to simulate a phone scan, and each is verified to have
no recoverable text layer. Six document layouts, three per document type, keep
the extractor from memorizing a single template.
