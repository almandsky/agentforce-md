"""End-to-end conversion tests using template inputs."""

from pathlib import Path

from scripts.convert import convert

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_hello_world_template(tmp_path: Path):
    """Convert the hello-world template and verify output structure."""
    bundle_dir = convert(
        project_root=TEMPLATES_DIR / "hello-world",
        agent_name="HelloAgent",
        output_dir=tmp_path,
    )

    assert bundle_dir.is_dir()
    agent_file = bundle_dir / "HelloAgent.agent"
    meta_file = bundle_dir / "HelloAgent.bundle-meta.xml"

    assert agent_file.exists()
    assert meta_file.exists()

    content = agent_file.read_text()
    assert 'developer_name: "HelloAgent"' in content
    assert "topic greeter:" in content
    assert "start_agent entry:" in content
    assert "language:" in content

    meta = meta_file.read_text()
    assert "<bundleType>AGENT</bundleType>" in meta


def test_multi_topic_template(tmp_path: Path):
    """Convert multi-topic template and verify both topics present."""
    bundle_dir = convert(
        project_root=TEMPLATES_DIR / "multi-topic",
        agent_name="AcmeAgent",
        output_dir=tmp_path,
    )

    content = (bundle_dir / "AcmeAgent.agent").read_text()

    # Both topics should be present
    assert "topic order_support:" in content
    assert "topic general_faq:" in content

    # Start agent should route to both
    assert "go_order_support:" in content
    assert "go_general_faq:" in content

    # System instructions from CLAUDE.md
    assert "customer support agent" in content

    # Tools without targets are omitted from action definitions
    # (they would cause compile errors), but topics should still exist
    assert "topic order_support:" in content
    assert "topic general_faq:" in content

    # Linked variables for service agent
    assert "EndUserId: linked string" in content
    assert "RoutableId: linked string" in content
    assert "ContactId: linked string" in content


def test_multi_topic_golden_file(tmp_path: Path):
    """Compare multi-topic output against golden file."""
    golden = FIXTURES_DIR / "multi-topic-expected.agent"
    if not golden.exists():
        # Generate the golden file for the first time
        bundle_dir = convert(
            project_root=TEMPLATES_DIR / "multi-topic",
            agent_name="AcmeAgent",
            output_dir=tmp_path,
        )
        content = (bundle_dir / "AcmeAgent.agent").read_text()
        golden.write_text(content)
        return  # First run creates the golden file

    bundle_dir = convert(
        project_root=TEMPLATES_DIR / "multi-topic",
        agent_name="AcmeAgent",
        output_dir=tmp_path,
    )
    content = (bundle_dir / "AcmeAgent.agent").read_text()
    expected = golden.read_text()
    assert content == expected, (
        "Generated output differs from golden file. "
        "If intentional, delete tests/fixtures/multi-topic-expected.agent and re-run."
    )


def test_verification_gate_template(tmp_path: Path):
    """Convert verification-gate template and verify structure."""
    bundle_dir = convert(
        project_root=TEMPLATES_DIR / "verification-gate",
        agent_name="SecureAgent",
        output_dir=tmp_path,
    )

    content = (bundle_dir / "SecureAgent.agent").read_text()

    assert "topic identity_verification:" in content
    assert "topic account_management:" in content
    assert "topic escalation:" in content

    # Should have linked variables
    assert "EndUserId: linked string" in content


def test_output_directory_structure(tmp_path: Path):
    """Verify the output follows the expected aiAuthoringBundles structure."""
    bundle_dir = convert(
        project_root=TEMPLATES_DIR / "hello-world",
        agent_name="TestAgent",
        output_dir=tmp_path,
    )

    assert bundle_dir == tmp_path / "aiAuthoringBundles" / "TestAgent"
    assert (bundle_dir / "TestAgent.agent").exists()
    assert (bundle_dir / "TestAgent.bundle-meta.xml").exists()


def test_custom_agent_type(tmp_path: Path):
    """Verify employee agent type is set correctly."""
    bundle_dir = convert(
        project_root=TEMPLATES_DIR / "hello-world",
        agent_name="EmpAgent",
        agent_type="AgentforceEmployeeAgent",
        output_dir=tmp_path,
    )

    content = (bundle_dir / "EmpAgent.agent").read_text()
    assert 'agent_type: "AgentforceEmployeeAgent"' in content
    # Employee agents should NOT get service-agent linked variables
    assert "EndUserId" not in content
