"""Tests for the non-regular languages and the length curve. Run from the project root:
   python -m pytest tests -q
"""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi import HTTPException

from generator import (dfa_length_sample, generate_examples, length_test, reference,
                       shortest_disagreement)
from learning import rpni
from main import LearnReq, LengthReq, learn, length_curve


# ---- should PASS ---------------------------------------------------------
def test_anbn_membership():
    a = reference("anbn")
    assert a.accepts("") and a.accepts("ab") and a.accepts("aaabbb")
    assert not a.accepts("aab") and not a.accepts("abab") and not a.accepts("ba")


def test_anbn_training_data_contains_every_member():
    ex = generate_examples(reference("anbn"), 40, 8, seed=1)
    assert {s for s, lab in ex if lab} == {"", "ab", "aabb", "aaabbb", "aaaabbbb"}
    assert all(reference("anbn").accepts(s) == lab for s, lab in ex)     # labels match the oracle
    assert len({s for s, _ in ex}) == len(ex)                            # no duplicates


def test_no_dfa_matches_anbn():
    # pumping lemma in action: whatever RPNI learns, it disagrees with a^n b^n somewhere
    ex = generate_examples(reference("anbn"), 60, 10, seed=3)
    dfa, _ = rpni(ex, ["a", "b"])
    assert shortest_disagreement(dfa, reference("anbn"), max_len=16) is not None


def test_dfa_length_sample_has_exact_length_and_label():
    ref = reference("div_by_3")
    rng = random.Random(0)
    for s in dfa_length_sample(ref, 12, True, 10, rng):
        assert len(s) == 12 and ref.accepts(s)
    for s in dfa_length_sample(ref, 12, False, 10, rng):
        assert len(s) == 12 and not ref.accepts(s)


def test_length_curve_regular_language_generalizes_to_every_length():
    out = length_curve(LengthReq(language="div_by_3", n=60, max_len=8))
    for p in out["points"]:
        if p["recall"] is not None:
            assert p["recall"] == 1.0
        if p["specificity"] is not None:
            assert p["specificity"] == 1.0


def test_length_curve_anbn_breaks_beyond_training_length():
    out = length_curve(LengthReq(language="anbn", n=40, max_len=8))
    beyond = [p["recall"] for p in out["points"] if p["beyond_training"] and p["recall"] is not None]
    assert beyond and min(beyond) < 1.0


# ---- should FAIL (and fail cleanly) -----------------------------------------
def test_lstar_rejects_a_non_regular_reference():
    with pytest.raises(HTTPException) as err:
        learn(LearnReq(alphabet=["a", "b"], examples=[], algorithm="lstar", reference="anbn"))
    assert err.value.status_code == 400 and "regular" in err.value.detail


def test_length_curve_rejects_unknown_language_and_lstar():
    with pytest.raises(HTTPException) as err:
        length_curve(LengthReq(language="nope"))
    assert err.value.status_code == 404
    with pytest.raises(HTTPException) as err:
        length_curve(LengthReq(language="anbn", algorithm="lstar"))
    assert err.value.status_code == 400