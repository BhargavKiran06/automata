"""Automata inference.

* RPNI  - passive learning from labeled examples (state merging on a prefix
          tree acceptor, red-blue framework).
* L*    - Angluin's active learner: asks membership queries and equivalence
          queries to a "teacher".
"""
from __future__ import annotations

from collections import Counter
from typing import Callable, Dict, List, Optional, Tuple

from automata import DFA

Sample = Tuple[str, bool]


def clean_samples(samples: List[Sample]) -> Tuple[List[Sample], int]:
    """Resolve duplicate strings with conflicting labels by majority vote
    (ties are dropped). Returns (clean list, number of conflicts found)."""
    votes: Dict[str, Counter] = {}
    for s, lab in samples:
        votes.setdefault(s, Counter())[lab] += 1
    out, conflicts = [], 0
    for s, c in votes.items():
        if len(c) > 1:
            conflicts += 1
            if c[True] == c[False]:
                continue
        out.append((s, c[True] > c[False]))
    return out, conflicts


# --------------------------------------------------------------------- RPNI
def build_pta(samples: List[Sample], alphabet: List[str]):
    """Prefix tree acceptor. State ids follow length-lexicographic order of
    the prefixes, which RPNI needs for its canonical merge order."""
    order = {a: i for i, a in enumerate(alphabet)}
    prefixes = {""}
    for s, _ in samples:
        for i in range(1, len(s) + 1):
            prefixes.add(s[:i])
    ordered = sorted(prefixes, key=lambda p: (len(p), [order[c] for c in p]))
    ident = {p: i for i, p in enumerate(ordered)}
    trans: Dict[Tuple[int, str], int] = {}
    for p in ordered:
        if p:
            trans[(ident[p[:-1]], p[-1])] = ident[p]
    label: Dict[int, Optional[bool]] = {i: None for i in range(len(ordered))}
    for s, lab in samples:
        label[ident[s]] = lab
    return trans, label


def rpni(samples: List[Sample], alphabet: List[str]) -> Tuple[DFA, dict]:
    samples, conflicts = clean_samples(samples)
    trans, label = build_pta(samples, alphabet)
    pta_states = len(label)
    red: List[int] = [0]
    merges = 0

    def blue_states() -> Dict[int, Tuple[int, str]]:
        rs = set(red)
        out: Dict[int, Tuple[int, str]] = {}
        for r in red:
            for a in alphabet:
                t = trans.get((r, a))
                if t is not None and t not in rs:
                    out[t] = (r, a)
        return out

    def try_merge(r: int, q: int, parent: Tuple[int, str]) -> bool:
        log: List[tuple] = []

        def set_t(k, v):
            log.append(("t", k, trans.get(k)))
            trans[k] = v

        def set_l(k, v):
            log.append(("l", k, label[k]))
            label[k] = v

        def undo():
            for kind, k, old in reversed(log):
                if kind == "t":
                    if old is None:
                        del trans[k]
                    else:
                        trans[k] = old
                else:
                    label[k] = old

        set_t(parent, r)
        stack = [(r, q)]
        while stack:
            x, y = stack.pop()
            if x == y:
                continue
            lx, ly = label[x], label[y]
            if lx is not None and ly is not None and lx != ly:
                undo()
                return False
            if lx is None and ly is not None:
                set_l(x, ly)
            for a in alphabet:
                ty = trans.get((y, a))
                if ty is None:
                    continue
                tx = trans.get((x, a))
                if tx is None:
                    set_t((x, a), ty)
                else:
                    stack.append((tx, ty))
        return True

    while True:
        blues = blue_states()
        if not blues:
            break
        q = min(blues)
        done = False
        for r in sorted(red):
            if try_merge(r, q, blues[q]):
                merges += 1
                done = True
                break
        if not done:
            red.append(q)

    # collect reachable part, unlabeled states count as reject
    seen, stack = {0}, [0]
    while stack:
        u = stack.pop()
        for a in alphabet:
            v = trans.get((u, a))
            if v is not None and v not in seen:
                seen.add(v)
                stack.append(v)
    ids = {s: i for i, s in enumerate(sorted(seen))}
    delta = {(ids[s], a): ids[t] for (s, a), t in trans.items() if s in seen and t in seen}
    acc = {ids[s] for s in seen if label[s] is True}
    dfa = DFA(alphabet, ids.values(), ids[0], acc, delta)
    info = {"pta_states": pta_states, "merges": merges, "conflicts_resolved": conflicts,
            "training_size": len(samples)}
    return dfa, info


# ----------------------------------------------------------------------- L*
def lstar(alphabet: List[str], teacher: DFA, max_rounds: int = 200) -> Tuple[DFA, dict]:
    """Angluin's L*. The teacher answers membership queries exactly and
    equivalence queries with the shortest counterexample."""
    cache: Dict[str, bool] = {}
    stats = {"membership_queries": 0, "equivalence_queries": 0}

    def mq(s: str) -> bool:
        if s not in cache:
            stats["membership_queries"] += 1
            cache[s] = teacher.accepts(s)
        return cache[s]

    S: List[str] = [""]
    E: List[str] = [""]

    def row(s: str) -> Tuple[bool, ...]:
        return tuple(mq(s + e) for e in E)

    hyp: Optional[DFA] = None
    for _ in range(max_rounds):
        # make the table closed and consistent
        while True:
            changed = False
            srows = {row(s) for s in S}
            for s in list(S):
                for a in alphabet:
                    if row(s + a) not in srows:
                        S.append(s + a)
                        changed = True
                        break
                if changed:
                    break
            if changed:
                continue
            by_row: Dict[tuple, List[str]] = {}
            for s in S:
                by_row.setdefault(row(s), []).append(s)
            for group in by_row.values():
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        for a in alphabet:
                            if row(group[i] + a) != row(group[j] + a):
                                ra, rb = row(group[i] + a), row(group[j] + a)
                                col = next(k for k in range(len(E)) if ra[k] != rb[k])
                                E.append(a + E[col])
                                changed = True
                                break
                        if changed:
                            break
                    if changed:
                        break
                if changed:
                    break
            if not changed:
                break

        reps: Dict[tuple, int] = {}
        rep_str: List[str] = []
        for s in S:
            r = row(s)
            if r not in reps:
                reps[r] = len(reps)
                rep_str.append(s)
        delta = {(reps[row(s)], a): reps[row(s + a)] for s in rep_str for a in alphabet}
        acc = {i for r, i in reps.items() if r[0]}
        hyp = DFA(alphabet, range(len(reps)), reps[row("")], acc, delta)

        stats["equivalence_queries"] += 1
        ce = hyp.counterexample(teacher)
        if ce is None:
            break
        for i in range(1, len(ce) + 1):
            if ce[:i] not in S:
                S.append(ce[:i])
    stats["rounds"] = stats["equivalence_queries"]
    assert hyp is not None
    return hyp, stats
