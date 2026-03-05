"""Tests for sub-agent parsing."""

from pathlib import Path

from scripts.parser.subagent import discover_subagents, parse_subagent


def test_basic_subagent(tmp_path: Path):
    md = tmp_path / "order-support.md"
    md.write_text("""---
name: order-support
description: Handles order inquiries and returns
tools: CheckOrderStatus, ProcessReturn
---
Help customers with their orders.

Always look up the order before processing a return.
If the order is older than 30 days, escalate to a manager.
""")
    topic = parse_subagent(md)
    assert topic.name == "order_support"
    assert topic.description == "Handles order inquiries and returns"
    assert len(topic.action_definitions) == 2
    assert topic.action_definitions[0].name == "check_order_status"
    assert topic.action_definitions[1].name == "process_return"
    assert len(topic.reasoning.instruction_lines) == 3
    assert "Help customers" in topic.reasoning.instruction_lines[0]


def test_subagent_no_tools(tmp_path: Path):
    md = tmp_path / "faq.md"
    md.write_text("""---
name: general-faq
description: Answers general questions
---
Answer general questions.
Be honest if you don't know.
""")
    topic = parse_subagent(md)
    assert topic.name == "general_faq"
    assert len(topic.action_definitions) == 0


def test_subagent_builtin_tools_filtered(tmp_path: Path):
    md = tmp_path / "reviewer.md"
    md.write_text("""---
name: code-reviewer
description: Reviews code
tools: Read, Grep, CustomAnalyzer
---
Review the code.
""")
    topic = parse_subagent(md)
    # Read and Grep are builtin, only CustomAnalyzer should remain
    assert len(topic.action_definitions) == 1
    assert topic.action_definitions[0].name == "custom_analyzer"


def test_subagent_tools_as_list(tmp_path: Path):
    md = tmp_path / "agent.md"
    md.write_text("""---
name: my-agent
description: Test
tools:
  - ToolA
  - ToolB
---
Do things.
""")
    topic = parse_subagent(md)
    assert len(topic.action_definitions) == 2


def test_discover_subagents(tmp_project: Path):
    agents_dir = tmp_project / ".claude" / "agents"
    (agents_dir / "alpha.md").write_text("---\nname: alpha\n---\nAlpha agent.")
    (agents_dir / "beta.md").write_text("---\nname: beta\n---\nBeta agent.")
    (agents_dir / "not-md.txt").write_text("ignored")

    paths = discover_subagents(tmp_project)
    assert len(paths) == 2
    names = [p.stem for p in paths]
    assert "alpha" in names
    assert "beta" in names


def test_subagent_lossy_fields_ignored(tmp_path: Path):
    """Lossy fields like model, maxTurns should not cause errors."""
    md = tmp_path / "agent.md"
    md.write_text("""---
name: test
description: Test agent
model: sonnet
maxTurns: 50
permissionMode: default
---
Do things.
""")
    topic = parse_subagent(md)
    assert topic.name == "test"


def test_subagent_topic_label(tmp_path: Path):
    """The agentforce.label field maps to topic.label."""
    md = tmp_path / "verification.md"
    md.write_text("""---
name: customer-verification
description: Verify customer identity
agentforce:
  label: "Service Customer Verification"
---
Verify the customer.
""")
    topic = parse_subagent(md)
    assert topic.label == "Service Customer Verification"


def test_subagent_available_when(tmp_path: Path):
    """The agentforce.available_when field maps to topic.available_when."""
    md = tmp_path / "account.md"
    md.write_text("""---
name: account-management
description: Manage accounts
agentforce:
  available_when: "@variables.isVerified==True"
---
Manage accounts.
""")
    topic = parse_subagent(md)
    assert topic.available_when == "@variables.isVerified==True"


def test_subagent_with_bindings(tmp_path: Path):
    """The agentforce.bindings.ToolName.with maps to invocation with_bindings."""
    md = tmp_path / "orders.md"
    md.write_text("""---
name: orders
description: Order support
tools: CheckOrder
agentforce:
  bindings:
    CheckOrder:
      with:
        customerId: "@variables.VerifiedCustomerId"
        orderSubject: "..."
---
Handle orders.
""")
    topic = parse_subagent(md)
    assert len(topic.reasoning.action_invocations) == 1
    inv = topic.reasoning.action_invocations[0]
    assert inv.with_bindings == {
        "customerId": "@variables.VerifiedCustomerId",
        "orderSubject": "...",
    }


def test_subagent_set_bindings(tmp_path: Path):
    """The agentforce.bindings.ToolName.set maps to invocation set_bindings."""
    md = tmp_path / "verify.md"
    md.write_text("""---
name: verify
description: Verify identity
tools: IdentifyRecord
agentforce:
  bindings:
    IdentifyRecord:
      set:
        "@variables.isVerified": "@outputs.isVerified"
        "@variables.customerId": "@outputs.customerId"
---
Verify identity.
""")
    topic = parse_subagent(md)
    inv = topic.reasoning.action_invocations[0]
    assert inv.set_bindings == {
        "@variables.isVerified": "@outputs.isVerified",
        "@variables.customerId": "@outputs.customerId",
    }


def test_subagent_post_action_branch(tmp_path: Path):
    """The agentforce.bindings.ToolName.after maps to post_branches."""
    md = tmp_path / "verify.md"
    md.write_text("""---
name: verify
description: Verify identity
tools: IdentifyRecord
agentforce:
  bindings:
    IdentifyRecord:
      set:
        "@variables.isVerified": "@outputs.isVerified"
      after:
        if: "@variables.isVerified"
        transition_to: "case-management"
---
Verify identity.
""")
    topic = parse_subagent(md)
    inv = topic.reasoning.action_invocations[0]
    assert len(inv.post_branches) == 1
    branch = inv.post_branches[0]
    assert branch.condition == "@variables.isVerified"
    assert branch.transition_to == "case_management"


def test_subagent_multiple_post_branches(tmp_path: Path):
    """Multiple after branches as a list."""
    md = tmp_path / "router.md"
    md.write_text("""---
name: router
description: Route based on status
tools: CheckStatus
agentforce:
  bindings:
    CheckStatus:
      set:
        "@variables.status": "@outputs.status"
      after:
        - if: "@variables.status"
          transition_to: "resolved"
        - if: "@variables.needsEscalation"
          transition_to: "escalation"
---
Route.
""")
    topic = parse_subagent(md)
    inv = topic.reasoning.action_invocations[0]
    assert len(inv.post_branches) == 2
    assert inv.post_branches[0].transition_to == "resolved"
    assert inv.post_branches[1].transition_to == "escalation"


def test_after_reasoning_run_with_condition(tmp_path: Path):
    """after_reasoning with conditional run + set parses correctly."""
    md = tmp_path / "case.md"
    md.write_text("""---
name: case-creation
description: Create cases
agentforce:
  after_reasoning:
    - if: "@variables.caseDescriptionCollected"
      run: CreateCase
      with:
        subject: "@variables.caseSubject"
        description: "@variables.caseDescription"
      set:
        "@variables.caseId": "@outputs.caseId"
---
Handle case creation.
""")
    topic = parse_subagent(md)
    assert len(topic.after_reasoning_directives) == 1
    d = topic.after_reasoning_directives[0]
    assert d.condition == "@variables.caseDescriptionCollected"
    assert d.run == "@actions.create_case"
    assert d.with_bindings == {
        "subject": "@variables.caseSubject",
        "description": "@variables.caseDescription",
    }
    assert d.set_bindings == {"@variables.caseId": "@outputs.caseId"}
    assert d.transition_to is None


def test_after_reasoning_bare_transition(tmp_path: Path):
    """after_reasoning transition_to with condition and no run."""
    md = tmp_path / "case.md"
    md.write_text("""---
name: case-creation
description: Create cases
agentforce:
  after_reasoning:
    - if: "@variables.caseId != \\"\\""
      transition_to: "case-confirmation"
---
Handle case creation.
""")
    topic = parse_subagent(md)
    assert len(topic.after_reasoning_directives) == 1
    d = topic.after_reasoning_directives[0]
    assert d.condition == '@variables.caseId != ""'
    assert d.run is None
    assert d.transition_to == "case_confirmation"


def test_after_reasoning_multiple_directives(tmp_path: Path):
    """Multiple after_reasoning entries all parse in order."""
    md = tmp_path / "flow.md"
    md.write_text("""---
name: multi-flow
description: Multi-step flow
agentforce:
  after_reasoning:
    - if: "@variables.verified"
      run: GetHistory
      with:
        customer_id: "@variables.customerId"
      set:
        "@variables.caseCount": "@outputs.previousCases"
    - if: "@variables.caseType != \\"\\""
      transition_to: "case-creation"
---
Handle flow.
""")
    topic = parse_subagent(md)
    assert len(topic.after_reasoning_directives) == 2

    d0 = topic.after_reasoning_directives[0]
    assert d0.condition == "@variables.verified"
    assert d0.run == "@actions.get_history"
    assert d0.with_bindings == {"customer_id": "@variables.customerId"}
    assert d0.set_bindings == {"@variables.caseCount": "@outputs.previousCases"}

    d1 = topic.after_reasoning_directives[1]
    assert d1.condition == '@variables.caseType != ""'
    assert d1.run is None
    assert d1.transition_to == "case_creation"


def test_after_reasoning_unconditional_run(tmp_path: Path):
    """A run without an if condition (unconditional directive)."""
    md = tmp_path / "logger.md"
    md.write_text("""---
name: audit-topic
description: Audit logging
agentforce:
  after_reasoning:
    - run: LogAuditEvent
      with:
        userId: "@variables.userId"
---
Audit all turns.
""")
    topic = parse_subagent(md)
    assert len(topic.after_reasoning_directives) == 1
    d = topic.after_reasoning_directives[0]
    assert d.condition is None
    assert d.run == "@actions.log_audit_event"
    assert d.with_bindings == {"userId": "@variables.userId"}


def test_after_reasoning_empty_list(tmp_path: Path):
    """Empty after_reasoning list produces no directives."""
    md = tmp_path / "empty.md"
    md.write_text("""---
name: simple
description: Simple
agentforce:
  after_reasoning: []
---
Do things.
""")
    topic = parse_subagent(md)
    assert topic.after_reasoning_directives == []


def test_no_agentforce_section_has_no_after_reasoning(tmp_path: Path):
    """Without agentforce section, after_reasoning_directives is empty."""
    md = tmp_path / "plain.md"
    md.write_text("""---
name: plain
description: Plain topic
---
Do things.
""")
    topic = parse_subagent(md)
    assert topic.after_reasoning_directives == []


def test_subagent_no_agentforce_section(tmp_path: Path):
    """Without agentforce section, topic has no label, no available_when, no bindings."""
    md = tmp_path / "simple.md"
    md.write_text("""---
name: simple
description: Simple topic
tools: MyTool
---
Do things.
""")
    topic = parse_subagent(md)
    assert topic.label is None
    assert topic.available_when is None
    inv = topic.reasoning.action_invocations[0]
    assert inv.with_bindings == {}
    assert inv.set_bindings == {}
    assert inv.post_branches == []
