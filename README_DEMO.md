# Multi-Agent Orchestration Best Practices Demo

A production-style demonstration of how to orchestrate multiple agents using Microsoft Agent Framework (MAF) patterns. This demo builds a **Technical Request Triage System** that classifies, analyzes, reviews, and publishes engineering requests through a 5-stage pipeline.

## What This Demo Does

The demo processes incoming technical requests (architecture reviews, incident analyses, feature requests) through a fully orchestrated multi-agent pipeline:

1. An incoming request is **classified** into a category and enriched with domain context.
2. A **planner agent** assesses complexity and creates an analysis plan.
3. Four specialist agents run **in parallel** analyzing security, reliability, cost, and integration.
4. A **handoff review chain** refines the synthesized report through reviewer → editor → final reviewer.
5. A **human-in-the-loop approval gate** requires explicit approval before publishing recommendations.

Each stage uses a different MAF orchestration pattern, demonstrating how to compose them into a cohesive system.

## Architecture

```
INPUT: Technical request (e.g., "Review our microservices migration plan")
  │
  ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 1: CLASSIFICATION           [WorkflowBuilder]          │
│  Classifier → extract_category → switch-case routing          │
│    ├── ArchitectureReview → enrich with architecture context  │
│    ├── IncidentAnalysis   → enrich with incident context      │
│    └── FeatureRequest     → enrich with feature context       │
└────────────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 2: PLANNING                 [Supervisor Pattern]       │
│  PlannerAgent calls assess_complexity sub-agent as a tool     │
│  Creates structured analysis plan for specialist agents       │
└────────────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 3: PARALLEL ANALYSIS        [WorkflowBuilder]          │
│  DispatchPrompt → fan-out to:                                 │
│    ├── SecurityAgent                                          │
│    ├── ReliabilityAgent                                       │
│    ├── CostAgent                                              │
│    └── IntegrationAgent                                       │
│  → fan-in: SynthesizerExecutor (LLM-driven aggregation)      │
└────────────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 4: HANDOFF REVIEW           [HandoffBuilder]           │
│  Reviewer ←→ Editor → FinalReviewer                           │
│  Routing rules: reviewer can route to editor or final;        │
│  editor can only route back to reviewer.                      │
│  Terminates when final_reviewer says "Goodbye!"               │
└────────────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage 5: HITL APPROVAL            [WorkflowBuilder]          │
│  ApprovalAgent → publish_recommendations tool                 │
│  (approval_mode="always_require")                             │
│  Human must approve/reject before publishing                  │
└────────────────────────────────────────────────────────────────┘
  │
  ▼
OUTPUT: Final approved analysis report
```

## Patterns Used

| Stage | MAF Pattern | Source Example | Key API |
|-------|------------|----------------|---------|
| 1. Classification | Structured output + switch-case routing | `workflow_switch_case.py` | `WorkflowBuilder`, `Case`, `Default`, `response_format` |
| 2. Planning | Supervisor with sub-agent as tool | `agent_supervisor.py` | `Agent`, `@tool` wrapping `agent.run()` |
| 3. Parallel Analysis | Fan-out/fan-in + LLM aggregation | `workflow_aggregator_summary.py` | `add_fan_out_edges`, `add_fan_in_edges`, `Executor` |
| 4. Handoff Review | HandoffBuilder with routing rules | `workflow_handoffbuilder_rules.py` | `HandoffBuilder`, `add_handoff`, `with_autonomous_mode` |
| 5. HITL Approval | Tool-level approval gate | `workflow_hitl_tool_approval.py` | `@tool(approval_mode="always_require")`, `get_request_info_events` |
| Cross-cutting | OpenTelemetry observability | `agent_otel_appinsights.py` | `enable_instrumentation`, `configure_azure_monitor` |
| Post-hoc | Azure AI Evaluation | `agent_evaluation.py` | `IntentResolutionEvaluator`, `TaskAdherenceEvaluator` |

## Why Multi-Agent?

A single agent approach fails for this scenario because:

- **Specialization**: Security, reliability, cost, and integration require different expertise. A single agent trying to cover all domains produces shallow, generic analysis.
- **Parallelism**: Running specialists concurrently reduces latency from ~4x sequential to ~1x parallel.
- **Governance**: Critical recommendations need human approval before publication. Tool-level approval gates enforce this without modifying agent logic.
- **Quality control**: A review chain with explicit handoff rules ensures output quality through structured peer review, not just a single pass.
- **Separation of concerns**: Classification, planning, analysis, review, and approval are distinct responsibilities. Mixing them into one agent creates an unmaintainable prompt.

## Agent Responsibilities

| Agent | Stage | Role |
|-------|-------|------|
| **Classifier** | 1 | Categorizes requests into ArchitectureReview / IncidentAnalysis / FeatureRequest with priority |
| **ComplexityAssessor** | 2 | Sub-agent that evaluates technical complexity (called as tool by Planner) |
| **Planner** | 2 | Creates structured analysis plan with focus areas for each specialist |
| **SecurityAgent** | 3 | Analyzes authentication, data protection, attack surface, compliance |
| **ReliabilityAgent** | 3 | Analyzes availability, failure modes, monitoring, recovery |
| **CostAgent** | 3 | Analyzes infrastructure costs, scaling, optimization, build vs buy |
| **IntegrationAgent** | 3 | Analyzes API contracts, dependencies, data migration, coordination |
| **Synthesizer** | 3 | LLM-driven aggregation of all specialist outputs into executive brief |
| **Reviewer** | 4 | Checks analysis for completeness, accuracy, and clarity |
| **Editor** | 4 | Refines language and structure based on reviewer feedback |
| **FinalReviewer** | 4 | Final quality check before approval stage |
| **ApprovalAgent** | 5 | Prepares and publishes recommendations (requires human approval) |

## How to Run

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Azure credentials (run `azd provision` to set up Azure resources)

### Infrastructure Setup

```bash
# Provision Azure AI Services + Foundry project + App Insights
azd provision
```

This creates:
- **Azure AI Services** account (kind: AIServices) with gpt-5.4 + text-embedding-3-large
- **AI Foundry project** for agent workflows
- **Application Insights** for telemetry

The `.env` file is automatically populated by the post-provision hook.

### Choosing a Provider

The demo supports three providers via the `API_HOST` environment variable in `.env`:

| API_HOST | Provider | Required env vars |
|----------|----------|-------------------|
| `foundry` | Microsoft Foundry (recommended) | `AZURE_AI_PROJECT`, `AZURE_OPENAI_CHAT_DEPLOYMENT` |
| `azure` | Azure OpenAI directly | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT` |
| `openai` | OpenAI API | `OPENAI_API_KEY` |

After `azd provision`, switch to Foundry by editing `.env`:
```
API_HOST=foundry
```

### Basic Run

```bash
# Full pipeline with interactive HITL approval
uv run python demo/orchestrator_demo.py

# Choose a specific request type
uv run python demo/orchestrator_demo.py architecture   # (default)
uv run python demo/orchestrator_demo.py incident
uv run python demo/orchestrator_demo.py feature
```

### With Evaluation

```bash
# Run pipeline + Azure AI Evaluation on the final output
uv run python demo/orchestrator_demo.py --eval
```

### With DevUI

```bash
# Launch DevUI for the parallel analysis workflow (Stage 3)
uv run python demo/orchestrator_demo.py --devui
```

### With Observability

Set `APPLICATIONINSIGHTS_CONNECTION_STRING` in your `.env` file. The demo will automatically enable OpenTelemetry export to Azure Application Insights.

## Stage-by-Stage Walkthrough

### Stage 1: Classification

The classifier agent uses `response_format=ClassifyResult` to produce a structured JSON output. The `extract_category` executor parses this into a typed `ClassifyResult` object. Switch-case edges then route to category-specific enrichment handlers that add relevant domain context.

**Key pattern**: Structured output ensures deterministic routing — no fragile string matching.

### Stage 2: Planning

The planner agent follows the supervisor pattern from `agent_supervisor.py`. It wraps a `ComplexityAssessor` sub-agent as a `@tool`, demonstrating hierarchical delegation. The planner uses this tool to assess complexity, then produces a structured analysis plan.

**Key pattern**: Sub-agents as tools enable composable, testable agent hierarchies.

### Stage 3: Parallel Analysis

Four specialist agents run concurrently on the same analysis plan. The `DispatchPrompt` executor broadcasts the plan via fan-out edges. Each specialist analyzes from their domain perspective independently. The `SynthesizerExecutor` collects all outputs and uses an LLM to synthesize them into an executive brief.

**Key pattern**: Fan-out/fan-in reduces latency while maintaining analysis depth.

### Stage 4: Handoff Review

A `HandoffBuilder` orchestrates three review agents with explicit routing rules:
- `reviewer` can hand off to `editor` (for revisions) or `final_reviewer` (when satisfied)
- `editor` can only hand off back to `reviewer`
- `final_reviewer` is terminal (no outgoing handoffs)

The review runs in autonomous mode with streaming events.

**Key pattern**: Routing rules enforce review governance — editor cannot bypass reviewer.

### Stage 5: HITL Approval

The approval agent uses `publish_recommendations` with `approval_mode="always_require"`. The workflow pauses and emits a `function_approval_request` event. The main event loop displays the tool call details and asks the human operator to approve or reject.

**Key pattern**: Declarative tool-level approval — no custom approval logic needed.

## File Structure

```
demo/
  __init__.py              # Package marker
  demo_config.py           # Shared client setup + optional observability
  agent_roles.py           # All agents, executors, tools, Pydantic models
  orchestrator_demo.py     # Main entrypoint — staged pipeline

README_DEMO.md             # This file
```

## Extending the Demo

### Add a new specialist agent

1. Add a `create_*_agent(client)` function in `agent_roles.py`
2. Add the agent to the fan-out/fan-in edges in `build_analysis_workflow()`
3. Update the `SynthesizerExecutor` instructions to mention the new domain

### Add a new request category

1. Add the category to `ClassifyResult.category` literal type
2. Add a condition function (`is_*()`)
3. Add an enrichment executor (`enrich_*`)
4. Add the case to `build_classification_workflow()`

### Add checkpointing

Integrate the `workflow_hitl_checkpoint.py` pattern to save/resume the pipeline at any stage.
