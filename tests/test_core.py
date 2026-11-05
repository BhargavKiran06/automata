"""Run from the project root:  python -m pytest tests -q   (pip install pytest)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from automata import DFA, NFA
from generator import PRESETS, generate_examples, reference
from learning import edsm, lstar, rpni


def test_dfa_simulation_and_minimization():
    ref = reference("ends_with_01")
    assert ref.accepts("1101") and not ref.accepts("0110") and not ref.accepts("")
    assert len(ref.minimized().states) == 3


def test_minimization_preserves_language():
    for key in PRESETS:
        ref = reference(key)
        assert ref.minimized().equivalent(ref)


def test_equivalence_finds_shortest_counterexample():
    a, b = reference("even_zeros"), reference("ends_with_01")
    ce = a.counterexample(b)
    assert ce is not None and a.accepts(ce) != b.accepts(ce)


def test_nfa_subset_construction():
    nfa = PRESETS["third_from_end"]["nfa"]()
    dfa, _ = nfa.to_dfa()
    for s in ["", "1", "100", "0110", "111", "000", "10101"]:
        assert nfa.accepts(s) == dfa.accepts(s)
    assert len(dfa.minimized().states) == 8


def test_rpni_is_consistent_with_training_data():
    for key, p in PRESETS.items():
        ref = reference(key)
        ex = generate_examples(ref, 80, 8, seed=5)
        dfa, _ = rpni(ex, p["alphabet"])
        assert all(dfa.accepts(s) == lab for s, lab in ex)


def test_rpni_recovers_simple_languages():
    for key in ["ends_with_01", "even_zeros", "contains_101", "div_by_3", "no_11"]:
        ref = reference(key)
        dfa, _ = rpni(generate_examples(ref, 150, 8, seed=2), PRESETS[key]["alphabet"])
        assert dfa.equivalent(ref), key


def test_lstar_learns_exactly():
    for key, p in PRESETS.items():
        ref = reference(key)
        dfa, stats = lstar(p["alphabet"], ref)
        assert dfa.equivalent(ref), key


def test_noise_inflates_state_count():
    ref = reference("div_by_3")
    clean, _ = rpni(generate_examples(ref, 100, 8, noise=0.0, seed=1), ["0", "1"])
    noisy, _ = rpni(generate_examples(ref, 100, 8, noise=0.2, seed=1), ["0", "1"])
    assert len(noisy.minimized().states) > len(clean.minimized().states)


def test_strict_edsm_fits_training_data():
    for key in ["ends_with_01", "even_zeros", "contains_101", "div_by_3", "no_11"]:
        ref = reference(key)
        ex = generate_examples(ref, 80, 8, seed=7)
        dfa, _ = edsm(ex, PRESETS[key]["alphabet"], noise=0.0)
        assert all(dfa.accepts(s) == lab for s, lab in ex), key


def test_tolerant_edsm_survives_label_noise():
    ref = reference("div_by_3")
    exact = 0
    for seed in range(5):
        ex = generate_examples(ref, 300, 10, noise=0.1, seed=seed)
        dfa, _ = edsm(ex, ["0", "1"], noise=0.1)
        exact += dfa.equivalent(ref)
    assert exact >= 4
    # strict RPNI on the same data needs far more states
    ex = generate_examples(ref, 300, 10, noise=0.1, seed=0)
    assert len(rpni(ex, ["0", "1"])[0].minimized().states) > 10