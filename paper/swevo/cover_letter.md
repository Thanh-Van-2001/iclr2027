# Cover letter (draft; fill the author details)

Dear Editors of *Swarm and Evolutionary Computation*,

Please consider the enclosed manuscript, *The convention on the page: an audit of 1644 metaheuristics papers in Scientific Reports against their own reporting rule*, for publication as a regular article.

The paper asks how much of the field's own reporting convention (independent runs, mean and standard deviation per function, the best value in bold, a non-parametric test) reaches the printed page, on every 2024–2025 article of *Scientific Reports* that OpenAlex lists as mentioning a metaheuristic. It uses released instruments under a same-day analysis plan: a model classifier of paper kind (second-labelled by another vendor), a regular-expression scan and a model reading of the full text, an image-based census of every table page of 500 random papers, and a frozen text-layer parser whose numbers on this format are reported as readings and not quoted as rates of the field. Every number in the manuscript is a macro generated from a released run record.

Points the editors should know:

- **Corpus deviation.** The analysis plan named seven fully open-access journals; three publishers' PDF servers blocked automated download (the throttled attempts are recorded in the release), so the corpus is the *Scientific Reports* subset. After review PMC's bulk route (the Open Access Subset on AWS) was found to serve two of the other journals; their 349 papers carry the text scan, the classifier and the frozen parser as a labelled post-hoc contrast (the table in Section 4), not the census, and the manuscript says so. The title says so, and no number in the paper describes the venues in which this journal's readers publish.
- **Human labels.** The reader's precision on the separate-column and Mean/Std-row layouts is the load-bearing measurement of the paper. It is checked against a second vendor's model on two hundred released kit items (reported as a model check, not a validation) and not yet against a person; the kits are released and the manuscript says so plainly. The per-cell-verdict field of the full-text reading is the one on which two readers disagree, one way; the disputed papers are listed in the release. [Replace this bullet once the labels are made.]
- **Concurrent submissions.** Two companion audits of machine-learning and multi-agent venues, using the same parser and reader protocol on different corpora with different questions, are under review elsewhere. They share the instrument and none of the corpus, questions or results.
- **Generative AI.** Large language models were used as labelling instruments under released protocols (named in the manuscript and the run records) and as a drafting and reviewing assistant; the author reviewed and edited all content and takes full responsibility for it.
- **Supplement.** A supplementary file carries the frozen parser's numbers and readings, the reference set, the impossible-pair check and the alternative conventions of the census, and the classifier's prompt; the main text points to it by section.
- **Data and code.** The release (instrument, corpus records, audits, run records, labelling kits) is at the repository named in the submission system; a public archive with a DOI will replace it on acceptance.

Suggested reviewers: researchers who have written on experimental methodology in metaheuristics (the authors of the statistical-test tutorials and guidelines cited in Section 2), and one statistician.

Yours sincerely,

[Author name, affiliation, email]
