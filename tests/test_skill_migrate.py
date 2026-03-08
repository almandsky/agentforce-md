"""Tests for agentforce-skill-migrate SKILL.md discovery and classification logic.

Since agentforce-skill-migrate is a pure SKILL.md instruction doc (not a Python
module), these tests validate:

1. The SKILL.md file itself is well-formed (frontmatter parses correctly)
2. Discovery logic: scanning local and global skill directories
3. Classification logic: simple vs complex signal detection
4. Deduplication: local skills take precedence over global
5. Exclusion: agentforce-* skills are skipped from global scans
6. Migration marking: skills with agentforce: target: are detected as already migrated
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

SKILL_MD = (
    Path(__file__).parent.parent
    / ".claude"
    / "skills"
    / "agentforce-skill-migrate"
    / "SKILL.md"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a SKILL.md file."""
    text = path.read_text()
    match = re.match(r"^---\n(.*?\n)---", text, re.DOTALL)
    assert match, f"No frontmatter found in {path}"
    return yaml.safe_load(match.group(1))


def _write_skill(skill_dir: Path, name: str, extra_frontmatter: str = "",
                 body: str = "Some instructions.") -> Path:
    """Create a minimal SKILL.md in skill_dir/<name>/SKILL.md."""
    d = skill_dir / name
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(f"---\nname: {name}\ndescription: Test skill\n{extra_frontmatter}---\n{body}\n")
    return md


# ---------------------------------------------------------------------------
# 1. SKILL.md file is well-formed
# ---------------------------------------------------------------------------

class TestSkillMdWellFormed:
    """The agentforce-skill-migrate SKILL.md parses correctly."""

    def test_skill_md_exists(self):
        assert SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}"

    def test_frontmatter_parses(self):
        fm = _parse_frontmatter(SKILL_MD)
        assert fm["name"] == "agentforce-skill-migrate"
        assert "description" in fm
        assert "allowed-tools" in fm

    def test_has_argument_hint(self):
        fm = _parse_frontmatter(SKILL_MD)
        assert "argument-hint" in fm

    def test_allowed_tools_include_essentials(self):
        fm = _parse_frontmatter(SKILL_MD)
        tools = fm["allowed-tools"].split()
        for tool in ["Bash", "Read", "Write", "Edit", "Glob"]:
            assert tool in tools, f"Missing allowed tool: {tool}"

    def test_body_has_required_phases(self):
        text = SKILL_MD.read_text()
        assert "## Phase 0: Discover" in text
        assert "## Phase 1: Classify" in text
        assert "## Phase 2A:" in text
        assert "## Phase 2B:" in text

    def test_body_mentions_global_skills(self):
        """The skill should scan both local and global skill directories."""
        text = SKILL_MD.read_text()
        assert "~/.claude/skills/" in text
        assert ".claude/skills/" in text

    def test_body_has_dedup_rule(self):
        text = SKILL_MD.read_text()
        assert "local" in text.lower() and "precedence" in text.lower()

    def test_body_has_exclusion_rule(self):
        """agentforce-* skills should be excluded from global scan."""
        text = SKILL_MD.read_text()
        assert "agentforce-" in text
        # Check that the exclusion rule is documented
        assert "exclusion" in text.lower() or "skip" in text.lower()


# ---------------------------------------------------------------------------
# 2. Discovery logic (simulated with tmp_path)
# ---------------------------------------------------------------------------

class TestDiscovery:
    """Simulate the discovery scan logic described in Phase 0."""

    def _discover(self, local_skills: Path, global_skills: Path) -> list[dict]:
        """Simulate Phase 0 discovery by scanning both directories.

        Returns a list of dicts: {name, source, path, already_migrated}.
        """
        results = {}

        # Scan local first
        for skill_md in sorted(local_skills.glob("*/SKILL.md")):
            name = skill_md.parent.name
            fm = _parse_frontmatter(skill_md)
            migrated = bool(fm.get("agentforce", {}).get("target"))
            results[name] = {
                "name": name,
                "source": "Local",
                "path": str(skill_md),
                "already_migrated": migrated,
            }

        # Scan global, skip agentforce-* and duplicates
        for skill_md in sorted(global_skills.glob("*/SKILL.md")):
            name = skill_md.parent.name
            if name.startswith("agentforce-"):
                continue
            if name in results:
                continue  # local takes precedence
            fm = _parse_frontmatter(skill_md)
            migrated = bool(fm.get("agentforce", {}).get("target"))
            results[name] = {
                "name": name,
                "source": "Global",
                "path": str(skill_md),
                "already_migrated": migrated,
            }

        return list(results.values())

    def test_discovers_local_skills(self, tmp_path: Path):
        local = tmp_path / "local"
        glob = tmp_path / "global"
        local.mkdir()
        glob.mkdir()
        _write_skill(local, "my-skill")

        results = self._discover(local, glob)
        assert len(results) == 1
        assert results[0]["name"] == "my-skill"
        assert results[0]["source"] == "Local"

    def test_discovers_global_skills(self, tmp_path: Path):
        local = tmp_path / "local"
        glob = tmp_path / "global"
        local.mkdir()
        glob.mkdir()
        _write_skill(glob, "global-skill")

        results = self._discover(local, glob)
        assert len(results) == 1
        assert results[0]["name"] == "global-skill"
        assert results[0]["source"] == "Global"

    def test_local_overrides_global(self, tmp_path: Path):
        local = tmp_path / "local"
        glob = tmp_path / "global"
        local.mkdir()
        glob.mkdir()
        _write_skill(local, "shared-skill", body="Local version")
        _write_skill(glob, "shared-skill", body="Global version")

        results = self._discover(local, glob)
        assert len(results) == 1
        assert results[0]["source"] == "Local"
        assert "local" in results[0]["path"]

    def test_excludes_agentforce_skills_from_global(self, tmp_path: Path):
        local = tmp_path / "local"
        glob = tmp_path / "global"
        local.mkdir()
        glob.mkdir()
        _write_skill(glob, "agentforce-convert")
        _write_skill(glob, "agentforce-discover")
        _write_skill(glob, "user-skill")

        results = self._discover(local, glob)
        assert len(results) == 1
        assert results[0]["name"] == "user-skill"

    def test_detects_already_migrated(self, tmp_path: Path):
        local = tmp_path / "local"
        glob = tmp_path / "global"
        local.mkdir()
        glob.mkdir()
        _write_skill(local, "migrated-skill",
                      extra_frontmatter='agentforce:\n  target: "flow://MyFlow"\n')
        _write_skill(local, "pending-skill")

        results = self._discover(local, glob)
        migrated = [r for r in results if r["already_migrated"]]
        pending = [r for r in results if not r["already_migrated"]]
        assert len(migrated) == 1
        assert migrated[0]["name"] == "migrated-skill"
        assert len(pending) == 1
        assert pending[0]["name"] == "pending-skill"

    def test_mixed_local_and_global(self, tmp_path: Path):
        local = tmp_path / "local"
        glob = tmp_path / "global"
        local.mkdir()
        glob.mkdir()
        _write_skill(local, "local-a")
        _write_skill(local, "local-b")
        _write_skill(glob, "global-c")
        _write_skill(glob, "agentforce-optimize")  # should be excluded

        results = self._discover(local, glob)
        names = {r["name"] for r in results}
        assert names == {"local-a", "local-b", "global-c"}


# ---------------------------------------------------------------------------
# 3. Classification logic (simple vs complex signal detection)
# ---------------------------------------------------------------------------

class TestClassification:
    """Test the classification signals described in Phase 1."""

    @staticmethod
    def _classify(body: str) -> str:
        """Classify a SKILL.md body as Simple or Complex.

        Implements the signal detection from Phase 1.
        """
        # Complex (MCP)
        if re.search(r"mcp__\w+", body):
            return "Complex (MCP)"

        # Complex (API/CLI) — bash blocks with external calls
        bash_blocks = re.findall(r"```bash\n(.*?)```", body, re.DOTALL)
        for block in bash_blocks:
            if re.search(r"\bcurl\b|\bwget\b", block):
                return "Complex (API/CLI)"

        # Complex (Code) — Python/JS with HTTP/subprocess
        code_blocks = re.findall(r"```(?:python|javascript|js)\n(.*?)```", body, re.DOTALL)
        for block in code_blocks:
            if re.search(r"\brequests\b|\bfetch\b|\baxios\b|\bsubprocess\b", block):
                return "Complex (Code)"

        # Complex (API) — auth patterns
        if re.search(r"\bBearer\b|\bAPI[_-]?[Kk]ey\b|\bOAuth\b", body):
            return "Complex (API)"

        return "Simple"

    def test_simple_prompt_only(self):
        body = """
        You are a helpful assistant that guides the user
        through filling out a form. Be polite and concise.
        """
        assert self._classify(body) == "Simple"

    def test_complex_mcp_tool(self):
        body = """
        Use mcp__jira__search_issues to find relevant tickets.
        Present the results as a table.
        """
        assert self._classify(body) == "Complex (MCP)"

    def test_complex_curl_in_bash(self):
        body = """
        Call the GitHub API:
        ```bash
        curl -H "Authorization: Bearer $TOKEN" https://api.github.com/repos
        ```
        Parse the response and show repo names.
        """
        assert self._classify(body) == "Complex (API/CLI)"

    def test_complex_wget_in_bash(self):
        body = """
        Download the file:
        ```bash
        wget https://example.com/data.csv
        ```
        """
        assert self._classify(body) == "Complex (API/CLI)"

    def test_complex_python_requests(self):
        body = """
        ```python
        import requests
        resp = requests.get("https://api.example.com/data")
        ```
        """
        assert self._classify(body) == "Complex (Code)"

    def test_complex_js_fetch(self):
        body = """
        ```javascript
        const resp = await fetch("https://api.example.com/data");
        ```
        """
        assert self._classify(body) == "Complex (Code)"

    def test_complex_python_subprocess(self):
        body = """
        ```python
        import subprocess
        result = subprocess.run(["some-cli", "arg"], capture_output=True)
        ```
        """
        assert self._classify(body) == "Complex (Code)"

    def test_complex_bearer_token(self):
        body = """
        Set the Authorization header with Bearer token.
        """
        assert self._classify(body) == "Complex (API)"

    def test_complex_api_key(self):
        body = """
        Pass the API_Key in the X-Api-Key header.
        """
        assert self._classify(body) == "Complex (API)"

    def test_complex_oauth(self):
        body = """
        This skill requires OAuth authentication to access the resource.
        """
        assert self._classify(body) == "Complex (API)"

    def test_simple_with_read_only_bash(self):
        """Bash blocks that only read files should still be Simple."""
        body = """
        Read the config:
        ```bash
        cat config.json
        ls -la
        ```
        Summarize the contents.
        """
        assert self._classify(body) == "Simple"

    def test_simple_markdown_with_code_fences(self):
        """Non-bash/python/js code fences don't trigger complex."""
        body = """
        Example output:
        ```json
        {"status": "ok"}
        ```
        Return a helpful response.
        """
        assert self._classify(body) == "Simple"


# ---------------------------------------------------------------------------
# 4. Naming conventions
# ---------------------------------------------------------------------------

class TestNaming:
    """Test PascalCase naming convention from Phase 2A/2B."""

    @staticmethod
    def _to_pascal(kebab_name: str) -> str:
        """Convert kebab-case to PascalCase."""
        return "".join(word.capitalize() for word in kebab_name.split("-"))

    def test_simple_name(self):
        assert self._to_pascal("my-skill") == "MySkill"

    def test_multi_word(self):
        assert self._to_pascal("check-order-status") == "CheckOrderStatus"

    def test_single_word(self):
        assert self._to_pascal("search") == "Search"

    def test_prompt_template_name(self):
        name = self._to_pascal("my-prompt-skill") + "Prompt"
        assert name == "MyPromptSkillPrompt"

    def test_apex_action_name(self):
        name = self._to_pascal("search-external-api") + "Action"
        assert name == "SearchExternalApiAction"


# ---------------------------------------------------------------------------
# 5. Remote site settings domain extraction
# ---------------------------------------------------------------------------

class TestRemoteSiteName:
    """Test SafeDomainName derivation from Phase 2B.4."""

    @staticmethod
    def _safe_domain(domain: str) -> str:
        """Convert a domain to a safe XML-friendly name."""
        return re.sub(r"[^a-zA-Z0-9_]", "_", domain.replace(".", "_").replace("-", "_"))

    def test_simple_domain(self):
        assert self._safe_domain("api.github.com") == "api_github_com"

    def test_domain_with_hyphens(self):
        assert self._safe_domain("my-api.example.com") == "my_api_example_com"

    def test_domain_with_port(self):
        # Ports should be stripped before calling this, but test robustness
        assert self._safe_domain("api.example.com:8080") == "api_example_com_8080"


# ---------------------------------------------------------------------------
# 6. Integration: templates/multi-topic skills are detectable
# ---------------------------------------------------------------------------

class TestMultiTopicTemplateDiscovery:
    """Verify the multi-topic template has skills that Phase 0 can discover."""

    MULTI_TOPIC = Path(__file__).parent.parent / "templates" / "multi-topic"

    def test_multi_topic_has_skills(self):
        skills = list(self.MULTI_TOPIC.glob(".claude/skills/*/SKILL.md"))
        assert len(skills) == 3

    def test_all_skills_have_frontmatter(self):
        for skill_md in self.MULTI_TOPIC.glob(".claude/skills/*/SKILL.md"):
            fm = _parse_frontmatter(skill_md)
            assert "name" in fm, f"Missing name in {skill_md}"
            assert "description" in fm, f"Missing description in {skill_md}"

    def test_all_template_skills_already_migrated(self):
        """multi-topic skills have agentforce: target: set — should be flagged."""
        for skill_md in self.MULTI_TOPIC.glob(".claude/skills/*/SKILL.md"):
            fm = _parse_frontmatter(skill_md)
            assert fm.get("agentforce", {}).get("target"), (
                f"{skill_md.parent.name} should have agentforce: target: set"
            )

    def test_template_skill_targets(self):
        """Verify the target types in multi-topic template skills."""
        targets = {}
        for skill_md in self.MULTI_TOPIC.glob(".claude/skills/*/SKILL.md"):
            fm = _parse_frontmatter(skill_md)
            name = skill_md.parent.name
            targets[name] = fm.get("agentforce", {}).get("target", "")

        assert targets["check-order-status"].startswith("flow://")
        assert targets["process-return"].startswith("flow://")
        assert targets["search-knowledge"].startswith("retriever://")
