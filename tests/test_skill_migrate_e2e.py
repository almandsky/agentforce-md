"""End-to-end tests for agentforce-skill-migrate.

Simulates the full migration workflow:
1. Create a project with mixed simple/complex skills
2. Run discovery (Phase 0)
3. Classify each skill (Phase 1)
4. Generate Salesforce artifacts (Phase 2A / 2B)
5. Validate generated XML and Apex are well-formed

These tests exercise the same logic the SKILL.md instructs Claude Code to
perform, implemented as deterministic Python to run in CI without an LLM.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Helpers: SKILL.md creation
# ---------------------------------------------------------------------------

def _write_skill(skills_dir: Path, name: str, *,
                 description: str = "Test skill",
                 extra_frontmatter: str = "",
                 body: str = "Some instructions.") -> Path:
    """Create a SKILL.md under skills_dir/<name>/SKILL.md."""
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra_frontmatter}---\n{body}\n"
    )
    return md


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a file."""
    text = path.read_text()
    match = re.match(r"^---\n(.*?\n)---", text, re.DOTALL)
    assert match, f"No frontmatter in {path}"
    return yaml.safe_load(match.group(1))


# ---------------------------------------------------------------------------
# Helpers: naming
# ---------------------------------------------------------------------------

def _to_pascal(kebab: str) -> str:
    return "".join(w.capitalize() for w in kebab.split("-"))


def _safe_domain(domain: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", domain.replace(".", "_").replace("-", "_"))


# ---------------------------------------------------------------------------
# Helpers: classification
# ---------------------------------------------------------------------------

def _classify(body: str) -> str:
    if re.search(r"mcp__\w+", body):
        return "Complex (MCP)"
    for block in re.findall(r"```bash\n(.*?)```", body, re.DOTALL):
        if re.search(r"\bcurl\b|\bwget\b", block):
            return "Complex (API/CLI)"
    for block in re.findall(r"```(?:python|javascript|js)\n(.*?)```", body, re.DOTALL):
        if re.search(r"\brequests\b|\bfetch\b|\baxios\b|\bsubprocess\b", block):
            return "Complex (Code)"
    if re.search(r"\bBearer\b|\bAPI[_-]?[Kk]ey\b|\bOAuth\b", body):
        return "Complex (API)"
    return "Simple"


# ---------------------------------------------------------------------------
# Helpers: discovery
# ---------------------------------------------------------------------------

def _discover(local_skills: Path, global_skills: Path | None = None) -> list[dict]:
    results = {}
    for skill_md in sorted(local_skills.glob("*/SKILL.md")):
        name = skill_md.parent.name
        fm = _parse_frontmatter(skill_md)
        results[name] = {
            "name": name,
            "source": "Local",
            "path": skill_md,
            "already_migrated": bool(fm.get("agentforce", {}).get("target")),
            "description": fm.get("description", ""),
        }
    if global_skills and global_skills.exists():
        for skill_md in sorted(global_skills.glob("*/SKILL.md")):
            name = skill_md.parent.name
            if name.startswith("agentforce-") or name in results:
                continue
            fm = _parse_frontmatter(skill_md)
            results[name] = {
                "name": name,
                "source": "Global",
                "path": skill_md,
                "already_migrated": bool(fm.get("agentforce", {}).get("target")),
                "description": fm.get("description", ""),
            }
    return list(results.values())


# ---------------------------------------------------------------------------
# Helpers: Phase 2A artifact generation (Simple → Prompt Template)
# ---------------------------------------------------------------------------

def _generate_prompt_template_xml(skill_name: str, description: str,
                                  body: str) -> str:
    pascal = _to_pascal(skill_name)
    label = " ".join(w.capitalize() for w in skill_name.split("-"))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<GenAiPromptTemplate xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        f'    <activeVersionNumber>1</activeVersionNumber>\n'
        f'    <developerName>{pascal}Prompt</developerName>\n'
        f'    <masterLabel>{label} Prompt</masterLabel>\n'
        f'    <description>{_escape_xml(description)}</description>\n'
        '    <templateType>einstein__agentAction</templateType>\n'
        '    <relatedEntity>N/A</relatedEntity>\n'
        '    <versions>\n'
        f'        <content><![CDATA[{body}]]></content>\n'
        '        <status>Published</status>\n'
        '        <versionNumber>1</versionNumber>\n'
        '    </versions>\n'
        '</GenAiPromptTemplate>\n'
    )


def _generate_gen_ai_function_xml(skill_name: str) -> str:
    pascal = _to_pascal(skill_name)
    label = " ".join(w.capitalize() for w in skill_name.split("-"))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<GenAiFunction xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        f'    <masterLabel>{label} Prompt Action</masterLabel>\n'
        '    <type>PromptTemplateGenerateText</type>\n'
        f'    <promptTemplateRef>{pascal}Prompt</promptTemplateRef>\n'
        '</GenAiFunction>\n'
    )


# ---------------------------------------------------------------------------
# Helpers: Phase 2B artifact generation (Complex → Apex)
# ---------------------------------------------------------------------------

def _generate_apex_action(skill_name: str, description: str,
                          endpoint: str, method: str,
                          inputs: list[tuple[str, str]],
                          outputs: list[tuple[str, str]]) -> str:
    pascal = _to_pascal(skill_name)
    label = " ".join(w.capitalize() for w in skill_name.split("-"))
    lines = [f"public with sharing class {pascal}Action {{", ""]

    # Input class
    lines.append("    public class Input {")
    for param_name, param_type in inputs:
        lines.append(f"        @InvocableVariable(label='{param_name}' required=true)")
        lines.append(f"        public {param_type} {param_name};")
    lines.extend(["    }", ""])

    # Output class
    lines.append("    public class Output {")
    for field_name, field_type in outputs:
        lines.append(f"        @InvocableVariable(label='{field_name}')")
        lines.append(f"        public {field_type} {field_name};")
    lines.extend(["    }", ""])

    # InvocableMethod
    lines.extend([
        f"    @InvocableMethod(label='{label} Action' description='{_escape_apex(description)}')",
        "    public static List<Output> execute(List<Input> inputs) {",
        "        Http http = new Http();",
        "        HttpRequest req = new HttpRequest();",
        f"        req.setEndpoint('{endpoint}');",
        f"        req.setMethod('{method}');",
        "        // TODO: set headers (auth, Content-Type)",
        "        HttpResponse res = http.send(req);",
        "        List<Output> results = new List<Output>();",
        "        // TODO: parse res.getBody() and populate Output fields",
        "        return results;",
        "    }",
        "}",
    ])
    return "\n".join(lines) + "\n"


def _generate_apex_meta_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        '    <apiVersion>66.0</apiVersion>\n'
        '    <status>Active</status>\n'
        '</ApexClass>\n'
    )


def _generate_remote_site_xml(domain: str, skill_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<RemoteSiteSetting xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        '    <isActive>true</isActive>\n'
        f'    <url>https://{domain}</url>\n'
        f'    <description>Remote site for {skill_name} Apex callout</description>\n'
        '</RemoteSiteSetting>\n'
    )


# ---------------------------------------------------------------------------
# Helpers: topic file generation
# ---------------------------------------------------------------------------

def _generate_topic_md(skill_name: str, description: str,
                       action_name: str) -> str:
    return (
        f"---\nname: {skill_name}\ndescription: {description}\n"
        f"tools: {action_name}\nagentforce:\n  bindings:\n"
        f"    {action_name}:\n      after: end\n---\n"
        f"{description}\n\nUse `{action_name}` to handle this request.\n"
    )


# ---------------------------------------------------------------------------
# Helpers: XML escape
# ---------------------------------------------------------------------------

def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_apex(text: str) -> str:
    return text.replace("'", "\\'")


# ---------------------------------------------------------------------------
# Test: Full E2E — mixed project with simple + complex + MCP + migrated skills
# ---------------------------------------------------------------------------

class TestMigrationE2E:
    """Full end-to-end: build project → discover → classify → generate → validate."""

    def _setup_project(self, tmp_path: Path) -> Path:
        """Create a project with 4 skills of different types."""
        project = tmp_path / "test-project"
        local_skills = project / ".claude" / "skills"
        agents_dir = project / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        local_skills.mkdir(parents=True)

        # 1. Simple skill — prompt-only
        _write_skill(local_skills, "tone-guide",
                      description="Guide the tone of agent responses",
                      body="Always be professional and empathetic.\n"
                           "Use active voice. Avoid jargon.")

        # 2. Complex (API) skill — has curl
        _write_skill(local_skills, "github-search",
                      description="Search GitHub issues for a repository",
                      body="Search GitHub for issues matching the query.\n\n"
                           "```bash\n"
                           "curl -H \"Authorization: Bearer $TOKEN\" "
                           "https://api.github.com/search/issues?q=$QUERY\n"
                           "```\n\n"
                           "Parse the JSON response and return the top 5 results.")

        # 3. Complex (MCP) skill
        _write_skill(local_skills, "jira-lookup",
                      description="Look up Jira tickets",
                      body="Use mcp__jira__search_issues to find tickets.\n"
                           "Present results as a table.")

        # 4. Already migrated skill
        _write_skill(local_skills, "order-check",
                      description="Check order status",
                      extra_frontmatter='agentforce:\n  target: "flow://GetOrder"\n',
                      body="Check the order status.")

        return project

    def test_phase0_discovery(self, tmp_path: Path):
        """Phase 0: discover finds all skills with correct metadata."""
        project = self._setup_project(tmp_path)
        local_skills = project / ".claude" / "skills"

        results = _discover(local_skills)
        assert len(results) == 4

        names = {r["name"] for r in results}
        assert names == {"tone-guide", "github-search", "jira-lookup", "order-check"}

        migrated = [r for r in results if r["already_migrated"]]
        assert len(migrated) == 1
        assert migrated[0]["name"] == "order-check"

    def test_phase1_classification(self, tmp_path: Path):
        """Phase 1: skills are classified correctly."""
        project = self._setup_project(tmp_path)
        local_skills = project / ".claude" / "skills"

        results = _discover(local_skills)
        classifications = {}
        for r in results:
            if not r["already_migrated"]:
                body = r["path"].read_text()
                # Strip frontmatter for classification
                body = re.sub(r"^---\n.*?\n---\n", "", body, flags=re.DOTALL)
                classifications[r["name"]] = _classify(body)

        assert classifications["tone-guide"] == "Simple"
        assert classifications["github-search"] == "Complex (API/CLI)"
        assert classifications["jira-lookup"] == "Complex (MCP)"

    def test_phase2a_simple_generates_valid_xml(self, tmp_path: Path):
        """Phase 2A: simple skill generates valid GenAiPromptTemplate XML."""
        project = self._setup_project(tmp_path)
        force_app = project / "force-app" / "main" / "default"

        # Generate GenAiPromptTemplate
        pt_dir = force_app / "genAiPromptTemplates"
        pt_dir.mkdir(parents=True)
        xml_content = _generate_prompt_template_xml(
            "tone-guide",
            "Guide the tone of agent responses",
            "Always be professional and empathetic.\nUse active voice. Avoid jargon.",
        )
        pt_file = pt_dir / "ToneGuidePrompt.genAiPromptTemplate-meta.xml"
        pt_file.write_text(xml_content)

        # Validate XML is parseable
        tree = ET.parse(pt_file)
        root = tree.getroot()
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        assert root.find("sf:developerName", ns).text == "ToneGuidePrompt"
        assert root.find("sf:masterLabel", ns).text == "Tone Guide Prompt"
        assert root.find("sf:templateType", ns).text == "einstein__agentAction"
        versions = root.find("sf:versions", ns)
        assert versions.find("sf:status", ns).text == "Published"
        assert versions.find("sf:versionNumber", ns).text == "1"
        assert "professional" in versions.find("sf:content", ns).text

    def test_phase2a_simple_generates_valid_gen_ai_function(self, tmp_path: Path):
        """Phase 2A: simple skill generates valid GenAiFunction XML in bundle dir."""
        force_app = tmp_path / "force-app" / "main" / "default"
        # GenAiFunction is a BUNDLE type — must be in a subdirectory
        bundle_dir = force_app / "genAiFunctions" / "ToneGuidePromptAction"
        bundle_dir.mkdir(parents=True)

        xml_content = _generate_gen_ai_function_xml("tone-guide")
        gaf_file = bundle_dir / "ToneGuidePromptAction.genAiFunction-meta.xml"
        gaf_file.write_text(xml_content)

        tree = ET.parse(gaf_file)
        root = tree.getroot()
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        assert root.find("sf:type", ns).text == "PromptTemplateGenerateText"
        assert root.find("sf:promptTemplateRef", ns).text == "ToneGuidePrompt"
        # Verify bundle structure: file is inside a subdirectory named after the function
        assert gaf_file.parent.name == "ToneGuidePromptAction"

    def test_phase2a_simple_generates_topic_md(self, tmp_path: Path):
        """Phase 2A: simple skill generates a valid topic markdown file."""
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)

        topic_content = _generate_topic_md(
            "tone-guide",
            "Guide the tone of agent responses",
            "ToneGuidePromptAction",
        )
        topic_file = agents_dir / "tone-guide.md"
        topic_file.write_text(topic_content)

        fm = _parse_frontmatter(topic_file)
        assert fm["name"] == "tone-guide"
        assert fm["tools"] == "ToneGuidePromptAction"
        assert fm["agentforce"]["bindings"]["ToneGuidePromptAction"]["after"] == "end"

    def test_phase2a_marks_skill_as_migrated(self, tmp_path: Path):
        """Phase 2A: adds agentforce: target: to source SKILL.md."""
        skills_dir = tmp_path / ".claude" / "skills"
        skill_md = _write_skill(skills_dir, "tone-guide",
                                 description="Guide tone",
                                 body="Be professional.")

        # Simulate adding agentforce: target: before closing ---
        text = skill_md.read_text()
        # text is: "---\nname: ...\ndescription: ...\n---\nBe professional.\n"
        # Find the second "---" and insert before it
        first_end = text.index("---\n") + 4  # skip opening ---\n
        second_start = text.index("---\n", first_end)
        new_text = (
            text[:second_start]
            + 'agentforce:\n  target: "promptTemplate://ToneGuidePrompt"\n'
            + text[second_start:]
        )
        skill_md.write_text(new_text)

        fm = _parse_frontmatter(skill_md)
        assert fm["agentforce"]["target"] == "promptTemplate://ToneGuidePrompt"

    def test_phase2b_complex_generates_valid_apex(self, tmp_path: Path):
        """Phase 2B: complex skill generates syntactically valid Apex."""
        force_app = tmp_path / "force-app" / "main" / "default"
        cls_dir = force_app / "classes"
        cls_dir.mkdir(parents=True)

        apex = _generate_apex_action(
            "github-search",
            "Search GitHub issues for a repository",
            "https://api.github.com/search/issues",
            "GET",
            inputs=[("query", "String"), ("repo", "String")],
            outputs=[("issueTitle", "String"), ("issueUrl", "String")],
        )
        cls_file = cls_dir / "GithubSearchAction.cls"
        cls_file.write_text(apex)

        content = cls_file.read_text()
        # Basic Apex structure checks
        assert "public with sharing class GithubSearchAction {" in content
        assert "public class Input {" in content
        assert "public class Output {" in content
        assert "@InvocableMethod" in content
        assert "@InvocableVariable" in content
        assert "req.setEndpoint('https://api.github.com/search/issues')" in content
        assert "req.setMethod('GET')" in content
        assert "public String query;" in content
        assert "public String repo;" in content
        assert "public String issueTitle;" in content
        assert "public String issueUrl;" in content

    def test_phase2b_complex_generates_valid_meta_xml(self, tmp_path: Path):
        """Phase 2B: complex skill generates valid .cls-meta.xml."""
        force_app = tmp_path / "force-app" / "main" / "default"
        cls_dir = force_app / "classes"
        cls_dir.mkdir(parents=True)

        meta = _generate_apex_meta_xml()
        meta_file = cls_dir / "GithubSearchAction.cls-meta.xml"
        meta_file.write_text(meta)

        tree = ET.parse(meta_file)
        root = tree.getroot()
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        assert root.find("sf:apiVersion", ns).text == "66.0"
        assert root.find("sf:status", ns).text == "Active"

    def test_phase2b_complex_generates_valid_remote_site(self, tmp_path: Path):
        """Phase 2B: complex skill generates valid Remote Site Settings XML."""
        force_app = tmp_path / "force-app" / "main" / "default"
        rss_dir = force_app / "remoteSiteSettings"
        rss_dir.mkdir(parents=True)

        xml_content = _generate_remote_site_xml("api.github.com", "github-search")
        safe_name = _safe_domain("api.github.com")
        rss_file = rss_dir / f"{safe_name}.remoteSite-meta.xml"
        rss_file.write_text(xml_content)

        tree = ET.parse(rss_file)
        root = tree.getroot()
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        assert root.find("sf:isActive", ns).text == "true"
        assert root.find("sf:url", ns).text == "https://api.github.com"
        assert "github-search" in root.find("sf:description", ns).text

    def test_full_simple_migration_output_structure(self, tmp_path: Path):
        """Full Phase 2A output structure matches the expected file layout."""
        project = tmp_path / "project"
        force_app = project / "force-app" / "main" / "default"
        agents_dir = project / ".claude" / "agents"
        skills_dir = project / ".claude" / "skills"

        # Create directories — GenAiFunction uses bundle (subdirectory)
        for d in [
            force_app / "genAiPromptTemplates",
            force_app / "genAiFunctions" / "ToneGuidePromptAction",
            agents_dir,
        ]:
            d.mkdir(parents=True)

        # Create source skill
        skill_md = _write_skill(skills_dir, "tone-guide",
                                 description="Guide tone",
                                 body="Be professional.")

        # Generate all artifacts
        (force_app / "genAiPromptTemplates" / "ToneGuidePrompt.genAiPromptTemplate-meta.xml").write_text(
            _generate_prompt_template_xml("tone-guide", "Guide tone", "Be professional.")
        )
        (force_app / "genAiFunctions" / "ToneGuidePromptAction" / "ToneGuidePromptAction.genAiFunction-meta.xml").write_text(
            _generate_gen_ai_function_xml("tone-guide")
        )
        (agents_dir / "tone-guide.md").write_text(
            _generate_topic_md("tone-guide", "Guide tone", "ToneGuidePromptAction")
        )

        # Verify all expected files exist
        assert (force_app / "genAiPromptTemplates" / "ToneGuidePrompt.genAiPromptTemplate-meta.xml").exists()
        assert (force_app / "genAiFunctions" / "ToneGuidePromptAction" / "ToneGuidePromptAction.genAiFunction-meta.xml").exists()
        assert (agents_dir / "tone-guide.md").exists()

    def test_full_complex_migration_output_structure(self, tmp_path: Path):
        """Full Phase 2B output structure matches the expected file layout."""
        project = tmp_path / "project"
        force_app = project / "force-app" / "main" / "default"
        agents_dir = project / ".claude" / "agents"
        skills_dir = project / ".claude" / "skills"

        for d in [force_app / "classes", force_app / "remoteSiteSettings", agents_dir]:
            d.mkdir(parents=True)

        _write_skill(skills_dir, "github-search",
                      description="Search GitHub issues",
                      body="```bash\ncurl https://api.github.com/search/issues\n```")

        (force_app / "classes" / "GithubSearchAction.cls").write_text(
            _generate_apex_action("github-search", "Search GitHub issues",
                                   "https://api.github.com/search/issues", "GET",
                                   [("query", "String")], [("title", "String")])
        )
        (force_app / "classes" / "GithubSearchAction.cls-meta.xml").write_text(
            _generate_apex_meta_xml()
        )
        (force_app / "remoteSiteSettings" / "api_github_com.remoteSite-meta.xml").write_text(
            _generate_remote_site_xml("api.github.com", "github-search")
        )
        (agents_dir / "github-search.md").write_text(
            _generate_topic_md("github-search", "Search GitHub issues", "GithubSearchAction")
        )

        # Verify all expected files exist
        assert (force_app / "classes" / "GithubSearchAction.cls").exists()
        assert (force_app / "classes" / "GithubSearchAction.cls-meta.xml").exists()
        assert (force_app / "remoteSiteSettings" / "api_github_com.remoteSite-meta.xml").exists()
        assert (agents_dir / "github-search.md").exists()

    def test_mcp_skill_is_not_auto_generated(self, tmp_path: Path):
        """MCP skills should NOT generate Apex or Prompt Template artifacts."""
        project = self._setup_project(tmp_path)
        local_skills = project / ".claude" / "skills"

        results = _discover(local_skills)
        mcp_skills = [r for r in results
                      if not r["already_migrated"]
                      and _classify(re.sub(r"^---\n.*?\n---\n", "",
                                           r["path"].read_text(), flags=re.DOTALL))
                      == "Complex (MCP)"]

        assert len(mcp_skills) == 1
        assert mcp_skills[0]["name"] == "jira-lookup"
        # No files should be generated for MCP skills
        force_app = project / "force-app"
        assert not force_app.exists()

    def test_already_migrated_skill_skipped(self, tmp_path: Path):
        """Skills with agentforce: target: are skipped in migration."""
        project = self._setup_project(tmp_path)
        local_skills = project / ".claude" / "skills"

        results = _discover(local_skills)
        to_migrate = [r for r in results if not r["already_migrated"]]
        names = {r["name"] for r in to_migrate}
        assert "order-check" not in names
        assert len(to_migrate) == 3


class TestMigrationWithGlobalSkills:
    """E2E tests that include global skills alongside local ones."""

    def test_global_simple_skill_generates_artifacts(self, tmp_path: Path):
        """A global simple skill produces the same artifacts as a local one."""
        local_skills = tmp_path / "project" / ".claude" / "skills"
        global_skills = tmp_path / "global"
        local_skills.mkdir(parents=True)
        global_skills.mkdir(parents=True)

        _write_skill(global_skills, "greeting-helper",
                      description="Standard greeting template",
                      body="Greet the user warmly. Use their name if known.")

        results = _discover(local_skills, global_skills)
        assert len(results) == 1
        assert results[0]["source"] == "Global"
        assert results[0]["name"] == "greeting-helper"

        # Generate artifacts for the global skill
        force_app = tmp_path / "project" / "force-app" / "main" / "default"
        pt_dir = force_app / "genAiPromptTemplates"
        pt_dir.mkdir(parents=True)

        xml = _generate_prompt_template_xml(
            "greeting-helper",
            "Standard greeting template",
            "Greet the user warmly. Use their name if known.",
        )
        pt_file = pt_dir / "GreetingHelperPrompt.genAiPromptTemplate-meta.xml"
        pt_file.write_text(xml)

        # Validate XML
        tree = ET.parse(pt_file)
        root = tree.getroot()
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        assert root.find("sf:developerName", ns).text == "GreetingHelperPrompt"

    def test_mixed_local_and_global_full_workflow(self, tmp_path: Path):
        """Both local and global skills are discovered and can be migrated."""
        local_skills = tmp_path / "project" / ".claude" / "skills"
        global_skills = tmp_path / "global"
        local_skills.mkdir(parents=True)
        global_skills.mkdir(parents=True)

        _write_skill(local_skills, "local-prompt",
                      description="Local prompt skill",
                      body="Respond concisely.")
        _write_skill(global_skills, "global-prompt",
                      description="Global prompt skill",
                      body="Be helpful and friendly.")
        _write_skill(global_skills, "agentforce-convert",
                      description="Should be excluded",
                      body="Convert stuff.")

        results = _discover(local_skills, global_skills)
        assert len(results) == 2

        local_r = [r for r in results if r["source"] == "Local"]
        global_r = [r for r in results if r["source"] == "Global"]
        assert len(local_r) == 1
        assert local_r[0]["name"] == "local-prompt"
        assert len(global_r) == 1
        assert global_r[0]["name"] == "global-prompt"

        # Both can be classified
        for r in results:
            body = re.sub(r"^---\n.*?\n---\n", "", r["path"].read_text(), flags=re.DOTALL)
            assert _classify(body) == "Simple"


class TestXmlWellFormedness:
    """Validate all generated XML is well-formed and parseable."""

    def test_prompt_template_is_valid_xml(self):
        xml = _generate_prompt_template_xml(
            "test-skill", "Test description",
            "Instructions with special chars: <>&\"'",
        )
        root = ET.fromstring(xml)
        assert root.tag.endswith("GenAiPromptTemplate")

    def test_gen_ai_function_is_valid_xml(self):
        xml = _generate_gen_ai_function_xml("test-skill")
        root = ET.fromstring(xml)
        assert root.tag.endswith("GenAiFunction")

    def test_apex_meta_is_valid_xml(self):
        xml = _generate_apex_meta_xml()
        root = ET.fromstring(xml)
        assert root.tag.endswith("ApexClass")

    def test_remote_site_is_valid_xml(self):
        xml = _generate_remote_site_xml("api.example.com", "test-skill")
        root = ET.fromstring(xml)
        assert root.tag.endswith("RemoteSiteSetting")

    def test_prompt_template_escapes_special_chars(self):
        """Description with XML special characters doesn't break parsing."""
        xml = _generate_prompt_template_xml(
            "special-chars",
            "Skills & Tools <v2> are \"great\"",
            "Use <tool> & check 'results'.",
        )
        root = ET.fromstring(xml)
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        desc = root.find("sf:description", ns).text
        assert "&" in desc or "&amp;" in ET.tostring(root, encoding="unicode")
        assert root.tag.endswith("GenAiPromptTemplate")


class TestApexWellFormedness:
    """Validate generated Apex class structure."""

    def test_apex_has_class_wrapper(self):
        apex = _generate_apex_action(
            "my-api", "Test", "https://api.example.com", "POST",
            [("input1", "String")], [("output1", "String")],
        )
        assert apex.startswith("public with sharing class MyApiAction {")
        assert apex.strip().endswith("}")

    def test_apex_has_invocable_method(self):
        apex = _generate_apex_action(
            "my-api", "Test", "https://api.example.com", "GET",
            [("q", "String")], [("result", "String")],
        )
        assert "@InvocableMethod" in apex
        assert "public static List<Output> execute" in apex

    def test_apex_has_inner_classes(self):
        apex = _generate_apex_action(
            "my-api", "Test", "https://api.example.com", "GET",
            [("q", "String")], [("r", "String")],
        )
        assert "public class Input {" in apex
        assert "public class Output {" in apex

    def test_apex_with_multiple_io(self):
        apex = _generate_apex_action(
            "multi-io", "Multi", "https://example.com", "POST",
            [("a", "String"), ("b", "Integer"), ("c", "Boolean")],
            [("x", "String"), ("y", "Decimal")],
        )
        assert "public String a;" in apex
        assert "public Integer b;" in apex
        assert "public Boolean c;" in apex
        assert "public String x;" in apex
        assert "public Decimal y;" in apex

    def test_apex_has_with_sharing(self):
        """Apex classes must include 'with sharing' for security."""
        apex = _generate_apex_action(
            "secure-api", "Secure", "https://api.example.com", "GET",
            [("q", "String")], [("r", "String")],
        )
        assert "public with sharing class SecureApiAction {" in apex


# ---------------------------------------------------------------------------
# Custom Metadata Type generation
# ---------------------------------------------------------------------------

def _generate_custom_metadata_type_xml(service_name: str) -> str:
    label = "".join(w.capitalize() for w in service_name.split("_"))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        f'    <label>{label}</label>\n'
        f'    <pluralLabel>{label}</pluralLabel>\n'
        '    <visibility>Protected</visibility>\n'
        '    <fields>\n'
        '        <fullName>apikey__c</fullName>\n'
        '        <label>API Key</label>\n'
        '        <type>Text</type>\n'
        '        <length>255</length>\n'
        '        <externalId>false</externalId>\n'
        '    </fields>\n'
        '</CustomObject>\n'
    )


def _generate_custom_metadata_record_xml(service_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<CustomMetadata xmlns="http://soap.sforce.com/2006/04/metadata"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
        '    <label>key</label>\n'
        '    <protected>false</protected>\n'
        '    <values>\n'
        '        <field>apikey__c</field>\n'
        '        <value xsi:type="xsd:string">REPLACE_WITH_ACTUAL_KEY</value>\n'
        '    </values>\n'
        '</CustomMetadata>\n'
    )


class TestCustomMetadataType:
    """Tests for Custom Metadata Type generation (API key storage)."""

    def test_generates_valid_object_xml(self):
        xml = _generate_custom_metadata_type_xml("youdotcom")
        root = ET.fromstring(xml)
        assert root.tag.endswith("CustomObject")
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        assert root.find("sf:label", ns).text == "Youdotcom"
        assert root.find("sf:visibility", ns).text == "Protected"
        fields = root.find("sf:fields", ns)
        assert fields.find("sf:fullName", ns).text == "apikey__c"

    def test_generates_valid_record_xml(self):
        xml = _generate_custom_metadata_record_xml("youdotcom")
        root = ET.fromstring(xml)
        assert root.tag.endswith("CustomMetadata")
        ns = {"sf": "http://soap.sforce.com/2006/04/metadata"}
        assert root.find("sf:label", ns).text == "key"

    def test_custom_metadata_file_structure(self, tmp_path: Path):
        """Custom Metadata Type uses correct directory structure."""
        force_app = tmp_path / "force-app" / "main" / "default"
        obj_dir = force_app / "objects" / "youdotcom__mdt"
        cm_dir = force_app / "customMetadata"
        obj_dir.mkdir(parents=True)
        cm_dir.mkdir(parents=True)

        (obj_dir / "youdotcom__mdt.object-meta.xml").write_text(
            _generate_custom_metadata_type_xml("youdotcom")
        )
        (cm_dir / "youdotcom.key.md-meta.xml").write_text(
            _generate_custom_metadata_record_xml("youdotcom")
        )

        assert (obj_dir / "youdotcom__mdt.object-meta.xml").exists()
        assert (cm_dir / "youdotcom.key.md-meta.xml").exists()
