"""Generation prompts — PRD -> features -> per-feature SDD document set.

The generator is two-phase:

* **decompose** — one call turns the PRD into a ``FeaturePlanList`` (the plan).
* **expand** — per feature, three staged calls produce ``Requirements`` ->
  ``Design`` -> ``Tasks`` (design sees requirements; tasks sees both).

Plus a once-per-project **constitution** call.

All calls are FREE-FORM JSON (not constrained ``response_format``): the model is
asked for a single raw JSON object, which is parsed leniently downstream
(``json_extract.parse_model``). This tolerates format drift — the whole point,
since every step runs through an LLM — and avoids the GBNF grammar failures that
constrained decoding hits on nested schemas. Each prompt embeds the relevant
skeleton (loaded live from ``specs/template/skeleton/``) as the target structure
and lists the exact JSON keys to emit.

Placeholders filled by the lib modules:
``{{prd_text}}``, ``{{skeleton}}``, ``{{feature_json}}``,
``{{requirements_json}}``, ``{{design_json}}``, ``{{tech_stack}}``,
``{{project_name}}``, ``{{project_structure}}``.
"""

from __future__ import annotations

from typing import Final

_JSON_ONLY: Final[str] = (
    "Output a SINGLE JSON object only — no markdown fences, no commentary before "
    "or after. If you are unsure of a value, give your best effort rather than "
    "omitting the key."
)

# Banned-vocabulary guidance, appended to the prose-bearing document prompts so
# the generator avoids words the critic flags as MAJOR issues. ``{{banned}}`` is
# filled from the live critic prompt (templates_loader.banned_vocabulary).
_BANNED: Final[str] = """\

Avoid the critic's BANNED VOCABULARY — each occurrence is scored as a MAJOR
issue. Instead of these vague words, name the specific actor, numeric threshold,
or behavioral contract. Do NOT use "the system" as the subject of an action
(name the component) and avoid passive voice ("should be done", "is processed").
{{banned}}

"""

# The project's locked repository layout, fed into every per-feature expand call
# so features place files under the SAME root instead of each inventing one
# (e.g. "/app/...") that collides with the constitution. ``{{project_structure}}``
# is filled from ``constitution.project_structure`` (lib.expand).
_LAYOUT: Final[str] = """\

# Project structure (the project's locked repository layout)
{{project_structure}}

Every file path you reference (components, modules, tasks' file changes) MUST
live under this layout. Do NOT invent a different root such as "/app/...". When
the layout above is unspecified, pick ONE root and use it consistently across
requirements, design, and tasks.
"""

# The PRD's canonical, project-shared data model, fed into every feature so all
# features use the SAME entity / field / enum names instead of each inventing a
# different shape for the same domain table. ``{{data_model}}`` is filled from the
# persisted ``DataModel`` (lib.expand); empty when no shared model was extracted.
_DATA_MODEL: Final[str] = """\

# Canonical shared data model (the project's single source of truth)
{{data_model}}

When this feature reads or writes any entity, field, or enum named above, use
those EXACT names, types, and enum member values — do NOT rename, split, merge,
or re-shape them (e.g. never turn "PricingTableRow" into "BaseTariff"). Introduce
a feature-local entity ONLY for something the canonical model does not cover, and
name it so it does not collide with a canonical entity.
"""

# --- Decompose: PRD -> FeaturePlanList -------------------------------------

DECOMPOSE_ROLE: Final[str] = (
    "Strategic Product Decomposer. Goal: split a PRD into a flat list of "
    "mid-size, self-contained features — each independently implementable and "
    "expandable into its own requirements/design/tasks set."
)
DECOMPOSE_TEMPERATURE: Final[float] = 0.2
DECOMPOSE_PROMPT: Final[str] = """\
Decompose the PRD below into a list of mid-size features. A feature is bigger
than a single ticket and smaller than the whole PRD. A PRD typically yields
3-8 features — emit what the PRD genuinely calls for, neither padding nor
cramming.

PRD:
{{prd_text}}

Emit a JSON object with these keys:
- prd_title: string
- prd_goal: string (the PRD's overarching goal)
- features: array of objects, each with:
    - id: literal "feature-" + zero-padded digits, e.g. "feature-01". This is a
      STRUCTURAL identifier, never a description. Ids are unique.
    - title: short human title (1-8 words)
    - slug: short kebab-case slug for the title
    - problem: the user/system problem this feature resolves
    - outcome: what is true once this feature ships
    - scope: array of strings (what this feature includes)
    - dependencies: array of OTHER feature ids this one needs first (acyclic;
      empty when independent)

Coverage: every capability, flow, and business rule in the PRD must be owned by exactly one
feature — do not silently drop a PRD section, and do not let two features claim the same
responsibility.

Honor the IMMUTABLE CONSTRAINTS in your system prompt (TECH STACK, thresholds).
""" + _JSON_ONLY

# --- Requirements ----------------------------------------------------------

REQUIREMENTS_ROLE: Final[str] = (
    "Requirements Engineer. Goal: turn one feature into a complete, testable "
    "requirements document — measurable outcomes, INVEST user stories with "
    "Given/When/Then acceptance criteria, an explicit Out of Scope, enumerated "
    "edge cases, and numeric non-functional requirements."
)
REQUIREMENTS_TEMPERATURE: Final[float] = 0.2
REQUIREMENTS_PROMPT: Final[str] = """\
Write the requirements document for ONE feature, drawn faithfully from the PRD.

# Target structure (skeleton)
{{skeleton}}

# PRD
{{prd_text}}

# Feature to specify
{{feature_json}}

Emit a JSON object with these keys:
- feature_id, feature_title: copy from the feature above (do not rename)
- status: "Draft"
- overview: 2-4 sentences (what, what problem, why now)
- outcomes: array of measurable definition-of-done statements ("A user can X and Y happens")
- in_scope: array of strings
- out_of_scope: array of strings (REQUIRED — at least 2 explicit exclusions; without this,
  AI agents WILL expand scope)
- user_stories: array of objects {id ("US-01"...), title, as_a, i_want, so_that,
  acceptance_criteria: array of "GIVEN ... WHEN ... THEN ..." strings (>=1, include a failure path)}
- edge_cases: array of strings, each "EC-NN: <trigger> -> <defined behavior>" (cover null/empty,
  boundary/max, duplicate/idempotency, partial failure, concurrency, auth expiry, dependency down,
  large datasets, injection/special chars, timezones where relevant)
- nfrs: array of {category, requirement} — include an NFR ONLY when the PRD states or clearly
  implies it, using the PRD's own numbers. Do NOT fabricate SLAs, limits, or thresholds to fill
  categories: if the PRD is silent on one, omit it or tag the value "[ASSUMPTION: needs
  confirmation]". When present, write numbers not adjectives (latency p50/p95, throughput,
  security model, availability SLA, scalability limit, accessibility level)
- open_questions: array of {question, owner, due} — empty array if all resolved

Use only the PRD's intent; do not invent scope. Tag any numeric threshold not in
the PRD inline with "[ASSUMPTION: <rationale>]".
""" + _DATA_MODEL + _LAYOUT + _BANNED + _JSON_ONLY

# --- Design ----------------------------------------------------------------

DESIGN_ROLE: Final[str] = (
    "Software Architect. Goal: turn a requirements document into an "
    "implementable technical design — components with single responsibilities, "
    "a complete data model, full API contracts, and decisions with rationale."
)
DESIGN_TEMPERATURE: Final[float] = 0.2
DESIGN_PROMPT: Final[str] = """\
Write the technical design for the feature whose requirements follow. The design
MUST be implementable as written and consistent with the requirements (same
entity names, every acceptance criterion supported).

# Target structure (skeleton)
{{skeleton}}

# Requirements (authoritative; do not contradict)
{{requirements_json}}

Emit a JSON object with these keys:
- feature_id, feature_title: copy from the requirements (do not rename)
- status: "Draft"
- architecture_overview: how this feature fits the system
- components: array of {name, responsibility (ONE sentence, no "and"), interface, dependencies[]}
- entities: array of {name, description}
- entity_fields: array of {entity, field, type, constraints (PK/NOT NULL/UNIQUE/FK...), description}
  — one row per field, keyed by entity name; complete enough to write migration SQL. Include
  EVERY entity this feature reads or writes, even ones shared with other features, so the data
  model is self-contained.
- relationships: array of strings (e.g. "Vehicle 1-N Trim via vehicle_id")
- endpoints: array of {method, path, auth, request_body, response, errors[] (each "NNN: <payload>")}
- error_handling: string
- security: string (auth model, input validation, rate limiting, secrets)
- decisions: array of {decision, alternative, reason ("we chose X because Y")}
- non_goals: array of strings
- risks: array of {risk, mitigation, area}

Honor the IMMUTABLE CONSTRAINTS (TECH STACK allow-list, threshold tagging).
""" + _DATA_MODEL + _LAYOUT + _BANNED + _JSON_ONLY

# --- Tasks -----------------------------------------------------------------

TASKS_ROLE: Final[str] = (
    "Delivery Lead. Goal: turn requirements + design into an ordered, traceable "
    "task breakdown where every task has a non-interpretive 'done when' and "
    "references the requirement it satisfies."
)
TASKS_TEMPERATURE: Final[float] = 0.2
TASKS_PROMPT: Final[str] = """\
Write the implementation task breakdown for the feature, derived from its
requirements and design.

# Target structure (skeleton)
{{skeleton}}

# Requirements
{{requirements_json}}

# Design
{{design_json}}

Emit a JSON object with these keys:
- feature_id, feature_title: copy from the requirements (do not rename)
- implementation_order: short note on sequencing / what unblocks parallel work
- tasks: array of {id ("T-01"...), title, phase, requirement_refs (US-/EC-/NFR- ids),
  estimate ("S"|"M"|"L"), implement (one-line file/code change), done_when (verifiable, no
  judgment needed), depends_on (task ids)}
  — include explicit test-writing tasks and edge-case-handling tasks
- verification_checklist: array of strings mapping back to the acceptance criteria/edge cases/NFRs
""" + _LAYOUT + _BANNED + _JSON_ONLY

# --- Constitution (once per project) ---------------------------------------

CONSTITUTION_ROLE: Final[str] = (
    "Engineering Lead. Goal: write the project constitution (steering document) "
    "from the declared tech stack and product intent — the durable rules every "
    "feature must honor."
)
CONSTITUTION_TEMPERATURE: Final[float] = 0.2
CONSTITUTION_PROMPT: Final[str] = """\
Write the project constitution from the PRD and its declared tech stack. This is
project-level steering, written ONCE and reused by every feature.

# Target structure (skeleton)
{{skeleton}}

# Project
{{project_name}}

# Declared tech stack
{{tech_stack}}

# PRD (for product vision)
{{prd_text}}

Emit a JSON object with these keys:
- project_name: string
- product_vision: 1-3 sentences (problem, for whom, why it matters)
- tech_stack: array of strings (runtime, framework, database, infra, key deps) — use ONLY the
  declared stack above; do not invent technologies
- architecture_principles: array of strings
- coding_standards: array of strings
- project_structure: short description of the top-level layout
- commands: array of strings (build/test/lint/dev)
- boundaries_always: array of strings (always-do rules)
- boundaries_ask_first: array of strings (ask-before-doing rules)
- boundaries_never: array of strings (never-do rules, e.g. "commit secrets")
- git_workflow: array of strings

The constitution governs HOW the project is built (stack, structure, conventions,
security defaults, workflow) — never WHAT a feature does. Do NOT encode feature-specific
behaviors, approval/confirmation flows, or business rules in the boundaries (e.g. "price
changes need two approvers"); those belong to the PRD and the individual feature specs.
Keep boundaries project-wide and HOW-level.
""" + _JSON_ONLY

# --- Contract: PRD -> one feature's requirement inventory ------------------

CONTRACT_ROLE: Final[str] = (
    "Requirements Auditor. Goal: extract the exhaustive, atomic list of what the "
    "PRD DEMANDS for ONE feature — the checkable ground truth a reviewer uses to "
    "detect whether the spec dropped, changed, or invented scope."
)
CONTRACT_TEMPERATURE: Final[float] = 0.1
CONTRACT_PROMPT: Final[str] = """\
Read the PRD and extract the requirement inventory for ONE feature only. Each item
is one atomic, verifiable thing the PRD requires of THIS feature — a behavior, a
business rule, a formula, a data entity/field, a role/permission, a notification or
alert routing (who is notified of what), a scheduled/periodic/background behavior, a
data-isolation/scoping rule, a state-machine state or transition, an explicit numeric
threshold, or a constraint.

# PRD
{{prd_text}}

# Feature (extract ONLY this feature's requirements)
{{feature_json}}

Emit a JSON object with these keys:
- feature_id, feature_title: copy from the feature above
- items: array of objects, each with:
    - id: "RQ-01", "RQ-02", ... (unique, sequential)
    - kind: one of functional | business_rule | data | nfr | role | formula | constraint
    - statement: what the PRD requires — one atomic claim, quoted or tightly paraphrased
    - prd_ref: the PRD section/heading it comes from
    - priority: "MUST" if the PRD states/implies it is required for this feature, else "SHOULD"

Rules:
- Extract ONLY what the PRD actually says for THIS feature. Do NOT invent
  requirements, and do NOT include implementation detail the PRD leaves open
  (column types, file paths, framework choices) — those are the spec's job, not
  the PRD's contract.
- Prefer many small atomic items over a few broad ones. Capture business rules and
  formulas precisely (exact discounts, the price formula, who confirms what, role
  permissions).
- Be exhaustive about EASILY-MISSED requirements, which are routinely dropped: alert /
  notification ROUTING (which role receives which alert), scheduled / periodic / background
  jobs (nightly runs, retries — capture even PRD-"future" ones as priority "SHOULD"),
  data-isolation / access-scoping rules (per-plant, per-user, per-role visibility), and every
  named state-machine state and transition. Capture each as its own item.
- If the PRD is written in another language, keep the statements in that language.
""" + _JSON_ONLY

# --- Data model: PRD -> the project's canonical shared data model ----------

DATA_MODEL_ROLE: Final[str] = (
    "Data Modeler. Goal: extract the ONE canonical data model the whole product "
    "shares — the entities, fields, and enums that multiple features read and "
    "write — so every feature builds against the same schema, not its own."
)
DATA_MODEL_TEMPERATURE: Final[float] = 0.1
DATA_MODEL_PROMPT: Final[str] = """\
Extract the CANONICAL, project-shared data model from the PRD. This is written
ONCE for the whole product and every feature must use these exact names — it is
what stops two features from modeling the same table in incompatible ways.

# PRD
{{prd_text}}

Emit a JSON object with these keys:
- prd_title: string
- overview: 1-3 sentences on what this data model covers
- entities: array of {name, description} — the durable domain nouns (tables/aggregates)
- entity_fields: array of {entity, field, type, constraints (PK/NOT NULL/UNIQUE/FK -> X),
  description} — one row per field, keyed by the entity name; include every field the PRD
  names or clearly implies, especially keys, foreign keys, and status/enum columns
- enums: array of {name, values: array of strings, description} — every closed value set the
  PRD defines (statuses, kinds, categories, flags), with the EXACT member values
- relationships: array of strings (e.g. "Order 1-N LineItem via order_id")

Rules:
- Capture ONLY entities/fields/enums grounded in the PRD; use the PRD's own names. If the PRD
  has an explicit data-model / schema section, follow it closely.
- This is the SHARED contract: include anything two or more features touch; omit purely
  feature-local helper tables.
- Do NOT invent fields the PRD does not imply, and do NOT decide storage details the PRD
  leaves open beyond what is needed to name the field and its type.
- If the PRD is written in another language, keep names/descriptions in that language.
""" + _JSON_ONLY
