# Bold Without Bars, metaheuristics edition — pre-registered plan

Written 2026-09-18, before any corpus PDF beyond the two 40-paper probes
(arXiv cs.NE, math.OC) was downloaded. Target: *Swarm and Evolutionary
Computation* (Elsevier, elsarticle, single-blind, no page limit; fallback
*Applied Soft Computing*). Third application of the frozen instrument
(`study/`, tag as in the ICLR and AAMAS papers); those two submissions are
disclosed as concurrent and the instrument is not re-described at length.

## Question

Metaheuristics has an explicit reporting convention: N independent runs
(30 is canonical), mean and standard deviation per function, the best
marked in bold, and a non-parametric test (Wilcoxon signed-rank, Friedman)
recommended since García et al. 2009 and Derrac et al. 2011. We ask, over
the open-access metaheuristics literature of 2024–2025:

1. how often the page prints what checking a bold cell needs (both
   dispersions and the run count), by the parser and by an image-based
   reader census;
2. how often the printed evidence resolves the bold at the stated run count
   (Welch's t on the printed means and deviations), and how that relates to
   the statistical test the paper itself reports (Wilcoxon/Friedman markers
   +/=/−, p-values, ranks);
3. how this differs between papers that propose a new optimizer (often
   metaphor-named), papers that compare existing ones on benchmark suites
   (CEC 2017/2020/2022, BBOB), and application papers;
4. whether papers citing the methodology literature (Derrac 2011, García
   2009, Sörensen 2015, Aranha 2022, Camacho-Villalón 2022/23, Bartz-Beielstein
   2020, Beiranvand 2017, Kendall 2016) report differently.

## Corpus (fixed before download)

Fully open-access CC-BY journals with a metaheuristics output, so that text
and data mining is permitted and the corpus is reproducible from an API:
Scientific Reports (2045-2322), Mathematics (2227-7390), Applied Sciences
(2076-3417), Biomimetics (2313-7673), Algorithms (1999-4893), Complex &
Intelligent Systems (2198-6053), PeerJ Computer Science (2376-5992).
Selection: OpenAlex, `type:article`, publication year 2024 or 2025, title
or abstract matching the phrase list in `swevo/harvest_oa.py` (metaheuristic,
evolutionary algorithm, genetic algorithm, particle swarm, differential
evolution, swarm intelligence, ant colony, simulated annealing,
nature-inspired, bio-inspired optimization, grey wolf, whale optimization,
memetic, NSGA). Every listed paper is fetched; failures are counted.
Hybrid-OA journals (SWEVO itself, ASOC) are excluded: their OA subset is a
selected sample.

## Instruments

- The frozen parser, unchanged. Known format hazard, stated in advance:
  metaheuristics tables often print the mean and the standard deviation in
  separate rows ("Mean" / "Std") or separate columns rather than as `a ± b`;
  the parser reads such a mean as bar-less. The census reader is therefore
  the primary instrument for bar presence, and its protocol adds one field:
  whether the dispersion sits beside the mean, in a separate row or column,
  or nowhere.
- Reference set of 140 boxed cells drawn after the parser has run, read by
  two vendors' models under the released protocol (as before); a random-page
  pilot; a census of every caption page of a random subset of papers (size
  set by relay budget, fixed before reading: 500 papers).
- A community classifier (new optimizer / benchmark comparison /
  application / survey-theory) from title and abstract, second-labelled on
  100 papers by another vendor.
- A statistical-test reader: regex over the text for Wilcoxon, Friedman,
  t-test, p-value, rank sums, and the +/=/− convention; a model reading of
  the full text on the papers with testable comparisons (N runs, which
  test, paired or not, on which quantity).
- No number in the paper is typed by hand; every one is a macro from a run
  record; adversarial review rounds before submission; human labels are
  requested from the author for the two strata the reviewers of the AAMAS
  paper asked for.

## What is not decided by the data

The headline unit (one bold cell against the best unmarked value), the
test (Welch's t at the stated run count, two-sided, unlabelled bar read as
a deviation), the failure threshold (p ≥ 0.05) and the corpus rule above
are fixed now. Filters on the parser's output that a reference set exposes
are reported as readings beside the frozen headline, as in the AAMAS paper.
