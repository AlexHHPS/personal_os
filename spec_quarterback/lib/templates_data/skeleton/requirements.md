# [Feature/Epic Name] — Requirements
Spec ID: [e.g., 007]
Status: [Draft | Reviewed | Approved]
Author: [name]
Last Updated: [YYYY-MM-DD]

---

## 1. Overview & Context
[2-4 sentences: what is this feature, what user problem does it solve, why now]

## 2. Outcomes (Definition of Done)
[Measurable results, not tasks. "A user can X and Y happens."]
- Outcome 1: [e.g., "A registered user can upload a JPEG/PNG ≤10MB and see it in their gallery within 3s"]
- Outcome 2: ...

## 3. Scope
### In Scope
- [Explicitly list what will be built in this iteration]

### Out of Scope
- [Explicitly list what will NOT be built — this is as important as in-scope]
- [e.g., "OAuth login is out of scope for this spec"]

## 4. User Stories & Acceptance Criteria
[Use INVEST framework: Independent, Negotiable, Valuable, Estimable, Small, Testable]
[Use Given/When/Then (Gherkin format) for acceptance criteria — machine-executable]

### US-01: [User story title]
**As a** [role]
**I want to** [action]
**So that** [outcome/value]

**Acceptance Criteria:**
- GIVEN [precondition]  WHEN [action]  THEN [expected result]
- GIVEN [precondition]  WHEN [action]  THEN [expected result]

### US-02: ...

## 5. Edge Cases & Error Scenarios
[This is where specs most often fail — be exhaustive here]
- EC-01: [e.g., file > 10MB → 413 error with message "File too large. Max 10MB."]
- EC-02: [e.g., unsupported file type → 415 with list of accepted types]
- EC-03: [e.g., upload drops mid-transfer → retry logic with idempotency key]
- EC-04: [e.g., user not authenticated → 401 redirect to login]

## 6. Non-Functional Requirements
- **Performance:** [e.g., "API response < 200ms at p99 under normal load"]
- **Security:** [e.g., "All uploads scanned for malware; OWASP Top 10 addressed"]
- **Accessibility:** [e.g., "WCAG 2.1 AA; keyboard navigable"]
- **Compliance:** [e.g., "GDPR: user can delete all their uploads"]
- **Availability:** [e.g., "99.9% uptime SLA for upload endpoint"]

## 7. Open Questions
[Things not yet decided that block or affect implementation]
- Q1: [question] — Owner: [name] — Due: [date]