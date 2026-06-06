"""Variant normalisation (graph node 1).

v1 does light, deterministic normalisation that needs no network:

* strip a leading 'chr' from the chromosome,
* upper-case ref/alt alleles,
* left-trim shared leading bases for simple indels (a minimal parsimony step).

Full HGVS<->VCF interconversion and VEP-based canonical-transcript resolution are a
v1.1 task (they need the Ensembl API). Keeping this deterministic means the demo and
eval are reproducible offline.
"""

from __future__ import annotations

from reviewer2.models import Variant


def normalise_variant(variant: Variant) -> Variant:
    chrom = variant.chrom
    if chrom.lower().startswith("chr"):
        chrom = chrom[3:]

    ref = variant.ref.upper()
    alt = variant.alt.upper()
    pos = variant.pos

    # Minimal left-trim of a shared leading base (e.g. ref=AG alt=A -> shift).
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref, alt = ref[1:], alt[1:]
        pos += 1

    return variant.model_copy(update={"chrom": chrom, "ref": ref, "alt": alt, "pos": pos})
