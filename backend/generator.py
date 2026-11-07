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


# ----------------------------------------------------------------------------
# Non-regular languages. No DFA can recognise these exactly, so they are given
# as a membership test ("oracle") plus helpers that build hard test strings.
# ----------------------------------------------------------------------------
class NonRegular:
    regular = False
    alphabet: List[str] = ["a", "b"]

    def accepts(self, s: str) -> bool:
        raise NotImplementedError

    def sample_positive(self, rng: random.Random, max_len: int) -> str:
        raise NotImplementedError

    def mutate(self, s: str, rng: random.Random) -> str:
        """A near miss: flip, delete or insert one symbol."""
        if not s:
            return rng.choice(self.alphabet)
        i = rng.randrange(len(s))
        kind = rng.random()
        if kind < 0.5:
            other = [c for c in self.alphabet if c != s[i]]
            return s[:i] + rng.choice(other) + s[i + 1:]
        if kind < 0.75:
            return s[:i] + s[i + 1:]
        return s[:i] + rng.choice(self.alphabet) + s[i:]

    def length_test(self, ell: int, rng: random.Random, k: int) -> Tuple[List[str], List[str]]:
        raise NotImplementedError

    def _split(self, strings, k):
        pos = sorted({s for s in strings if self.accepts(s)})
        neg = sorted({s for s in strings if not self.accepts(s)})
        rng = random.Random(len(strings))
        rng.shuffle(pos)
        rng.shuffle(neg)
        return pos[: max(1, k // 2)], neg[:k]


class AnBn(NonRegular):
    """a^n b^n : n a's followed by exactly n b's."""
    def accepts(self, s: str) -> bool:
        if len(s) % 2:
            return False
        h = len(s) // 2
        return s == "a" * h + "b" * h

    def sample_positive(self, rng, max_len):
        h = rng.randint(0, max_len // 2)
        return "a" * h + "b" * h

    def length_test(self, ell, rng, k):
        member = "a" * (ell // 2) + "b" * (ell // 2) if ell % 2 == 0 else None
        pool = ["a" * i + "b" * (ell - i) for i in range(ell + 1)]       # same shape, wrong counts
        if member is not None:
            pool.append(member)
            for _ in range(ell):
                pool.append(self.mutate(member, rng)[:ell].ljust(ell, "b"))
        for _ in range(ell):
            pool.append("".join(rng.choice("ab") for _ in range(ell)))
        return self._split([s for s in pool if len(s) == ell], k)


class EqualAB(NonRegular):
    """Strings with the same number of a's and b's (any order)."""
    def accepts(self, s: str) -> bool:
        return s.count("a") == s.count("b")

    def sample_positive(self, rng, max_len):
        h = rng.randint(0, max_len // 2)
        chars = list("a" * h + "b" * h)
        rng.shuffle(chars)
        return "".join(chars)

    def length_test(self, ell, rng, k):
        pool = []
        if ell % 2 == 0:
            for _ in range(4 * k):
                chars = list("a" * (ell // 2) + "b" * (ell // 2))
                rng.shuffle(chars)
                m = "".join(chars)
                pool.append(m)
                if m:
                    i = rng.randrange(ell)
                    pool.append(m[:i] + ("b" if m[i] == "a" else "a") + m[i + 1:])
        for _ in range(2 * k):
            pool.append("".join(rng.choice("ab") for _ in range(ell)))
        return self._split(pool, k)


def dfa_length_sample(d: DFA, ell: int, want_accept: bool, k: int, rng: random.Random) -> List[str]:
    """Up to k distinct strings of exactly length ell, drawn uniformly from the
    strings the DFA accepts (or rejects). Dynamic programming over lengths."""
    d = d.completed()
    good = (lambda s: s in d.accepting) if want_accept else (lambda s: s not in d.accepting)
    ways = [{s: 1 if good(s) else 0 for s in d.states}]
    for l in range(1, ell + 1):
        ways.append({s: sum(ways[l - 1][d.delta[(s, a)]] for a in d.alphabet) for s in d.states})
    if ways[ell][d.start] == 0:
        return []
    out = set()
    for _ in range(k * 12):
        if len(out) >= k:
            break
        s, word = d.start, []
        for l in range(ell, 0, -1):
            opts = [(a, ways[l - 1][d.delta[(s, a)]]) for a in d.alphabet]
            r = rng.randrange(sum(w for _, w in opts))
            for a, w in opts:
                if r < w:
                    break
                r -= w
            word.append(a)
            s = d.delta[(s, a)]
        out.add("".join(word))
    return sorted(out)


def length_test(ref, ell: int, rng: random.Random, k: int) -> Tuple[List[str], List[str]]:
    """(members, non-members) of length ell for any reference language."""
    if hasattr(ref, "length_test"):
        return ref.length_test(ell, rng, k)
    return (dfa_length_sample(ref, ell, True, max(1, k // 2), rng),
            dfa_length_sample(ref, ell, False, k, rng))


def shortest_disagreement(dfa: DFA, ref, max_len: int = 16) -> Optional[str]:
    """Shortest string on which a DFA and an oracle disagree (brute force)."""
    for L in range(max_len + 1):
        for t in product(ref.alphabet, repeat=L):
            s = "".join(t)
            if dfa.accepts(s) != ref.accepts(s):
                return s
    return None


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
    "anbn": {"title": "aⁿbⁿ (not regular)", "alphabet": ["a", "b"], "build": lambda: AnBn(),
             "desc": "n a's then n b's. Not regular: no DFA can match it, so every learner must fail somewhere."},
    "equal_ab": {"title": "Equal a's and b's (not regular)", "alphabet": ["a", "b"], "build": lambda: EqualAB(),
                 "desc": "Same number of a and b in any order. Not regular: counting needs unbounded memory."},
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
    if not getattr(ref, "regular", True):
        return _generate_oracle(ref, n, max_len, noise, seed, exclude)
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


def _generate_oracle(ref, n, max_len, noise, seed, exclude):
    """Training data for a non-regular language: every member we can find (up to
    half the sample), then near misses of members plus random strings."""
    rng = random.Random(seed)
    exclude = exclude or set()
    seen, pos, neg = set(), [], []
    tries = 0
    while len(pos) < n // 2 and tries < 40 * n + 400:
        tries += 1
        s = ref.sample_positive(rng, max_len)
        if s in seen or s in exclude or len(s) > max_len or not ref.accepts(s):
            continue
        seen.add(s)
        pos.append(s)
    tries = 0
    while len(neg) < n - len(pos) and tries < 60 * n + 800:
        tries += 1
        if pos and rng.random() < 0.6:
            s = ref.mutate(rng.choice(pos), rng)
        else:
            s = random_string(ref.alphabet, max_len, rng)
        if s in seen or s in exclude or len(s) > max_len or ref.accepts(s):
            continue
        seen.add(s)
        neg.append(s)
    data = [(s, True) for s in pos] + [(s, False) for s in neg]
    rng.shuffle(data)
    if noise > 0:
        for i in rng.sample(range(len(data)), min(round(noise * len(data)), len(data))):
            s, lab = data[i]
            data[i] = (s, not lab)
    return data


def test_set(ref, max_train_len: int, n: int = 1500, seed: int = 12345,
             exclude: Optional[set] = None) -> List[Tuple[str, bool, bool]]:
    """Held-out strings. Returns (string, label, is_longer_than_training)."""
    rng = random.Random(seed)
    exclude = exclude or set()
    if not getattr(ref, "regular", True):
        top = max_train_len * 2
        per = max(4, n // (top + 1))
        out = []
        for ell in range(top + 1):
            members, others = ref.length_test(ell, rng, per)
            for s in members + others:
                if s not in exclude:
                    out.append((s, ref.accepts(s), ell > max_train_len))
        return out
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