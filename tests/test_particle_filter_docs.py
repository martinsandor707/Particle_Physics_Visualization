"""The particle filter's prose follows the code (review S4-S8, U7)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
CONTENT = ROOT / "calosrv/static/js/methodology/content"
STATS = (CONTENT / "s2_4_statistics.js").read_text()
RESULTS = (CONTENT / "s3_results.js").read_text()


def test_counter_is_carried_and_seed_fixed():
    assert "restarts at 0 only on" in README
    assert "restarts at 0\n  whenever the pool can change" not in README
    assert "returns to zero only on an experiment switch" in STATS
    assert "to begin with" not in STATS and "to begin with, one draw" not in RESULTS


def test_theta_bounds_in_degrees_and_radians_and_equation_is_zero_based():
    assert "0.175–0.262 rad" in README and "0.175–0.262 rad" in STATS
    assert "print degrees and radians together" not in STATS
    assert r"\mathrm{draw} \bmod N" in STATS and "(\\mathrm{draw} \\bmod N) + 1" not in STATS


def test_tilted_mean_is_the_pools():
    assert "more hits than the selection's mean" not in README
    assert README.count("the pool's (the candidates') mean") == 2


def test_unplaceable_events_are_not_called_reachable_by_number():
    assert "stay reachable by number" not in RESULTS
    assert "chooses shower B" in RESULTS and "choose shower B" in " ".join(README.split())


def test_overclaims_are_qualified():
    assert "With a particle bound set" in README
    assert "selection-scope and cloud drawers" in README
    assert "With a particle bound set and the pool empty" in RESULTS
