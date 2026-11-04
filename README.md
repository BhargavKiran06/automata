# Automata Lab (TOC Problem 8)

A website that learns a DFA from labeled strings, draws it, lets you test strings step by step, and compares it with a reference automaton. It also studies how the amount of data and label noise change the learned machine.

## Run it

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --reload
```

Open http://127.0.0.1:8000

The page loads vis-network, Chart.js and Google Fonts from CDNs, so the computer needs internet access. If the fonts do not load, the site still works with fallback fonts.

Run the tests (optional): `pip install pytest` then `python -m pytest tests -q` from the project root.

## How it maps to the problem statement

| Requirement | Where |
|---|---|
| Dataset generator for regular languages over configurable alphabets | `backend/generator.py` (8 preset languages, custom alphabet and examples in the UI) |
| DFA and NFA representations with string-acceptance simulation | `backend/automata.py` (`DFA.run`, `NFA.run`) |
| Automata-inference algorithm | `backend/learning.py`: **RPNI** (from examples) and **L\*** (active, with a teacher) |
| Visualize states, transitions, accepting states, execution paths | `frontend/app.js` (`Graph` class, step-by-step path highlight) |
| Accuracy, state count, generalization on unseen strings | `/api/learn` returns accuracy, F1, accuracy on shorter vs longer strings, states |
| Noisy or insufficient training examples | "Experiments" tab (`/api/experiment`) |
| Automata equivalence, state minimization | `DFA.minimized` (Moore refinement), `DFA.counterexample` (product BFS, shortest counterexample) |
| Active learning | L* membership and equivalence queries |
| Clustering for exploratory analysis | "Clusters" tab (features, k-means, PCA) |
| NFA to DFA | "NFA to DFA" tab (subset construction table plus minimized DFA) |

## Folder map

```
automata-lab/
  backend/
    automata.py    DFA, NFA, minimization, equivalence, subset construction
    generator.py   reference languages, example generator, label noise, test sets
    learning.py    RPNI and L*
    main.py        FastAPI endpoints (/api/learn, /api/run, /api/experiment, ...)
  frontend/
    index.html  style.css  app.js
  tests/test_core.py
```

## The two algorithms in plain words

**RPNI (passive).** Put all training strings in a tree (a prefix tree acceptor), one state per prefix. Then walk the states in order and try to merge each one into an earlier state. A merge is allowed only if no accepted string and rejected string end up in the same state after the merge (merging can cascade, because the machine must stay deterministic). If no merge works, the state is kept. What is left is a small DFA consistent with every example. With too little data it overgeneralizes; with noisy labels it needs extra states to fit the wrong labels.

**L\* (active).** The learner keeps an observation table: rows are prefixes, columns are suffixes, cells say whether prefix+suffix is in the language. When the table is closed and consistent it builds a DFA and asks the teacher "is this right?". The teacher answers with a shortest counterexample, the learner adds it to the table, and the loop repeats. It finds the minimal DFA using polynomially many queries.

## Likely viva questions

- Why is the minimized DFA unique? (Myhill-Nerode: states correspond to equivalence classes of strings.)
- Why can RPNI overgeneralize on small data? (Merges that no example forbids are accepted.)
- How do you check that two DFAs accept the same language? (Product automaton: search for a reachable pair where one accepts and the other rejects.)
- Why can an NFA with 4 states need a DFA with 8? (Subset construction can grow exponentially; the "third symbol from the end" language is the classic case.)
- Why does noise hurt RPNI? (It must stay consistent with every label, so wrong labels force extra states.)
- Difference between passive and active learning? (RPNI gets a fixed sample; L* chooses its own questions.)

## Suggested demo flow (5 minutes)

1. Pick "Ends with 01", press Learn: show the 3-state DFA and "Same language as the reference".
2. Test `1101` and step through the path.
3. Switch to "Third symbol from the end is 1", cut the examples to about 12, learn: show the verdict naming a shortest counterexample, then regenerate with 100 examples.
4. Run the L* option: show that it needs only a few dozen queries.
5. Experiments tab: show accuracy rising with data and states exploding with noise.
6. NFA to DFA tab: 4 NFA states become 8 DFA states.

## Known limits (say these before the TA asks)

- The NFA support covers simulation and NFA to DFA conversion; the learner always outputs a DFA.
- NFAs have no epsilon moves.
- Symbols are single characters.
- Presets are the ground truth, so metrics are only available for them (custom examples get training accuracy only).
