"""Tests for bundle file writer."""

from pathlib import Path

from scripts.generator.writer import write_bundle


def test_creates_directory_structure(tmp_path: Path):
    bundle_dir = write_bundle(
        output_dir=tmp_path,
        agent_name="MyAgent",
        agent_content="config:\n   developer_name: MyAgent\n",
        bundle_meta_content="<xml/>",
    )

    assert bundle_dir == tmp_path / "aiAuthoringBundles" / "MyAgent"
    assert bundle_dir.is_dir()


def test_writes_agent_file(tmp_path: Path):
    content = "config:\n   developer_name: TestAgent\n"
    write_bundle(tmp_path, "TestAgent", content, "<xml/>")

    agent_file = tmp_path / "aiAuthoringBundles" / "TestAgent" / "TestAgent.agent"
    assert agent_file.exists()
    assert agent_file.read_text() == content


def test_writes_bundle_meta_file(tmp_path: Path):
    meta = '<?xml version="1.0"?>\n<AiAuthoringBundle/>\n'
    write_bundle(tmp_path, "TestAgent", "agent content", meta)

    meta_file = tmp_path / "aiAuthoringBundles" / "TestAgent" / "TestAgent.bundle-meta.xml"
    assert meta_file.exists()
    assert meta_file.read_text() == meta


def test_overwrites_existing_files(tmp_path: Path):
    write_bundle(tmp_path, "Agent", "version 1", "<v1/>")
    write_bundle(tmp_path, "Agent", "version 2", "<v2/>")

    agent_file = tmp_path / "aiAuthoringBundles" / "Agent" / "Agent.agent"
    assert agent_file.read_text() == "version 2"


def test_returns_bundle_dir_path(tmp_path: Path):
    result = write_bundle(tmp_path, "Foo", "content", "<xml/>")
    assert result == tmp_path / "aiAuthoringBundles" / "Foo"


def test_files_are_utf8(tmp_path: Path):
    unicode_content = 'config:\n   agent_description: "Héllo wörld"\n'
    write_bundle(tmp_path, "Unicode", unicode_content, "<xml/>")

    agent_file = tmp_path / "aiAuthoringBundles" / "Unicode" / "Unicode.agent"
    assert agent_file.read_text(encoding="utf-8") == unicode_content
