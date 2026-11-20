"""Automata Lab - FastAPI backend.

Run:  uvicorn main:app --reload      (from the backend/ folder)
Open: http://127.0.0.1:8000
"""
from __future__ import annotations

import os
import random
import time
from typing import Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from automata import DFA, NFA
from generator import (PRESETS, generate_examples, length_test, reference, shortest_disagreement,
                       test_set)
from learning import clean_samples, edsm, lstar, rpni

app = FastAPI(title="Automata Lab")
FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")


# ----------------------------------------------------------------- schemas
class Example(BaseModel):
    s: str
    label: bool


class GenerateReq(BaseModel):
    language: str
    n: int = Field(60, ge=2, le=3000)
    max_len: int = Field(8, ge=1, le=14)
    balance: bool = True
    noise: float = Field(0.0, ge=0, le=0.5)
    seed: Optional[int] = None


class LearnReq(BaseModel):
    alphabet: List[str]
    examples: List[Example] = []
    algorithm: str = "rpni"              # "rpni" | "edsm" | "lstar"
    noise: float = Field(0.0, ge=0, le=0.45)   # expected label noise (fraction), used by edsm
    reference: Optional[str] = None      # preset key; needed for L* and for comparison
    test_max_len: int = 8


class RunReq(BaseModel):
    kind: str = "dfa"                    # "dfa" | "nfa"
    automaton: dict
    string: str
    reference: Optional[str] = None


class ExperimentReq(BaseModel):
    language: str
    sizes: List[int] = [6, 12, 25, 50, 100, 200]
    noise_levels: List[float] = [0, 0.05, 0.1, 0.2, 0.3]
    noise_size: int = 100
    trials: int = Field(6, ge=1, le=15)
    max_len: int = 8


class ClusterReq(BaseModel):
    alphabet: List[str]
    examples: List[Example]
    k: int = Field(2, ge=2, le=8)


class NfaReq(BaseModel):
    alphabet: List[str]
    start: int
    accepting: List[int]
    transitions: List[List]              # [src, symbol, [targets]]
    test_strings: List[str] = []


# --------------------------------------------------------------- endpoints
@app.get("/api/languages")
def languages():
    out = []
    for key, p in PRESETS.items():
        ref = reference(key)
        regular = getattr(ref, "regular", True)
        out.append({"key": key, "title": p["title"], "alphabet": p["alphabet"],
                    "desc": p["desc"], "regular": regular,
                    "min_states": len(ref.minimized().states) if regular else None,
                    "has_nfa": "nfa" in p})
    return out


@app.get("/api/reference/{key}")
def reference_graph(key: str):
    if key not in PRESETS:
        raise HTTPException(404, "Unknown language")
    raw = reference(key)
    if not getattr(raw, "regular", True):
        return {"dfa": None, "graph": None, "nfa": None, "regular": False}
    ref = raw.minimized()
    return {"dfa": ref.to_dict(), "graph": ref.graph(), "regular": True,
            "nfa": PRESETS[key]["nfa"]().graph() if "nfa" in PRESETS[key] else None}


@app.post("/api/generate")
def generate(req: GenerateReq):
    if req.language not in PRESETS:
        raise HTTPException(404, "Unknown language")
    ref = reference(req.language)
    data = generate_examples(ref, req.n, req.max_len, req.balance, req.noise, req.seed)
    return {"alphabet": PRESETS[req.language]["alphabet"],
            "examples": [{"s": s, "label": lab} for s, lab in data],
            "positives": sum(1 for _, l in data if l), "total": len(data)}


def _metrics(pred, truth, short_mask):
    tp = sum(1 for p, t in zip(pred, truth) if p and t)
    fp = sum(1 for p, t in zip(pred, truth) if p and not t)
    fn = sum(1 for p, t in zip(pred, truth) if not p and t)
    correct = [p == t for p, t in zip(pred, truth)]
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    def acc(mask):
        idx = [i for i, m in enumerate(mask) if m]
        return (sum(correct[i] for i in idx) / len(idx)) if idx else None

    return {"accuracy": sum(correct) / len(correct), "precision": prec, "recall": rec,
            "f1": f1, "acc_short": acc(short_mask),
            "acc_long": acc([not m for m in short_mask]),
            "false_accepts": fp, "false_rejects": fn, "tested": len(correct)}


def _evaluate(dfa: DFA, ref: DFA, train: set, max_len: int, n: int = 1500) -> dict:
    ts = test_set(ref, max_len, n, exclude=train)
    pred = [dfa.accepts(s) for s, _, _ in ts]
    truth = [lab for _, lab, _ in ts]
    short = [not longer for _, _, longer in ts]
    return _metrics(pred, truth, short)


@app.post("/api/learn")
def learn(req: LearnReq):
    alphabet = req.alphabet
    if not alphabet or any(len(a) != 1 for a in alphabet):
        raise HTTPException(400, "Alphabet must be single-character symbols.")
    ref = reference(req.reference) if req.reference in PRESETS else None
    examples = [(e.s, e.label) for e in req.examples]
    for s, _ in examples:
        if any(c not in alphabet for c in s):
            raise HTTPException(400, f"String '{s}' uses symbols outside the alphabet.")

    t0 = time.perf_counter()
    if req.algorithm not in ("rpni", "edsm", "lstar"):
        raise HTTPException(400, "Unknown algorithm.")
    if req.algorithm == "lstar":
        if ref is None:
            raise HTTPException(400, "L* needs a teacher: pick a reference language.")
        if not getattr(ref, "regular", True):
            raise HTTPException(400, "L* needs a regular reference language: it cannot ask exact equivalence "
                                     "questions about a non-regular language.")
        dfa, info = lstar(alphabet, ref)
        train = set()
    else:
        if len(examples) < 1:
            raise HTTPException(400, "Add at least one labeled example.")
        if req.algorithm == "edsm":
            dfa, info = edsm(examples, alphabet, noise=req.noise)
        else:
            dfa, info = rpni(examples, alphabet)
        train = {s for s, _ in clean_samples(examples)[0]}
    elapsed = (time.perf_counter() - t0) * 1000

    mini = dfa.minimized()
    resp = {
        "algorithm": req.algorithm,
        "info": info,
        "time_ms": round(elapsed, 2),
        "states_raw": len(dfa.reachable().states),
        "states_minimized": len([s for s in mini.states if s not in mini.sink_states()]),
        "states_with_sink": len(mini.states),
        "dfa": mini.to_dict(),
        "graph": mini.graph(),
        "nfa": (PRESETS[req.reference]["nfa"]().to_dict() if req.reference in PRESETS and "nfa" in PRESETS[req.reference] else mini.to_nfa().to_dict()),
        "nfa_graph": (PRESETS[req.reference]["nfa"]().graph() if req.reference in PRESETS and "nfa" in PRESETS[req.reference] else mini.to_nfa().graph()),
    }
    # fit on the training set itself
    if examples:
        clean = clean_samples(examples)[0]
        resp["train_accuracy"] = sum(mini.accepts(s) == l for s, l in clean) / len(clean)
    if ref is not None and not getattr(ref, "regular", True):
        ce = shortest_disagreement(mini, ref)
        resp["reference"] = {
            "regular": False, "states": None, "equivalent": False, "counterexample": ce,
            "counterexample_ref_label": (ref.accepts(ce) if ce is not None else None),
            "note": "Not a regular language: no DFA can match it exactly.",
        }
        resp["metrics"] = _evaluate(mini, ref, train, req.test_max_len)
    elif ref is not None:
        refmin = ref.minimized()
        ce = mini.counterexample(refmin)
        resp["reference"] = {
            "states": len([s for s in refmin.states if s not in refmin.sink_states()]),
            "equivalent": ce is None,
            "counterexample": ce,
            "counterexample_ref_label": (refmin.accepts(ce) if ce is not None else None),
        }
        resp["metrics"] = _evaluate(mini, ref, train, req.test_max_len)
    return resp


@app.post("/api/run")
def run(req: RunReq):
    if req.kind == "nfa":
        nfa = NFA.from_dict(req.automaton)
        ok, steps = nfa.run(req.string)
        return {"accepted": ok, "steps": steps}
    dfa = DFA.from_dict(req.automaton)
    bad = [c for c in req.string if c not in dfa.alphabet]
    if bad:
        raise HTTPException(400, f"Symbols not in alphabet: {sorted(set(bad))}")
    # run on the completed DFA so the path always ends in a visible state
    comp = dfa.completed()
    ok, steps = comp.run(req.string)
    resp = {"accepted": ok, "steps": steps, "start": comp.start}
    if req.reference in PRESETS:
        truth = reference(req.reference).accepts(req.string)
        resp["reference_accepts"] = truth
        resp["agrees"] = truth == ok
    return resp


@app.post("/api/nfa/convert")
def nfa_convert(req: NfaReq):
    states = {req.start, *req.accepting}
    for s, _a, ts in req.transitions:
        states.add(s)
        states.update(ts if isinstance(ts, list) else [ts])
    try:
        nfa = NFA.from_dict({"alphabet": req.alphabet, "states": sorted(states), "start": req.start,
                             "accepting": req.accepting, "transitions": req.transitions})
    except Exception as exc:  # malformed input from the textarea
        raise HTTPException(400, f"Could not read the NFA: {exc}")
    dfa, table = nfa.to_dfa()
    mini = dfa.minimized()
    results = []
    for s in req.test_strings:
        results.append({"s": s, "nfa": nfa.accepts(s), "dfa": mini.accepts(s)})
    return {"nfa_graph": nfa.graph(), "nfa": nfa.to_dict(), "table": table,
            "dfa_graph": dfa.graph(), "min_graph": mini.graph(), "min_dfa": mini.to_dict(),
            "nfa_states": len(nfa.states), "dfa_states": len(dfa.states),
            "min_states": len([s for s in mini.states if s not in mini.sink_states()]),
            "tests": results}


@app.post("/api/experiment")
def experiment(req: ExperimentReq):
    if req.language not in PRESETS:
        raise HTTPException(404, "Unknown language")
    ref = reference(req.language)
    alphabet = PRESETS[req.language]["alphabet"]
    regular = getattr(ref, "regular", True)
    ref_states = (len([s for s in ref.minimized().states if s not in ref.minimized().sink_states()])
                  if regular else None)

    def trial(n: int, noise: float, seed: int, algo: str = "rpni"):
        data = generate_examples(ref, n, req.max_len, True, noise, seed)
        if algo == "edsm":
            dfa, _ = edsm(data, alphabet, noise=noise)   # assumes the noise level is known
        else:
            dfa, _ = rpni(data, alphabet)
        mini = dfa.minimized()
        # test on strings the learner has not seen; labels come from the clean reference
        m = _evaluate(mini, ref, {s for s, _ in data}, req.max_len, 800)
        return (m["accuracy"], len([s for s in mini.states if s not in mini.sink_states()]),
                (mini.equivalent(ref) if regular else False))

    def curve(points, make):
        out = []
        for p in points:
            accs, sts, eqs = [], [], []
            for t in range(req.trials):
                a, s, e = make(p, 1000 + t)
                accs.append(a); sts.append(s); eqs.append(e)
            out.append({"x": p, "accuracy": float(np.mean(accs)), "acc_std": float(np.std(accs)),
                        "states": float(np.mean(sts)), "exact_rate": float(np.mean(eqs))})
        return out

    sizes = sorted({max(2, int(n)) for n in req.sizes})[:10]
    noises = sorted({float(x) for x in req.noise_levels})[:8]
    return {"language": req.language, "ref_states": ref_states,
            "size_curve": curve(sizes, lambda n, seed: trial(n, 0.0, seed)),
            "noise_curve": curve(noises, lambda z, seed: trial(req.noise_size, z, seed)),
            "size_curve_edsm": curve(sizes, lambda n, seed: trial(n, 0.0, seed, "edsm")),
            "noise_curve_edsm": curve(noises, lambda z, seed: trial(req.noise_size, z, seed, "edsm")),
            "noise_size": req.noise_size, "trials": req.trials}


class LengthReq(BaseModel):
    language: str
    algorithm: str = "rpni"              # "rpni" | "edsm"
    n: int = Field(60, ge=4, le=1000)
    max_len: int = Field(8, ge=2, le=12)
    noise: float = Field(0.0, ge=0, le=0.45)
    per_length: int = Field(40, ge=4, le=200)
    max_test_len: int = Field(0, ge=0, le=30)     # 0 means 3 x max_len
    seed: Optional[int] = 7


@app.post("/api/length-curve")
def length_curve(req: LengthReq):
    """Train once, then test at every string length. For each length we test
    members (recall) and non-members (specificity; for non-regular languages
    these are hard near misses). Shows where generalization breaks down."""
    if req.language not in PRESETS:
        raise HTTPException(404, "Unknown language")
    if req.algorithm not in ("rpni", "edsm"):
        raise HTTPException(400, "Length curve supports rpni and edsm.")
    ref = reference(req.language)
    alphabet = PRESETS[req.language]["alphabet"]
    data = generate_examples(ref, req.n, req.max_len, True, req.noise, req.seed)
    if req.algorithm == "edsm":
        dfa, info = edsm(data, alphabet, noise=req.noise)
    else:
        dfa, info = rpni(data, alphabet)
    mini = dfa.minimized()
    top = min(30, req.max_test_len or 3 * req.max_len)
    rng = random.Random(req.seed)
    points = []
    for ell in range(top + 1):
        members, others = length_test(ref, ell, rng, req.per_length)
        recall = (sum(mini.accepts(s) for s in members) / len(members)) if members else None
        spec = (sum(not mini.accepts(s) for s in others) / len(others)) if others else None
        points.append({"length": ell, "recall": recall, "specificity": spec,
                       "n_members": len(members), "n_others": len(others),
                       "beyond_training": ell > req.max_len})
    return {"language": req.language, "regular": getattr(ref, "regular", True),
            "algorithm": req.algorithm, "train_max_len": req.max_len,
            "training_size": len(data),
            "states": len([s for s in mini.states if s not in mini.sink_states()]),
            "points": points}


def _features(strings: List[str], alphabet: List[str]) -> np.ndarray:
    bigrams = [a + b for a in alphabet for b in alphabet]
    rows = []
    for s in strings:
        L = len(s)
        row = [L]
        row += [s.count(a) for a in alphabet]
        row += [(s.count(a) / L) if L else 0.0 for a in alphabet]
        row += [sum(1 for i in range(L - 1) if s[i:i + 2] == bg) for bg in bigrams]
        row += [1.0 if s and s[0] == a else 0.0 for a in alphabet]
        row += [1.0 if s and s[-1] == a else 0.0 for a in alphabet]
        rows.append(row)
    return np.array(rows, dtype=float)


@app.post("/api/cluster")
def cluster(req: ClusterReq):
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    ex = [(e.s, e.label) for e in req.examples]
    if len(ex) < req.k + 1:
        raise HTTPException(400, f"Need more than {req.k} examples to form {req.k} clusters.")
    X = _features([s for s, _ in ex], req.alphabet)
    Xs = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=req.k, n_init=10, random_state=0).fit(Xs)
    xy = PCA(n_components=2, random_state=0).fit_transform(Xs)
    pts = [{"s": s, "label": lab, "cluster": int(c), "x": float(p[0]), "y": float(p[1])}
           for (s, lab), c, p in zip(ex, km.labels_, xy)]
    summary = []
    for c in range(req.k):
        members = [p for p in pts if p["cluster"] == c]
        pos = sum(1 for p in members if p["label"])
        summary.append({"cluster": c, "size": len(members), "accepted": pos,
                        "rejected": len(members) - pos,
                        "avg_len": float(np.mean([len(p["s"]) for p in members])) if members else 0})
    return {"points": pts, "summary": summary}


# ------------------------------------------------------------- static site
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))