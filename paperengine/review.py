"""Adversarial self-review.

The submission is read by people whose default action is rejection: at recent
ICLRs roughly seven submissions in ten are turned down.  The cheapest way to
find out why yours will be is to run the rejection yourself, several times,
before the program committee does.

This module holds the rubric, the reviewer personas, the prompts, and the
bookkeeping that turns a sequence of critiques into a decision about whether
the paper is ready.  It does not call a model itself; a ``judge`` callable is
injected, so the same loop runs under a subagent, an API client, or a human
co-author reading from the same script.

The loop is deliberately pessimistic in two ways.  Reviewers are told to reject
unless convinced, matching how a real committee behaves under load.  And an
objection counts as resolved only when a later round stops raising it, not when
the authors declare it answered.
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Callable, Optional, Sequence

# ---------------------------------------------------------------------------
# personas
# ---------------------------------------------------------------------------

# Four readers, chosen so their failure modes do not overlap.  Redundant
# reviewers agree with each other and miss the same things.
REVIEWERS: list[dict] = [
    {
        "key": "champion",
        "name": "The potential champion",
        "brief": (
            "You are the reviewer most sympathetic to this paper's area. You want to argue for "
            "acceptance in the discussion. Read for the strongest version of the contribution, then "
            "ask what you would need in hand to defend it against a hostile co-reviewer. Your review "
            "should say exactly what is missing that would stop you fighting for it."
        ),
    },
    {
        "key": "methodologist",
        "name": "The methodologist",
        "brief": (
            "You care only about whether the experiments can support the claims. Attack: sample size, "
            "seeds, confidence intervals, whether the reported gaps exceed noise, confounds, "
            "cherry-picked baselines, missing ablations, leakage between train and evaluation data, "
            "and whether the metric measures what the claim says. If a number has no interval, say so. "
            "If a comparison lacks a test, say so. Quantify your objections wherever you can."
        ),
    },
    {
        "key": "novelty_hawk",
        "name": "The novelty hawk",
        "brief": (
            "You have read everything on arXiv since 2023 and you believe this has been done before. "
            "Search for prior work that anticipates the contribution and name it with identifiers. "
            "Distinguish 'genuinely scooped' from 'adjacent but different', and be honest about which "
            "you have found -- a false accusation of unoriginality wastes everyone's time. Also judge "
            "whether the delta over the closest prior work is worth nine pages."
        ),
    },
    {
        "key": "tired_reviewer",
        "name": "The overloaded reviewer",
        "brief": (
            "You have six papers to review this week and forty minutes for this one. You read the "
            "title, the abstract, the figures, the main table, and the first line of each section. "
            "Report what you understood and what you could not tell from that pass, then give the "
            "score you would actually give. If the contribution was not legible in forty minutes, "
            "that is the paper's problem, not yours."
        ),
    },
]

# ICLR asks for a rating and a confidence; these are the dimensions reviewers
# are asked to consider along the way.
RUBRIC = [
    ("claims_and_evidence", "Are the claims stated precisely, and does the evidence support each one?"),
    ("novelty", "What exactly is new relative to the closest prior work?"),
    ("significance", "Would the field change its behaviour if this result were believed?"),
    ("rigour", "Are the experiments sound, controlled, and statistically honest?"),
    ("clarity", "Can a competent non-specialist follow the argument in one pass?"),
    ("reproducibility", "Could an independent group reproduce the headline result from what is provided?"),
    ("limitations", "Are the weaknesses stated by the authors rather than discovered by the reviewer?"),
]

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "rating": {"type": "number", "description": "ICLR 1-10 scale; 6 is a weak accept, 5 a weak reject"},
        "confidence": {"type": "number", "description": "1-5"},
        "summary": {"type": "string", "description": "What the paper claims and does, in your own words"},
        "strengths": {"type": "string"},
        "objections": {
            "type": "array",
            "description": "Every reason you would reject, most damaging first",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "short stable slug, e.g. 'single-seed'"},
                    "severity": {"type": "string", "enum": ["blocking", "major", "minor"]},
                    "dimension": {"type": "string"},
                    "objection": {"type": "string"},
                    "what_would_fix_it": {"type": "string"},
                },
                "required": ["id", "severity", "dimension", "objection", "what_would_fix_it"],
            },
        },
        "questions_to_authors": {"type": "string"},
        "would_champion": {"type": "boolean"},
    },
    "required": ["rating", "confidence", "summary", "strengths", "objections",
                 "questions_to_authors", "would_champion"],
}


def review_prompt(persona: dict, paper_text: str, round_no: int,
                  prior_objections: Sequence[dict] = ()) -> str:
    rubric = "\n".join(f"  - {k}: {q}" for k, q in RUBRIC)
    history = ""
    if prior_objections:
        listed = "\n".join(
            f"  - [{o['severity']}] {o['id']}: {o['objection']}" for o in prior_objections
        )
        history = (
            "\n\nObjections raised in earlier rounds. Check each one against the current draft and "
            "say whether it has actually been resolved. Do not accept an authors' claim of resolution "
            "that the text does not support; equally, do not re-raise something that is now fixed.\n"
            + listed
        )

    return f"""{persona['brief']}

You are reviewing a submission to ICLR 2027 (round {round_no} of internal review). Apply the standard
a real ICLR reviewer applies: the acceptance rate is near 30 percent, so the default outcome is
rejection and the paper must earn its place. Rate on the ICLR 1-10 scale, where 6 is a weak accept
and 5 a weak reject. Do not inflate. A rating of 8 means you would be surprised and disappointed if
this were rejected.

Judge along these dimensions:
{rubric}

Give every objection a short stable id so that it can be tracked across rounds; reuse the id from an
earlier round when you are raising the same point again.{history}

--- BEGIN SUBMISSION ---
{paper_text}
--- END SUBMISSION ---
"""


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Round:
    number: int
    reviews: list[dict]

    @property
    def ratings(self) -> list[float]:
        return [float(r.get("rating", 0)) for r in self.reviews]

    @property
    def mean_rating(self) -> float:
        rs = self.ratings
        return sum(rs) / len(rs) if rs else 0.0

    @property
    def min_rating(self) -> float:
        return min(self.ratings) if self.ratings else 0.0

    def objections(self, severities: Sequence[str] = ("blocking", "major")) -> list[dict]:
        out = []
        for r in self.reviews:
            for o in r.get("objections", []):
                if o.get("severity") in severities:
                    out.append(o)
        return out

    def objection_ids(self, severities: Sequence[str] = ("blocking", "major")) -> set[str]:
        return {o["id"] for o in self.objections(severities)}


@dataclasses.dataclass
class ReviewHistory:
    rounds: list[Round] = dataclasses.field(default_factory=list)

    def add(self, rnd: Round) -> None:
        self.rounds.append(rnd)

    def unresolved(self) -> set[str]:
        return self.rounds[-1].objection_ids() if self.rounds else set()

    def resolved(self) -> set[str]:
        """Ids raised at some point and absent from the latest round."""
        if len(self.rounds) < 2:
            return set()
        ever = set().union(*(r.objection_ids() for r in self.rounds[:-1]))
        return ever - self.rounds[-1].objection_ids()

    def persistent(self) -> set[str]:
        """Ids raised in every round -- these are the real problems."""
        if not self.rounds:
            return set()
        sets = [r.objection_ids() for r in self.rounds]
        return set.intersection(*sets) if sets else set()

    def trajectory(self) -> list[float]:
        return [round(r.mean_rating, 2) for r in self.rounds]

    def ready(self, *, min_mean: float = 6.0, min_floor: float = 5.0) -> tuple[bool, str]:
        """Is the paper ready to submit?

        The floor matters more than the mean. A paper scoring 8, 8, 3 is in more
        danger than one scoring 6, 6, 6, because the 3 becomes the anchor of the
        discussion and the area chair has to justify overriding it.
        """
        if not self.rounds:
            return False, "no review rounds have been run"
        last = self.rounds[-1]
        blocking = [o for o in last.objections(("blocking",))]
        if blocking:
            return False, f"{len(blocking)} blocking objection(s) remain: {sorted({o['id'] for o in blocking})}"
        if last.min_rating < min_floor:
            return False, f"lowest rating is {last.min_rating}, below the floor of {min_floor}"
        if last.mean_rating < min_mean:
            return False, f"mean rating {last.mean_rating:.2f} is below {min_mean}"
        if self.persistent():
            return False, f"objections raised in every round and never fixed: {sorted(self.persistent())}"
        return True, (f"mean {last.mean_rating:.2f}, floor {last.min_rating}, "
                      f"no blocking objections, trajectory {self.trajectory()}")


def run_rounds(
    paper_text_fn: Callable[[int], str],
    judge: Callable[[str, dict], dict],
    *,
    n_rounds: int = 4,
    revise: Optional[Callable[[int, Round, ReviewHistory], None]] = None,
    reviewers: Sequence[dict] = REVIEWERS,
    history_path: Optional[str] = None,
) -> ReviewHistory:
    """Review, revise, review again.

    ``paper_text_fn(round_no)`` returns the current draft, so that a revision
    made between rounds is picked up.  ``judge(prompt, schema)`` returns a dict
    matching :data:`REVIEW_SCHEMA`.  ``revise`` is where the authors respond to
    round ``n`` before round ``n+1`` begins; if it is omitted the loop simply
    measures how the same draft reads to different reviewers.
    """
    history = ReviewHistory()
    for n in range(1, n_rounds + 1):
        text = paper_text_fn(n)
        prior = history.rounds[-1].objections() if history.rounds else []
        reviews = []
        for persona in reviewers:
            verdict = judge(review_prompt(persona, text, n, prior), REVIEW_SCHEMA)
            if verdict:
                verdict["reviewer"] = persona["key"]
                reviews.append(verdict)
        rnd = Round(number=n, reviews=reviews)
        history.add(rnd)

        if history_path:
            os.makedirs(os.path.dirname(os.path.abspath(history_path)), exist_ok=True)
            with open(history_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "trajectory": history.trajectory(),
                    "rounds": [{"number": r.number, "reviews": r.reviews} for r in history.rounds],
                    "resolved": sorted(history.resolved()),
                    "unresolved": sorted(history.unresolved()),
                    "persistent": sorted(history.persistent()),
                }, fh, indent=2)

        ok, why = history.ready()
        if ok and n >= 2:
            break
        if revise and n < n_rounds:
            revise(n, rnd, history)
    return history


def rebuttal_prompt(objections: Sequence[dict], paper_text: str) -> str:
    """Draft the response the authors will need in November anyway.

    Writing it now is not premature: an objection that cannot be answered in a
    rebuttal is one that should change the paper before submission.
    """
    listed = "\n".join(
        f"  - [{o['severity']}] {o['id']} ({o['dimension']}): {o['objection']}\n"
        f"      reviewer says this would fix it: {o['what_would_fix_it']}"
        for o in objections
    )
    return f"""You are the author preparing the ICLR rebuttal. For each objection below, decide which of
these it is, and say so plainly:

  (a) a misreading, which means the paper is unclear and the text must change;
  (b) a fair criticism you can answer with an experiment that fits in the discussion period;
  (c) a fair criticism you cannot answer, which must be moved into the limitations section
      before submission rather than discovered by a reviewer.

Do not argue with (c). A limitation the authors state costs far less than one a reviewer finds.
For each (b), name the exact experiment, its cost, and what result would settle the point.

OBJECTIONS
{listed}

--- BEGIN CURRENT DRAFT ---
{paper_text}
--- END CURRENT DRAFT ---
"""
