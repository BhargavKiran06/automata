"""Reference languages (as DFAs / an NFA) and the training-data generator."""
from __future__ import annotations

import random
from itertools import product
from typing import Dict, List, Optional, Tuple

from automata import DFA, NFA, from_functional

BIN = ["0", "1"]


def _ends_with_01() -> DFA:
    return from_functional(BIN, "", lambda s, a: (s + a)[-2:], lambda s: s == "01")


def _even_zeros() -> DFA:
    return from_functional(BIN, 0, lambda s, a: (s + (a == "0")) % 2, lambda s: s == 0)


def _contains_101() -> DFA:
    # KMP-style tracker: state = length of the longest matched prefix of "101"
    table = {0: {"0": 0, "1": 1}, 1: {"0": 2, "1": 1}, 2: {"0": 0, "1": 3}, 3: {"0": 3, "1": 3}}
    return from_functional(BIN, 0, lambda s, a: table[s][a], lambda s: s == 3)


def _div_by_3() -> DFA:
    return from_functional(BIN, 0, lambda s, a: (s * 2 + int(a)) % 3, lambda s: s == 0)


def _no_11() -> DFA:
    def step(st, a):
        if st == "dead":
            return "dead"
        if a == "1":
            return "dead" if st == "one" else "one"
        return "zero"
    return from_functional(BIN, "zero", step, lambda s: s != "dead")


def _starts_ends_same() -> DFA:
    ab = ["a", "b"]
    def step(st, a):
        if st == "init":
            return (a, True)           # (first symbol, last==first)
        first, _ = st
        return (first, a == first)
    return from_functional(ab, "init", step, lambda s: s != "init" and s[1])


def _abc_mod() -> DFA:
    """Over {a,b,c}: number of a's is even and number of b's is odd."""
    abc = ["a", "b", "c"]
    def step(st, x):
        ea, ob = st
        if x == "a":
            return ((ea + 1) % 2, ob)
        if x == "b":
            return (ea, (ob + 1) % 2)
        return st
    return from_functional(abc, (0, 0), step, lambda s: s == (0, 1))


def _third_from_end_nfa() -> NFA:
    # 4-state NFA for "the third symbol from the end is 1"
    delta = {(0, "0"): {0}, (0, "1"): {0, 1},
             (1, "0"): {2}, (1, "1"): {2},
             (2, "0"): {3}, (2, "1"): {3}}
    return NFA(BIN, range(4), 0, {3}, delta)


PRESETS: Dict[str, dict] = {
    "ends_with_01": {"title": "Ends with 01", "alphabet": BIN, "build": _ends_with_01,
                     "desc": "Binary strings whose last two symbols are 0 then 1."},
    "even_zeros": {"title": "Even number of 0s", "alphabet": BIN, "build": _even_zeros,
                   "desc": "Binary strings containing an even count of 0."},
    "contains_101": {"title": "Contains 101", "alphabet": BIN, "build": _contains_101,
                     "desc": "Binary strings with 101 as a substring."},
    "div_by_3": {"title": "Binary number divisible by 3", "alphabet": BIN, "build": _div_by_3,
                 "desc": "Read as a binary number, the value is a multiple of 3."},
    "no_11": {"title": "No two consecutive 1s", "alphabet": BIN, "build": _no_11,
              "desc": "Binary strings that never contain 11."},
    "third_from_end": {"title": "Third symbol from the end is 1 (NFA-friendly)", "alphabet": BIN,
                       "build": lambda: _third_from_end_nfa().to_dfa()[0], "nfa": _third_from_end_nfa,
                       "desc": "A 4-state NFA, but its smallest DFA needs 8 states."},
    "starts_ends_same": {"title": "Starts and ends with the same symbol", "alphabet": ["a", "b"],
                         "build": _starts_ends_same, "desc": "Non-empty strings over {a,b} with equal first and last symbol."},
    "abc_parity": {"title": "Even a's and odd b's", "alphabet": ["a", "b", "c"], "build": _abc_mod,
                   "desc": "Over {a,b,c}: even number of a, odd number of b, any number of c."},
}


def reference(name: str) -> DFA:
    return PRESETS[name]["build"]()


def random_string(alphabet: List[str], max_len: int, rng: random.Random) -> str:
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, max_len)))


def generate_examples(ref: DFA, n: int, max_len: int, balance: bool = True,
                      noise: float = 0.0, seed: Optional[int] = None,
                      exclude: Optional[set] = None) -> List[Tuple[str, bool]]:
    """n unique labeled strings, labels from the reference DFA. With `balance`
    we try for roughly equal positives and negatives. `noise` flips that
    fraction of labels afterwards."""
    rng = random.Random(seed)
    exclude = exclude or set()
    seen, pos, neg = set(), [], []
    target_pos = n // 2 if balance else n
    target_neg = n - n // 2 if balance else n
    attempts, max_attempts = 0, 60 * n + 2000
    cap = sum(len(ref.alphabet) ** k for k in range(max_len + 1))
    n = min(n, cap)
    while len(pos) + len(neg) < n and attempts < max_attempts:
        attempts += 1
        s = random_string(ref.alphabet, max_len, rng)
        if s in seen or s in exclude:
            continue
        lab = ref.accepts(s)
        if lab and len(pos) >= target_pos and balance and attempts < max_attempts // 2:
            continue
        if (not lab) and len(neg) >= target_neg and balance and attempts < max_attempts // 2:
            continue
        seen.add(s)
        (pos if lab else neg).append((s, lab))
    data = pos + neg
    rng.shuffle(data)
    data = data[:n]
    if noise > 0:
        k = round(noise * len(data))
        for i in rng.sample(range(len(data)), min(k, len(data))):
            s, lab = data[i]
            data[i] = (s, not lab)
    return data


def test_set(ref: DFA, max_train_len: int, n: int = 1500, seed: int = 12345,
             exclude: Optional[set] = None) -> List[Tuple[str, bool, bool]]:
    """Held-out strings. Returns (string, label, is_longer_than_training)."""
    rng = random.Random(seed)
    exclude = exclude or set()
    out, seen = [], set()
    top = max_train_len * 2
    tries = 0
    while len(out) < n and tries < n * 40:
        tries += 1
        s = random_string(ref.alphabet, top, rng)
        if s in seen or s in exclude:
            continue
        seen.add(s)
        out.append((s, ref.accepts(s), len(s) > max_train_len))
    return out
