# How the paper should read

Reviewers form a judgement in the first forty minutes, most of it in the first
page. Prose is not decoration; it is the channel through which the contribution
either arrives or does not.

Two failure modes matter here. The first is the ordinary one: vague claims,
buried results, throat-clearing. The second is newer: text that is fluent,
grammatical, evenly paced, and unmistakably machine-written. The second is worse
than it looks, because a reviewer who senses it starts discounting the evidence
too. ICLR 2027 requires an AI use statement, so the goal is not concealment. The
goal is that a person took responsibility for every sentence, and that this shows.

## What top papers actually do

Read the opening of any paper that changed its field and the same habits recur.

**They state the finding, not the activity.** "We show that scaling the model
without scaling data hurts" is a finding. "We conduct a comprehensive study of
scaling behaviour" is an activity report. The finding tells the reviewer whether
to keep reading; the activity report tells them nothing.

**The first sentence does work.** No "In recent years, deep learning has achieved
remarkable success." That sentence has appeared in ten thousand papers and
informed no one. Start where the tension is: what everyone assumes, and why it is
wrong or incomplete.

**Sentence length varies.** Read good prose aloud and you hear a rhythm: a long
sentence that develops an idea, then a short one that lands it. Machine-written
text tends to a uniform twenty-word cadence that is exhausting to read even when
every sentence is correct. The `style` module measures this as the standard
deviation of sentence length; below about six words, the prose has flatlined.

**Numbers appear in the abstract.** "Substantially outperforms" is a claim a
reviewer must take on faith. "Reduces error from 12.4% to 8.1%" is one they can
evaluate. Put the number where the decision is made.

**Limitations are stated by the authors.** A weakness the authors name costs a
fraction of what the same weakness costs when a reviewer discovers it. Naming it
also signals that the authors understand their own result, which is the single
strongest correlate of a confident accept.

**Hedging is calibrated, not reflexive.** "May potentially suggest that" hedges
three times and commits to nothing. Either the evidence supports the claim, in
which case say it; or it supports a weaker claim, in which case say the weaker
claim plainly.

## Words and shapes to avoid

Not because any one of them is wrong, but because their frequency rose sharply
after 2022 and reviewers now read them as a signature.

Vocabulary: delve, intricate, pivotal, realm, landscape, tapestry, testament,
underscore, showcase, leverage (as a verb), robust (when it means "good"),
comprehensive, holistic, nuanced, multifaceted, seamless, meticulous.

Shapes, which are more telling than the words:

- *It's not just X, it's Y.* — an essayist's flourish that says nothing.
- *Firstly, secondly, moreover, furthermore* stacked as connective tissue.
- Three-item lists everywhere, because the model likes threes.
- *In conclusion,* opening a conclusion the reader can already see.
- Section-ending summary sentences that restate the section.
- Uniform paragraph length, four to five sentences each, throughout.
- Em-dashes used at a rate no human sustains.

The `style` module flags these. It is advisory: it points, a person decides. A
flagged word in its correct technical sense stays.

## Structure that survives a forty-minute read

The overloaded reviewer reads the title, the abstract, the figures, the main
table, and the first sentence of each section. Write so that pass alone conveys
the contribution.

- **Abstract**: problem, what was done, what was found with a number, what it
  means. In that order. No motivation paragraph.
- **Introduction**: end with an explicit contribution list only if each item is a
  claim, not a task. "We release a benchmark" is a task. "We show existing
  benchmarks cannot distinguish the models they rank" is a claim.
- **First sentence of every section** should be its thesis, not its agenda.
- **Every figure caption** should state the finding, not describe the axes. A
  caption reading "Accuracy versus model size" wastes the one line the skimming
  reviewer will read.
- **Main table** should be legible without the surrounding text: baselines
  named, metric stated, intervals shown, best result marked.

## The discipline behind the prose

Write the limitations section before the results section. It forces honesty
about what the experiments can support, and it is much harder to write
afterwards when the result is in hand and the temptation to overclaim is strong.

Then read the whole thing aloud once. Every sentence you stumble over is a
sentence the reviewer will stumble over, and unlike you they will not reread it.
