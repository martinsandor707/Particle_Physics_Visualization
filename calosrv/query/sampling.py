"""Choose between the exact projection table and its sampled companion.

The honest position on latency: a cold projection query over 22.5 million rows
cannot be answered in under 100 ms. The floor is decompressing and hashing a few
hundred megabytes, and no amount of DuckDB tuning moves it.

What *can* be delivered is a sub-100 ms interactive feel, by serving a 10%
Bernoulli sample while a slider is being dragged and swapping in the exact
result when it is released. Every aggregate the projection query computes is a
sum, and a Bernoulli sample is an unbiased estimator of a sum, so the preview is
a genuine statistical estimate rather than a crop of the data. Its relative
error on a cell holding ``k`` hits is about ``1 / sqrt(0.1 * k)``: a fraction of
a percent in the bright cells that carry the structure, and below the 8-bit
quantisation step everywhere else.

Every payload produced from the sample is marked ``exact: false`` so the
interface can say so rather than quietly showing an estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db.registry import ExperimentRecord

#: Below this row count the exact scan is already fast enough that sampling
#: would add inaccuracy for no perceptible gain.
SAMPLE_THRESHOLD_ROWS = 2_000_000


@dataclass(frozen=True)
class SamplingDecision:
    sampled: bool
    reason: str
    percent: float


def decide(
    record: ExperimentRecord,
    preview: bool,
    sample_percent: float,
) -> SamplingDecision:
    """Whether to serve this request from the sampled table."""
    if not preview:
        return SamplingDecision(False, "Exact scan requested.", 100.0)
    if not record.has_sample:
        return SamplingDecision(
            False, "No sampled companion table exists for this experiment.", 100.0
        )
    if record.n_hits < SAMPLE_THRESHOLD_ROWS:
        return SamplingDecision(
            False,
            f"Experiment holds {record.n_hits:,} rows, below the "
            f"{SAMPLE_THRESHOLD_ROWS:,}-row threshold where preview sampling "
            "becomes worthwhile.",
            100.0,
        )
    return SamplingDecision(
        True,
        f"Drag preview served from a {sample_percent:g}% unbiased sample; "
        "release the slider for the exact result.",
        sample_percent,
    )
