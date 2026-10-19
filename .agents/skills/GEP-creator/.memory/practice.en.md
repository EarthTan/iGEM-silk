> English translation of [practice.md](practice.md). The Chinese original is kept unchanged as the source of truth.

# GEP-Creator Skill Practice Log

## 2026-04-20 — Skill Creation

**Event**: Created the GEP-creator skill for Tiancheng, based on the GEP (Genome Evolution Protocol) concept from the Superlinear Academy EvoMap course.

**Design decisions**:
- The skill is named `GEP-creator` (consistent with the skill-creator naming style)
- The three-element structure (Experience / Environment Fingerprint / Audit Record) maps directly onto the gene capsule design in the EvoMap/GEP papers
- Follows the skill-creator template conventions (SKILL.md + references/ + .memory/)
- The storage path uses `~/.gep/capsules/` as the suggested directory, separate from the OpenClaw workspace

**To be validated**:
- The granularity of the Environment Fingerprint needs practical feedback
- The "success rate" quantification in Audit Record may be rather subjective in informal validation scenarios
- The capsule version management strategy (deprecated + superseded_by) draws on semantic versioning ideas

**Follow-up suggestions**:
- Could add a `gep-evaluator` skill: validate gene capsule quality
- Could add a `gep-searcher` skill: search a known capsule library for capsules suitable for the current task
- Could add a `gep-evolver` skill: mutate + select existing capsules and iterate toward improvement
