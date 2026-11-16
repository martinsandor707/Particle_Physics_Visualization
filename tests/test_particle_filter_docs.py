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


def test_the_pool_is_the_experiments_and_the_equation_says_so():
    """Martin, 2026-11-16: E1, E2 and D do not narrow the candidates, on either page."""
    assert r"e \in \mathcal E" in STATS and r"e \in \mathrm{Sel}" not in STATS
    assert r"\mathrm{Sel}" not in STATS
    assert "do not narrow the pool" in STATS and "2026-11-16" in STATS
    assert "basis=experiment" in STATS and "422" in STATS
    # The older rule survives only as the API's default, and no page uses it.
    assert "basis=selection" in STATS and "no page uses it" in STATS
    # The draw counter no longer crosses an E1/E2/D commit, and the first draw is draw 0.
    assert "carried across $E_1$, $E_2$, $D$ and particle commits" not in STATS
    assert "the Event viewer's first draw" in STATS and "draw 0 of the shuffle" in STATS
    # What the production counts say, with dataset and date (never a constant).
    assert "2026-11-16" in STATS and "57 of 20,325" in STATS


def test_the_results_audit_the_event_viewer():
    text = " ".join(RESULTS.split())
    # The count line's experiment wording, not the selection's.
    assert "of the 20,325 events of the experiment" in text
    assert "of the 20,268 selected by E₁, E₂ and D" not in text
    assert "no selected event with a defined separation" not in text
    assert "no event of the experiment with a defined separation holds a shower with" in text
    # The tab bar and the status chip say the mode by text, not colour alone.
    assert "Entire selection" in text and "Event viewer" in text and "text chip" in text
    # The isolation, the first draw, the parked event, the empty state.
    assert "Entire selection sends nothing to the event routes" in text
    assert "the viewer sends no projection" in text
    assert "draw 0 after an experiment switch" in text and "parks" in text
    assert "No event drawn: type an event number, or press Pick for me or Most tilted." in text
    assert "The first event could not be drawn" in text
    # Standalone gating, the aggregate's shut tab, the Models 3-D card's standing line.
    assert "The panels show the summed energy density" in text
    assert "The Event viewer is not available for this experiment" in text
    assert "Unavailable for this experiment" in text
    # Production counts carry their dataset and date.
    assert "2026-11-15" in text and "2026-11-16" in text and "hits_all_models" in text


def test_the_readme_documents_the_basis_and_the_subpage():
    # Strings the brief (section 12) keeps for ps-readme: the API parameter and the hash key.
    assert "basis" in README and "psub" in README
