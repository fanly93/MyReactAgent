# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]  
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify compliance with `.specify/memory/constitution.md` before proceeding:

- [ ] **I. Readability** — Is the planned code readable for the target phase? No premature abstractions for Phase 1–2.
- [ ] **II. Dependencies** — Are all new dependencies justified? No convenience-only additions.
- [ ] **III. Explicit** — Are all registrations, configs, and errors explicit? No magic or silent failures.
- [ ] **IV. Layer Boundaries** — Does the design respect `utils → tools → llm/memory → agent → orchestrator → server`? No upward imports.
- [ ] **V. Phase Gate** — Does this work belong to the declared phase? Is the previous phase gate confirmed complete?
- [ ] **VI. Observability** — Are lifecycle events emitted via `_emit()` + `BaseCallbackHandler`? No scattered `print()` calls.
- [ ] **VII. Event Format** — Do all runtime events conform to the unified JSON envelope (`event`, `data`, `timestamp`, `session_id`)?
- [ ] **VIII. Async Rules** — Is sync used in Phase 1? Is async used correctly (no blocking event loop) from Phase 2 onward?
- [ ] **IX. Retry/Fallback** — Are all LLM calls and tool calls wrapped with retry + graceful error handling?
- [ ] **X. Tests** — Does every new core module have a corresponding test file planned?
- [ ] **XI. HITL** — Are destructive tools declared with `is_destructive=True`? Is pause/resume state considered?
- [ ] **XII. Session Isolation** — Is there any global mutable state introduced? (Must be zero.)
- [ ] **XIII. Context Management** — Is `ConversationMemory` configured with a windowing or summarization strategy?
- [ ] **XIV. Validation** — Are tool args and agent outputs validated via Pydantic at module boundaries?
- [ ] **XV. Security** — Are tool results injected as `role: "tool"` messages? Are tool permissions declared?
- [ ] **XVI. Ecosystem** — Are tool loaders designed as plugins? Is MCP integration considered for Phase 4?

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
