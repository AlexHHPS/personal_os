"""spec_quarterback Hermes skill — markdown-first PRD -> Specs.

Two flows back this package:

* **pm-engine (generator)** — :mod:`.lib.api` /
  :func:`spec_quarterback.lib.api.run_from_prd_file`:
  a lean PRD -> ``SpecList`` generation, written as per-project markdown
  via :mod:`.lib.spec_store`.
* **hermes (refiner)** — :mod:`.lib.refiner`: an iterative
  critique -> improve -> score loop that raises the quality of the
  generated specs against the PRD.

History: this is the dissolution of the standalone ``spec-quarterback``
repo (CrewAI brain + Linear publisher). CrewAI was replaced by direct
OmniRoute calls; the Linear publisher was replaced by the markdown spec
store.
"""
