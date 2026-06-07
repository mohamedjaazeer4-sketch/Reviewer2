# Reviewer2 — Postmortem (honest, critical)

> A genuine engineering + scientific critique of v0.1.0, written as if a skeptical senior
> reviewer (half staff-engineer, half clinical-variant-scientist) spent an afternoon reading
> the actual code — not the marketing.
>
> Date: 2026-06-06 · Verdict: **a strong portfolio scaffold with one load-bearing weakness in
> the evaluation, and a known scientific under-call, that must be owned out loud.**

---

> **These findings were verified by running the code, not by reading it.** The four load-bearing
> claims below were reproduced live on 2026-06-06:
> | Claim | §  | Verified result |
> | --- | --- | --- |
> | BRCA1 null without the fixture PS1 flag → VUS | 3.2 | `PVS1+PM2+PP3 (all supporting) ⇒ Uncertain significance` |
> | TP53 null → VUS (truth was bent to match engine) | 3.1/3.2 | same: `⇒ Uncertain significance` |
> | `make app` is broken | 5 | `app/streamlit_app.py` MISSING |
> | Provenance hash ignores staleness | 3.4 | identical hash `e2b5a354c1d26a31` for stale vs non-stale |

## 0. The one-paragraph truth

Reviewer2 is well-built *software*: clean types, a deterministic auditable core, graceful
fallbacks, real tests, MCP, a nice CLI. But two things are weaker than the README implies. **(1)
The headline "100% catch / 0% false-positive" metric is largely circular** — the test set's
"ground truth" was authored to match what the engine itself produces, and every injected error is
cross-band, so catching them is nearly guaranteed *by construction*. **(2) The science under-calls
true loss-of-function variants** because PVS1 is hard-capped to "Supporting," which means a clean
nonsense variant in BRCA1 that is absent from gnomAD lands at **VUS** unless a fixture flag rescues
it. Both are fixable, and both are *more* impressive to discuss honestly than to hide. This
document is the plan to do that.

---

## 1. Scorecard

| Dimension | Grade | One-line justification |
| --- | :---: | --- |
| Software engineering | **A−** | Typed, modular, injectable providers, graceful fallback, mypy/ruff clean. |
| Reproducibility infra | **B+** | `provenance_hash` + lockfile + deterministic core — but the hash misses a conclusion-affecting input (see §3.4). |
| Test suite | **B** | 19 tests pin the rules table and key behaviours; but they test plumbing, not correctness against a gold standard. |
| **Evaluation (ErrorCatch)** | **C** | Methodology is presented honestly *as a harness*, but the numbers are near-tautological (§3.1). This is the biggest gap. |
| ACMG scientific fidelity | **C+** | Faithful combining-rule table, but the PVS1 cap causes systematic under-calling (§3.2), and several criteria are fixture-fabricated (§3.3). |
| Domain framing / narrative | **A** | The "second reviewer," staleness, action-band story is genuinely sharp and role-relevant. |
| Honesty of docs | **B+** | Scope boundaries are stated; but the README's headline metric oversells what the eval proves. |

**Net:** great *vehicle*, and the honesty-and-rigor angle is real — but the eval and the PVS1 cap
need to be addressed or the most knowledgeable interviewer will catch them in five minutes (and
that's the exact audience we're targeting).

---

## 2. What is genuinely done well (keep, lean into)

- **Deterministic, LLM-free classification core.** `acmg/rules.py` reads like the 2015 paper; the
  LLM only polishes prose and *cannot* change a verdict. This is the right architecture and a real
  differentiator from "wrap GPT and pray" demos.
- **"No claim without a source" as a type invariant.** The `ACMGCriterion` validator that refuses
  `met=True` without evidence is elegant and demonstrably enforced by a test. Strong signal.
- **Provider seam done properly.** `EvidenceProvider` as a `Protocol`, injected into the graph, is
  why the eval can run offline and deterministically. Textbook dependency inversion.
- **Graceful degradation everywhere.** `get_llm_client()` never raises; the demo runs with zero
  keys. This is the difference between "works on my machine" and "works in a reviewer's hands."
- **Action-band conflict gating.** The §4.1 fix (don't block on P-vs-LP) shows real clinical
  judgment, not just coding. Keep telling that story.
- **MCP server exists at all.** "Produce a tool, don't just consume APIs" is a rare, current skill.

---

## 3. Critical weaknesses (ranked) — the honest part

### 3.1 The ErrorCatch metric is largely circular  ⚠️ **biggest issue**

**What's happening.** Each injected-error case carries inline evidence; `expected_truth` was chosen
to be what the deterministic engine produces from *that same evidence*; and in all 8 cases the
`proposed_classification` sits in a **different clinical action band** than `expected_truth`. So
"catch" reduces to: *does the cross-band disagreement detector fire when two calls are in different
bands?* — which is true essentially by construction.

**Concrete proof.** Walk the 8 injected cases: every one is cross-band (VUS↔Pathogenic,
LikelyBenign↔Pathogenic, Pathogenic↔Benign, LP↔LB, …). The only way to *miss* would be a within-band
pair, and the set contains none. So 8/8 is not evidence the engine is *accurate* — it's evidence the
plumbing connects.

**Why it matters.** The README leads with "8/8 caught, 0% false positives" as if it measured
classification accuracy against truth. It doesn't. It measures self-consistency of the disagreement
detector. A variant scientist will see this immediately.

**Worse, the "ground truth" is engine-truth, not clinical-truth.** Example: case
`undercall-null-tp53-01` is a nonsense variant in TP53, absent from gnomAD, damaging in-silico, and
ClinVar-Pathogenic — clinically that's **Pathogenic**. But `expected_truth` is set to **"Likely
pathogenic"** to match the engine's PVS1-capped output (§3.2). The test set was bent to fit the
engine.

**The fix (this is the high-value work):**
1. **Get an independent gold standard.** Use **expert-panel (3-star/ClinGen VCEP) ClinVar
   classifications** as truth, on a *held-out* set the rules were not tuned on. Report **concordance**
   (how often the engine's independent call matches expert truth) as a *separate* number from the
   second-reviewer flagging behaviour.
2. **Decouple the two questions** the project conflates:
   - *Accuracy:* does the engine reproduce expert ACMG calls? (concordance %, confusion matrix)
   - *Reviewer utility:* given a (possibly wrong) proposed call, does it flag the right ones without
     crying wolf? (catch / FP — but now on cases where truth is independent of the engine).
3. **Add adversarial controls** where the proposed call is *correct* but the evidence is messy
   (conflicting submitters, borderline AF), to genuinely stress the false-positive rate.
4. **Report n and CIs.** 8 and 4 are too small to quote as percentages without a Wilson interval;
   say "8/8 (95% CI 67–100%)" or just stop quoting % until n is larger.

### 3.2 The engine systematically under-calls loss-of-function variants  ⚠️ **clinical-safety issue**

**What's happening.** `scorer.py` emits **PVS1 at `SUPPORTING` strength**, and `_counts()` then
files it in the **PP** bucket — i.e. a "null variant in a known LoF gene" is treated as a single
*supporting* point, identical to a weak in-silico hint.

**Consequence (provable from the rules):** a clean nonsense/frameshift in BRCA1 that is **absent from
gnomAD** fires PVS1(→PP) + PM2(→PP) = two supporting points → **VUS**. The headline demo only reaches
"Likely pathogenic" because the *fixture* sets `same_aa_change_pathogenic: true`, firing PS1
(Strong). Remove that fabricated flag and the flagship example collapses to VUS.

**Why it matters.** Under-calling a true pathogenic LoF is the most dangerous error class in clinical
genetics (missed actionable finding). A second-reviewer that down-weights every null variant would
*generate* the exact errors it's meant to catch.

**Also: dead code.** Because the scorer never emits `VERY_STRONG` (or a second `STRONG`), the
`pvs >= 1` and `ps >= 2` branches in `_is_pathogenic()`/`_is_likely_pathogenic()` **can never fire**.
The rules table looks complete but ~half of its pathogenic logic is unreachable in practice.

**The fix:**
1. Implement a real **PVS1 decision tree** (Abou Tayoun et al., 2018, ClinGen SVI): use VEP
   consequence + exon/NMD context to assign PVS1 at **Very Strong / Strong / Moderate / Supporting**
   rather than a blanket cap. This needs transcript/exon data → ties into the live VEP provider.
2. Until then, **at least allow PVS1 = Very Strong for unambiguous null classes** (stop-gain/
   frameshift/canonical ±1,2 splice) in curated LoF genes, with PM2 → Likely Pathogenic, which is the
   textbook result. Keep the conservative cap only for ambiguous consequences.
3. Add a rules test that asserts **PVS1(VeryStrong) + PM2(Supporting) = Likely Pathogenic** so the
   currently-dead branches are exercised.

### 3.3 Several "intelligent" signals are fabricated booleans in fixtures

PS1 (`same_aa_change_pathogenic`) and submitter-conflict (`review_status_conflicting`) are **hand-set
booleans** in the JSON, not derived from anything. In production these require real work: PS1 →
querying ClinVar for *other* variants at the same codon with a different nucleotide change and a
pathogenic assertion; conflict → parsing ClinVar's aggregate review-status field. **As shipped, the
fixtures encode the answer the engine then "discovers."** That's fine for a deterministic demo, but
the docs should not imply the engine *infers* these. Mark them clearly as provider-supplied facts,
and make implementing them real v1.1 acceptance criteria.

### 3.4 Provenance hash doesn't cover a conclusion-affecting input

`provenance_hash()` fingerprints (variant, evidence quotes/data, fired criteria, engine version) but
**excludes `retrieved_at`**, while the **staleness conflict** depends on `retrieved_at` (it's
`retrieved_at − source_last_updated`). So two runs months apart produce the **same hash** but
**different conflicts** (one stale, one not). The hash claims "same inputs ⇒ same output," but a
dossier *output* (the stale flag) can change without changing the hash. Either (a) freeze an
`as_of_date` into the request and hash it, or (b) include the staleness decision inputs in the hash.

### 3.5 The staleness signal measures the wrong thing

The blog framing is "ClinVar was updated *after* the curator made the call" (the reviewer's verdict
predates a reclassification). The implementation measures "record age vs **now**." An old-but-stable
benign variant settled in 2019 would be flagged "stale" though nothing ever changed → **noisy in
production**. Fix: compare `source_last_updated` against the **proposed call's date** (add
`proposed_at` to `ReviewRequest`), and/or use ClinVar's revision history to detect an *actual*
classification change, not mere age.

> Note: in the current eval, the two `stale_clinvar` cases are actually "caught" via the **cross-band
> disagreement**, not the staleness flag — so the marquee staleness feature isn't even what's earning
> the catch. It's closer to decorative right now.

---

## 4. Medium issues

- **`condition` and `proposed_by` are collected but never used.** BS1/PM2 are inherently
  disease-dependent, yet `condition` never reaches the scorer. Either use it (disease-aware
  thresholds) or drop it from the model to avoid implying capability that isn't there.
- **BS1 at a flat 1% is gene-agnostic.** "Higher than expected for the disorder" depends on
  prevalence/penetrance/heterogeneity. A constant will misfire (e.g. common recessive carrier
  alleles). At minimum document it as a crude proxy; ideally make it disease-parameterised.
- **`disagreement_score` (in the dossier) and the action-band gating tell slightly different
  stories.** A P-vs-LP pair yields `disagreement_score = 0.25` (non-zero) but "no blocking conflict."
  Fine, but the README should reconcile the two so they don't look contradictory.
- **The MCP server returns fixture-only data.** `get_evidence` uses the default fixture provider, so
  any variant outside the 3 demo cases returns `[]`. An external agent would think the tool is broken
  or that the variant has no evidence. Gate it behind the live provider or label it "demo data."
- **`normalise_variant` is idiosyncratic and untested for edge cases.** It left-trims only when *both*
  alleles have length > 1, does no right-trim, and can't left-align without a reference genome. It's
  honest-minimal, but there's no test asserting its behaviour, so a future change could silently break
  the provenance key.

---

## 5. Minor / hygiene

- **`make app` is broken** — the Makefile target and `app` extra reference `app/streamlit_app.py`,
  which doesn't exist. Either build the Streamlit app or remove the target/extra. A broken make target
  in a "complete repo" undercuts the whole pitch.
- **No CI.** `make check` exists but nothing runs it automatically. A local pre-commit hook (or a
  GitHub Action later) would prevent regressions and is itself a hireability signal.
- **No test exercises the cloud LLM clients** (all paths fall back to template). Acceptable, but a
  mocked test of `get_llm_client()` provider selection + fallback would be cheap insurance.
- **`ref/alt` regex `^[ACGT]+$`** rejects `N`, `*`, and symbolic alleles; a real VCF line will raise a
  validation error and crash the CLI. Fine for scope, but catch it with a friendly message.
- **`datetime`/staleness assumes `retrieved_at` is timezone-aware vs a naive `date`** — works now, but
  one timezone refactor away from an off-by-one. Add a test.

---

## 6. What to REMOVE (or stop advertising)

Cutting these *increases* credibility — "complete and honest" beats "broad and partly hollow":

1. **The empty `LiveEvidenceProvider` stubs** (`_gnomad/_clinvar/_vep` return `[]`). Either implement
   one real provider or move this to a clearly-labeled `// TODO v1.1` branch. Empty methods that look
   like features read as padding.
2. **`make app` + the `app`/Streamlit extra** until the app actually exists.
3. **The breadth of 5 LLM providers** *as a headline*. It's cheap to keep in code, but don't sell
   "Anthropic/OpenAI/Gemini/Ollama/Mistral/Qwen" as a feature for a summary-only function — a sharp
   reviewer reads it as résumé-keyword stuffing. Keep Ollama + one cloud + template; mention the rest
   as "pluggable."
4. **Unused `proposed_by`/`condition`** unless wired in.
5. **The dead very-strong/strong combining branches** — or, better, *make them reachable* (§3.2) so
   the rules table isn't decorative.

---

## 7. What to ADD (prioritized)

### P0 — fixes that defend the headline (do before showing anyone genomics-literate)
- [ ] **Independent concordance eval** vs expert-panel ClinVar (held-out), reported separately from
      catch/FP. This converts §3.1 from a liability into a strength.
- [ ] **Real PVS1 strength assignment** (or at least Very-Strong for unambiguous nulls) so the engine
      stops under-calling LoF; add the `PVS1+PM2 = LP` test (§3.2).
- [ ] **Rewrite the README metric section** to say exactly what ErrorCatch proves and what it doesn't,
      with n and a confidence interval. Replace "100%" framing with the honest version.
- [ ] **Fix `make app`** (build a minimal Streamlit page or remove the target).

### P1 — make it real, not fixtured
- [ ] **One real evidence provider**: gnomAD GraphQL *or* ClinVar E-utilities *or* Ensembl VEP REST,
      behind the existing seam. Even one real source changes the story from "demo" to "tool."
- [ ] **Date-aware staleness** (`proposed_at` on the request; compare to record revision) (§3.5).
- [ ] **Provenance covers staleness inputs** / freeze an `as_of_date` (§3.4).
- [ ] **Disease-aware BS1/PM2** using `condition` (§4).
- [ ] **Tests for `conflicts.py` and `normalise.py`** edge cases + a golden-dossier snapshot test.

### P2 — depth & polish
- [ ] Real **PS1** (same-codon ClinVar query) and **submitter-conflict parsing** from live data (§3.3).
- [ ] **Calibration / "insufficient evidence" state** instead of defaulting thin evidence toward VUS
      silently.
- [ ] **Local pre-commit** running `make check`; later a CI workflow.
- [ ] **Expand ErrorCatch** to a stratified set drawn from real ClinVar conflicts; publish the
      construction script so the metric is auditable.
- [ ] Somatic (AMP/ASCO/CAP) and an NLI faithfulness critic — the existing v2 items, now genuinely
      v2.

---

## 8. How to talk about this in an interview (turn weakness into signal)

Don't hide §3.1 and §3.2 — **lead with them**. The sentence that lands:

> *"The first version's eval was honestly near-circular — I'd authored the ground truth to match my
> own engine, and I'd capped PVS1 so conservatively that it under-called true nulls. I caught both
> when the false-positive rate and the TP53 case didn't smell right. v1.1 splits accuracy
> (concordance vs expert-panel ClinVar) from reviewer-utility (catch/FP on independent truth), and
> implements the real PVS1 decision tree."*

That paragraph demonstrates exactly the judgment the role wants: you can build it, *and* you can find
the flaw in your own work and prioritise the fix. That's rarer than a clean demo.

---

## 9. Prioritized action checklist (copy-paste)

```text
P0  [ ] Concordance eval vs expert-panel ClinVar (held-out); report separately from catch/FP
P0  [ ] Real PVS1 strength (≥Very Strong for unambiguous nulls); add PVS1+PM2=LP test
P0  [ ] README: restate ErrorCatch honestly (what it proves / n / CI)
P0  [ ] Fix or remove `make app`
P1  [ ] One real evidence provider (gnomAD or ClinVar or VEP)
P1  [ ] Date-aware staleness (`proposed_at`) + provenance covers staleness inputs
P1  [ ] Disease-aware BS1/PM2 via `condition`
P1  [ ] Tests for conflicts.py + normalise.py + golden dossier snapshot
P2  [ ] Real PS1 + submitter-conflict from live data
P2  [ ] Remove empty Live stubs / trim advertised LLM breadth
P2  [ ] Local pre-commit running `make check`
P2  [ ] Expand ErrorCatch to stratified real-ClinVar set + publish builder script
```

---

## 10. Bottom line

- **Is it good?** As software and as a *narrative vehicle*, yes — clearly above the median portfolio.
- **Is it finished?** As a *demo*, yes. As a *credible clinical-genomics claim*, not yet — the eval
  and the PVS1 cap are the two things between "nice repo" and "this person actually gets variant
  interpretation."
- **What's the single highest-leverage next move?** Replace the circular metric with a real
  **concordance-vs-expert-panel** number on held-out ClinVar, and fix PVS1. Do those two and the
  project goes from *B+ portfolio piece* to *A− "hire this person for the variant-AI team."*

*The most valuable property of this repo is the same one it tries to give its users: it tells you,
specifically and with receipts, where to look before you trust it.*
