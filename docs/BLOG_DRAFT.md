# Reviewer2 — working-backwards brief

> **Write the announcement before the code.** This file is the spec. If a feature
> doesn't help make the headline below *true and defensible*, it is cut from v1.

---

## The LinkedIn / blog headline (the thing this repo must earn)

> **"I built a second-reviewer AI for ACMG variant classification — here's a
> reclassified ClinVar call it caught that a static pipeline missed."**

Opening paragraph (draft):

> Clinical genetics labs already run a *second reviewer* on variant calls — it's
> required by CAP/CLIA. But that reviewer is a busy human, and the evidence under
> a variant changes constantly: ClinVar submitters disagree, "pathogenic" calls
> get downgraded, VUS get reclassified months before anyone re-pulls them.
> Reviewer2 is an evidence-grounded agent that independently re-derives the ACMG/AMP
> classification for a germline variant, shows the exact source sentence behind every
> criterion it fires, and flags where the proposed call disagrees with current
> evidence. It does **not** replace the human reviewer — it makes the human faster and
> harder to fool. And unlike every happy-path genomics demo on GitHub, it ships with
> **ErrorCatch**: a harness that injects known classification errors and reports the
> catch rate *and the false-positive rate*, honestly.

---

## Who this is for
- **Primary (hiring):** clinical-genomics / oncology comp-bio teams (Illumina, Genentech,
  10x, Dana-Farber, Lilly) who need people fluent in **both** ACMG variant interpretation
  **and** production agentic AI.
- **Secondary (users):** variant scientists who want a fast, auditable second opinion.

## What it is
A deterministic, rule-based ACMG/AMP criteria engine wrapped in a 4-node LangGraph
agent, with transparent evidence grounding (every criterion links to a source quote),
a standalone gnomAD/ClinVar **MCP server**, and an honest **ErrorCatch** evaluation.

## What it is NOT (v1 boundaries — deliberately cut)
- ❌ Not somatic (AMP/ASCO/CAP tiering) — **germline ACMG only**. (v2)
- ❌ Not an NLI faithfulness model — **transparent source-quote grounding** instead. (v2)
- ❌ Not RAG-over-PubMed — structured evidence from ClinVar/gnomAD/VEP only. (v1.1)
- ❌ Not autonomous — **human-in-the-loop**; emits a dossier, a human signs off.
- ❌ Not a ClinVar replacement — it *audits against* ClinVar.

## The honest metric (no hand-waving)
The README reports, computed by `make eval`:
- catch rate = caught / total injected errors, broken down **by ACMG criterion type**,
- **false-positive rate** = correct calls wrongly flagged, on a held set of correct calls,
- exact test-set construction, so an interviewer can interrogate it.

## The real failure story (FILL THIS IN — your unfair advantage)
> _One real (anonymised, non-confidential) reclassification or VUS-staleness situation
> you have personally seen in 10+ years of clinical genomics. One specific sentence.
> This beats every published statistic._
>
> e.g. *"I have seen a variant that was reclassified in ClinVar months before our
> reporting pipeline reflected it; a staleness check like this would have surfaced it."*

## Definition of done for v1.0
1. `make demo` runs offline, no keys, classifies the fixture variants, prints dossiers.
2. `make eval` prints an honest ErrorCatch table (catch rate + FP rate).
3. `gnomad-clinvar-mcp` server starts and answers a tool call.
4. README has: 30-sec GIF, headline metric, architecture diagram, skills table,
   "why this matters", and the real failure story above.
