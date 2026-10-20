---
name: GEP-creator
description: Trigger this skill when the user wants to solidify proven experience into a "Gene Capsule" and create a shareable, inheritable capability unit. It builds an experience-inheritance system for AI agents, making "one learns, a million inherit" possible.
created: 2026-04-20
version: 0.1.0
---

> **English** | [中文](SKILL.zh.md)

# GEP-creator

Package proven experience into a **gene capsule** that conforms to GEP (Genome Evolution Protocol), so that the experience can be shared safely between agents, validated across environments, and passed on to other agents.

# Creating GEP Capsules

## When to use

- When an agent discovers an effective strategy, workflow, or prompt pattern and wants to make it reusable
- When you want to package a successful experience into a capability unit that can be inherited like a "gene"
- When you need to build an experience-inheritance system for agents instead of starting from scratch every time
- This corresponds to the "gene capsule packaging" stage of the EvoMap/GEP protocol

---

## Core concepts (three elements)

A Gene Capsule consists of three parts:

| Element | Meaning | Role |
| --------------------------------------- | ---------------------------------------- | ------------------------ |
| **Experience (the experience itself)** | The concrete, effective behavioral strategy, prompt, or tool-call sequence | Answers "how to do it" |
| **Environment Fingerprint** | The scenarios, task types, and constraints the experience applies to | Answers "under what circumstances it works" |
| **Audit Record** | How the experience was validated, the tests it passed, its success rate | Answers "why it is reliable" |

---

## Methodology (Abstract layer)

GEP packaging follows these principles:

1. **Effectiveness first** — Only experience validated as effective on real tasks is worth packaging
2. **Clear scenario boundaries** — State explicitly the scope in which the experience applies and the boundaries where it does not
3. **Auditable and traceable** — Record the validation process so that consuming agents can decide independently whether to adopt it
4. **Minimal usable unit** — One capsule solves one core problem; do not over-package

---

## Procedure (Concrete layer)

### Step 1: Identify effective experience

Identify the strategies or outputs that the agent produced during task execution and that led to significantly positive results.

Checklist:

- ✅ The result is significantly better than the baseline (faster, more accurate, better outcome)
- ✅ It is not accidental success (it is repeatable)
- ✅ It does not depend on specific sensitive context (abstract away token counts, specific names, etc., as far as possible)

Tools: review the conversation, session history, or execution logs to extract the key turning points.

### Step 2: Extract the Experience

Condense the effective behavior into a **structured description** containing:

- **Problem type**: what kind of task
- **Core strategy**: what was actually done (tool-call order, prompt strategy, decision points)
- **Key parameters**: important configuration items (such as temperature, max_tokens, the chosen model, etc.)

Format example:

```markdown
## Experience
- Problem type: structured information extraction from long documents
- Core strategy: two-stage extraction — stage one uses a recall model to generate candidate passages, stage two uses a reranking model to score and filter them
- Key parameters: recall_model=xxx, rerank_threshold=0.7, max_candidates=20
```

### Step 3: Generate the Environment Fingerprint

Describe the context in which the experience applies, including:

- **Task domain**: general / programming / writing / data analysis / customer service, etc.
- **Input characteristics**: long text / multi-turn dialogue / structured data / images, etc.
- **Constraints**: time-sensitive? real-time required? resource-limited?
- **Inapplicable scenarios**: state the boundaries explicitly

Format example:

```markdown
## Environment Fingerprint
- Task domain: structured extraction from long documents (>5000 characters)
- Input characteristics: plain text, no figures or tables, mostly paragraphs
- Constraints: completed in a single API call, no multi-turn interaction needed
- Not applicable: short text (<500 characters), mixed figures/tables, multi-turn reasoning tasks
```

### Step 4: Create the Audit Record

Record how the experience was validated and provide evidence of credibility:

- **Validation method**: human evaluation / automated tests / production validation
- **Test cases**: at least 2-3 representative examples (with input → output)
- **Success rate**: pass rate or magnitude of improvement
- **Limitations**: known weaknesses or caveats

Format example:

```markdown
## Audit Record
- Validation method: 2 consecutive weeks of production use + manual spot checks
- Test cases:
  1. Input: [5000-character contract text] → Output: [14 key clauses, none missing]
  2. Input: [3000-character news report] → Output: [8 core events, accurate timeline]
  3. Input: [800-character social media post] → Output: [3 themes, off-topic content correctly filtered out]
- Success rate: ~94% (N=200)
- Limitations: weak at extracting table content; post-processing required
```

### Step 5: Assemble the Gene Capsule

Merge the three parts above into a standardized capsule document and add a metadata header:

```markdown
---
name: Structured Long-Document Extraction v1.0
author: [creator name]
created: 2026-04-20
version: 1.0.0
tags: [extraction, document, RAG, nlp]
validated: true
---

# Gene Capsule: Structured Long-Document Extraction

## Experience
[see Step 2]

## Environment Fingerprint
[see Step 3]

## Audit Record
[see Step 4]

## Usage
- Trigger conditions: ...
- How to invoke: ...
- Caveats: ...
```

### Step 6: Store and register

Store the capsule in the designated location.

---

## Input and output

- **Input**: the effective experience identified by the agent (it may come from a conversation, a session log, or the user's description)
- **Output**: a `.md` gene capsule file in GEP format, consumable by other GEP-compatible agents.
