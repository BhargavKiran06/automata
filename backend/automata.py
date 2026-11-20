"""Core automata classes: DFA, NFA, minimization, equivalence, subset construction.

States are plain integers. A DFA may be *partial* (missing transition = reject);
call `.completed()` to add an explicit sink state.
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Dict, Hashable, Iterable, List, Optional, Set, Tuple


class DFA:
    def __init__(self, alphabet: Iterable[str], states: Iterable[int], start: int,
                 accepting: Iterable[int], delta: Dict[Tuple[int, str], int]):
        self.alphabet: List[str] = list(alphabet)
        self.states: List[int] = sorted(set(states))
        self.start = start
        self.accepting: Set[int] = set(accepting)
        self.delta: Dict[Tuple[int, str], int] = dict(delta)

    # ------------------------------------------------------------ simulation
    def run(self, s: str) -> Tuple[bool, List[dict]]:
        """Run the DFA on s. Returns (accepted, steps). A missing transition
        sends the machine to an implicit dead state (to = None)."""
        cur: Optional[int] = self.start
        steps: List[dict] = []
        for ch in s:
            if cur is None:
                steps.append({"from": None, "sym": ch, "to": None})
                continue
            nxt = self.delta.get((cur, ch))
            steps.append({"from": cur, "sym": ch, "to": nxt})
            cur = nxt
        return (cur is not None and cur in self.accepting), steps

    def accepts(self, s: str) -> bool:
        cur: Optional[int] = self.start
        for ch in s:
            cur = self.delta.get((cur, ch))
            if cur is None:
                return False
        return cur in self.accepting

    # ------------------------------------------------------- transformations
    def reachable(self) -> "DFA":
        seen = {self.start}
        q = deque([self.start])
        while q:
            u = q.popleft()
            for a in self.alphabet:
                v = self.delta.get((u, a))
                if v is not None and v not in seen:
                    seen.add(v)
                    q.append(v)
        return DFA(self.alphabet, seen, self.start, self.accepting & seen,
                   {k: v for k, v in self.delta.items() if k[0] in seen})

    def completed(self) -> "DFA":
        """Total DFA: every missing transition goes to an explicit sink."""
        d = self.reachable()
        missing = any((s, a) not in d.delta for s in d.states for a in d.alphabet)
        if not missing:
            return d
        sink = max(d.states) + 1
        delta = dict(d.delta)
        for s in d.states + [sink]:
            for a in d.alphabet:
                delta.setdefault((s, a), sink)
        return DFA(d.alphabet, d.states + [sink], d.start, d.accepting, delta)

    def minimized(self) -> "DFA":
        """Moore partition refinement on the completed, reachable DFA.
        States are renumbered in BFS order from the start state."""
        d = self.completed()
        block = {s: (1 if s in d.accepting else 0) for s in d.states}
        while True:
            sig = {s: (block[s],) + tuple(block[d.delta[(s, a)]] for a in d.alphabet)
                   for s in d.states}
            ids: Dict[tuple, int] = {}
            new_block = {}
            for s in d.states:
                new_block[s] = ids.setdefault(sig[s], len(ids))
            if len(set(new_block.values())) == len(set(block.values())):
                block = new_block
                break
            block = new_block
        # renumber blocks in BFS order
        order: Dict[int, int] = {}
        q = deque([block[d.start]])
        order[block[d.start]] = 0
        rep = {}
        for s in d.states:
            rep.setdefault(block[s], s)
        delta: Dict[Tuple[int, str], int] = {}
        while q:
            b = q.popleft()
            for a in d.alphabet:
                nb = block[d.delta[(rep[b], a)]]
                if nb not in order:
                    order[nb] = len(order)
                    q.append(nb)
                delta[(order[b], a)] = order[nb]
        acc = {order[b] for b in order if rep[b] in d.accepting}
        return DFA(d.alphabet, range(len(order)), 0, acc, delta)

    def sink_states(self) -> Set[int]:
        """States from which no accepting state is reachable."""
        d = self.completed()
        rev: Dict[int, Set[int]] = {s: set() for s in d.states}
        for (s, _a), t in d.delta.items():
            rev[t].add(s)
        good = set(d.accepting)
        q = deque(good)
        while q:
            u = q.popleft()
            for p in rev[u]:
                if p not in good:
                    good.add(p)
                    q.append(p)
        return {s for s in d.states if s not in good}

    # ----------------------------------------------------------- equivalence
    def counterexample(self, other: "DFA") -> Optional[str]:
        """Shortest string on which the two DFAs disagree, or None if they
        recognise the same language (BFS over the product automaton)."""
        a, b = self.completed(), other.completed()
        alphabet = sorted(set(a.alphabet) | set(b.alphabet))
        # symbols missing from one automaton lead to reject in that automaton
        def step(d: DFA, s: Optional[int], ch: str) -> Optional[int]:
            return None if s is None else d.delta.get((s, ch))
        def acc(d: DFA, s: Optional[int]) -> bool:
            return s is not None and s in d.accepting
        start = (a.start, b.start)
        seen = {start: ""}
        q = deque([start])
        while q:
            u = q.popleft()
            if acc(a, u[0]) != acc(b, u[1]):
                return seen[u]
            for ch in alphabet:
                v = (step(a, u[0], ch), step(b, u[1], ch))
                if v not in seen:
                    seen[v] = seen[u] + ch
                    q.append(v)
        return None

    def equivalent(self, other: "DFA") -> bool:
        return self.counterexample(other) is None

    # --------------------------------------------------------- serialization
    def to_dict(self) -> dict:
        return {
            "alphabet": self.alphabet,
            "states": self.states,
            "start": self.start,
            "accepting": sorted(self.accepting),
            "transitions": [[s, a, t] for (s, a), t in sorted(self.delta.items())],
        }

    def to_nfa(self) -> "NFA":
        delta: Dict[Tuple[int, str], Set[int]] = {}
        for (s, a), t in self.delta.items():
            delta[(s, a)] = {t}
        return NFA(self.alphabet, self.states, self.start, self.accepting, delta)

    @staticmethod
    def from_dict(d: dict) -> "DFA":
        return DFA(d["alphabet"], d["states"], d["start"], d["accepting"],
                   {(s, a): t for s, a, t in d["transitions"]})

    def graph(self) -> dict:
        """Nodes/edges for the frontend. Dead states (cannot reach an accepting
        state) are flagged so the UI can hide them."""
        comp = self.completed()
        dead = self.sink_states()
        nodes = [{"id": s, "label": f"q{s}", "start": s == comp.start,
                  "accepting": s in comp.accepting, "dead": s in dead}
                 for s in comp.states]
        grouped: Dict[Tuple[int, int], List[str]] = {}
        for (s, a), t in sorted(comp.delta.items()):
            grouped.setdefault((s, t), []).append(a)
        edges = [{"from": s, "to": t, "label": ",".join(syms), "symbols": syms}
                 for (s, t), syms in grouped.items()]
        return {"nodes": nodes, "edges": edges}


def from_functional(alphabet: List[str], init: Hashable,
                    step: Callable[[Hashable, str], Hashable],
                    accept: Callable[[Hashable], bool]) -> DFA:
    """Build a DFA by exploring a state-tracking function (BFS over reachable
    abstract states). Handy for defining reference languages."""
    ids: Dict[Hashable, int] = {init: 0}
    q = deque([init])
    delta: Dict[Tuple[int, str], int] = {}
    while q:
        u = q.popleft()
        for a in alphabet:
            v = step(u, a)
            if v not in ids:
                ids[v] = len(ids)
                q.append(v)
            delta[(ids[u], a)] = ids[v]
    acc = {i for st, i in ids.items() if accept(st)}
    return DFA(alphabet, range(len(ids)), 0, acc, delta)


class NFA:
    """NFA without epsilon moves (enough for the course; keep the model simple)."""

    def __init__(self, alphabet: Iterable[str], states: Iterable[int], start: int,
                 accepting: Iterable[int], delta: Dict[Tuple[int, str], Set[int]]):
        self.alphabet = list(alphabet)
        self.states = sorted(set(states))
        self.start = start
        self.accepting = set(accepting)
        self.delta = {k: set(v) for k, v in delta.items()}

    def run(self, s: str) -> Tuple[bool, List[dict]]:
        cur = {self.start}
        steps = [{"sym": None, "active": sorted(cur)}]
        for ch in s:
            cur = set().union(*[self.delta.get((q, ch), set()) for q in cur]) if cur else set()
            steps.append({"sym": ch, "active": sorted(cur)})
        return bool(cur & self.accepting), steps

    def accepts(self, s: str) -> bool:
        return self.run(s)[0]

    def to_dfa(self) -> Tuple[DFA, List[dict]]:
        """Subset construction. Also returns the table of subsets for display."""
        start = frozenset([self.start])
        ids = {start: 0}
        q = deque([start])
        delta: Dict[Tuple[int, str], int] = {}
        table: List[dict] = []
        while q:
            u = q.popleft()
            row = {"subset": sorted(u), "id": ids[u], "moves": {}}
            for a in self.alphabet:
                v = frozenset().union(*[self.delta.get((s, a), set()) for s in u]) if u else frozenset()
                if v not in ids:
                    ids[v] = len(ids)
                    q.append(v)
                delta[(ids[u], a)] = ids[v]
                row["moves"][a] = ids[v]
            table.append(row)
        subsets = {i: sorted(s) for s, i in ids.items()}
        for row in table:
            row["accepting"] = bool(set(row["subset"]) & self.accepting)
        acc = {i for s, i in ids.items() if s & self.accepting}
        dfa = DFA(self.alphabet, range(len(ids)), 0, acc, delta)
        for row in table:
            row["subset_label"] = "{" + ", ".join(f"q{x}" for x in subsets[row["id"]]) + "}"
        return dfa, table

    def to_dict(self) -> dict:
        return {
            "alphabet": self.alphabet,
            "states": self.states,
            "start": self.start,
            "accepting": sorted(self.accepting),
            "transitions": [[s, a, sorted(t)] for (s, a), t in sorted(self.delta.items())],
        }

    @staticmethod
    def from_dict(d: dict) -> "NFA":
        delta: Dict[Tuple[int, str], Set[int]] = {}
        for s, a, ts in d["transitions"]:
            ts = ts if isinstance(ts, list) else [ts]
            delta.setdefault((s, a), set()).update(ts)
        return NFA(d["alphabet"], d["states"], d["start"], d["accepting"], delta)

    def graph(self) -> dict:
        nodes = [{"id": s, "label": f"q{s}", "start": s == self.start,
                  "accepting": s in self.accepting, "dead": False} for s in self.states]
        grouped: Dict[Tuple[int, int], List[str]] = {}
        for (s, a), ts in sorted(self.delta.items()):
            for t in sorted(ts):
                grouped.setdefault((s, t), []).append(a)
        edges = [{"from": s, "to": t, "label": ",".join(syms), "symbols": syms}
                 for (s, t), syms in grouped.items()]
        return {"nodes": nodes, "edges": edges}
