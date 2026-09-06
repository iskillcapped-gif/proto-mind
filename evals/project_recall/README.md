# Practical project recall

This fixed corpus contains 53 ordinary RU/UK/EN questions and 16 synthetic note versions.
It includes a correction, an archived note and a second workspace. Expected results were
written before the search changes; the corpus remained unchanged during the before/after run.

Corpus SHA-256: `f666127c86919395556b492b7e281c8a096d33677bf4023c14fefd5902977d23`.

Run locally, without an account or model:

```sh
python3 scripts/eval_project_recall.py --output /tmp/project-recall-results.json
```

The evaluator creates disposable notes through the ordinary save/correction/archive
operations. It compares the full selected set with the expected current notes in both
automatic recall and library search, and checks that subsequent reads leave all fixture
files byte-identical. Exit status is nonzero for any mismatch.

## Measured selection

Baseline: Native 0.56.1, source `913f8b4`, with only the new evaluator/corpus added.
Candidate: Native 0.57.0, using `local_content_terms_v3`.

| Path | Exact cases before → after | Precision before → after | Recall before → after |
| --- | ---: | ---: | ---: |
| Automatic | 25/53 → 53/53 | 43.84% → 100% | 88.89% → 100% |
| Library | 21/53 → 53/53 | 36.23% → 100% | 69.44% → 100% |

Precision counts selected relevant notes among all selected notes; recall counts selected
relevant notes among all expected notes. Exact cases require the entire selected set to match,
including no-note cases. These are fixed regression examples used to develop this change;
they do not measure general semantic understanding or the quality of a model's final answer.

Additional regression tests cover short filenames, dotfiles, Unicode normalization, full
paths with identical basenames, multiple services, independent topics, missing environments,
legacy clients, source drift and retained history. The existing limits remain: three whole
automatic notes within 6000 characters, and up to five library search results.

Selection remains local and lexical. Aliases and service/environment qualifiers use a finite
vocabulary; paths and identifiers use normalized literal matching. No embedding, provider call,
usage counter, automatic correction or note write is introduced. Provenance/basis text remains
inspectable but no longer causes a library match by itself.

