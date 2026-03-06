"""Wrapper around `sf` CLI commands for agent deployment.

Deployment lifecycle for Agent Script (.agent) bundles:
  1. deploy_metadata()   — deploys the AiAuthoringBundle to the org
  2. validate_bundle()   — validates the .agent file (optional but recommended)
  3. publish_bundle()    — compiles the bundle into BotDefinition/BotVersion/GenAiPlannerBundle
  4. activate()          — activates the agent

Steps 2-3 require `sf agent validate/publish authoring-bundle` (CLI >= 2.123.1).
Step 1 alone only puts raw metadata in the org — it does NOT create a usable agent.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass
class CliResult:
    returncode: int
    stdout: str
    stderr: str


class SfAgentCli:
    """Wraps the Salesforce CLI commands for deploying agents.

    Supports the full agent deployment lifecycle:
    1. deploy_metadata:  `sf project deploy start` (deploys AiAuthoringBundle)
    2. validate_bundle:  `sf agent validate authoring-bundle` (validates .agent)
    3. publish_bundle:   `sf agent publish authoring-bundle` (compiles to BotDefinition)
    4. activate:         `sf agent activate` (activates the agent)

    Also supports: create_from_spec, deactivate, preview.
    """

    def __init__(self, sf_binary: str = "sf"):
        self.sf_binary = sf_binary

    def deploy_metadata(
        self,
        source_dir: str,
        target_org: str,
        dry_run: bool = False,
    ) -> CliResult:
        """Deploy metadata (including aiAuthoringBundles) via `sf project deploy start`.

        This deploys the raw AiAuthoringBundle to the org but does NOT create
        a usable agent. You must call publish_bundle() afterwards to compile
        the bundle into a BotDefinition.

        Args:
            source_dir: Path to the directory containing the metadata
                        (e.g. force-app/main/default).
            target_org: Target org username or alias.
            dry_run: If True, validate only without saving to the org.
        """
        cmd = [
            self.sf_binary, "project", "deploy", "start",
            "--source-dir", source_dir,
            "-o", target_org,
            "--json",
        ]
        if dry_run:
            cmd.append("--dry-run")
        return self._run(cmd)

    def validate_bundle(
        self,
        api_name: str,
        target_org: str,
    ) -> CliResult:
        """Validate an authoring bundle via `sf agent validate authoring-bundle`.

        Requires SF CLI >= 2.123.1. Validates that the .agent file is
        syntactically and semantically correct before publishing.

        Args:
            api_name: The agent API/developer name (e.g. AcmeAgent).
            target_org: Target org username or alias.
        """
        return self._run([
            self.sf_binary, "agent", "validate", "authoring-bundle",
            "--api-name", api_name,
            "-o", target_org,
            "--json",
        ])

    def publish_bundle(
        self,
        api_name: str,
        target_org: str,
        skip_retrieve: bool = False,
    ) -> CliResult:
        """Publish (compile) an authoring bundle via `sf agent publish authoring-bundle`.

        This handles the full lifecycle: compile the Agent Script, publish to
        the org (creating Bot/BotVersion/GenAiPlannerBundle/GenAiPlugin/GenAiFunction),
        retrieve the generated metadata back, and deploy the authoring bundle.

        Args:
            api_name: The agent API/developer name (e.g. AcmeAgent).
            target_org: Target org username or alias.
            skip_retrieve: Don't retrieve the generated metadata back to the DX project.
        """
        cmd = [
            self.sf_binary, "agent", "publish", "authoring-bundle",
            "--api-name", api_name,
            "-o", target_org,
            "--json",
        ]
        if skip_retrieve:
            cmd.append("--skip-retrieve")
        return self._run(cmd)

    def create_from_spec(
        self,
        name: str,
        spec_path: str,
        target_org: str,
        api_name: str | None = None,
        preview: bool = False,
    ) -> CliResult:
        """Create an agent from a YAML spec file via `sf agent create`.

        Args:
            name: Agent display name (label).
            spec_path: Path to the agent spec YAML file.
            target_org: Target org username or alias.
            api_name: Optional API name (derived from name if omitted).
            preview: If True, preview without saving.
        """
        cmd = [
            self.sf_binary, "agent", "create",
            "--name", name,
            "--spec", spec_path,
            "-o", target_org,
            "--json",
        ]
        if api_name:
            cmd.extend(["--api-name", api_name])
        if preview:
            cmd.append("--preview")
        return self._run(cmd)

    def query_asa_users(self, target_org: str) -> CliResult:
        """Query the org for Agent Service Account (ASA) users.

        ASA users have the 'Einstein Agent User' profile and 'Einstein Agent' license.
        """
        query = (
            "SELECT Id, Username, Name FROM User "
            "WHERE IsActive = true AND Profile.Name = 'Einstein Agent User' "
            "ORDER BY CreatedDate DESC"
        )
        return self._run([
            self.sf_binary, "data", "query",
            "-q", query,
            "-o", target_org,
            "--json",
        ])

    def activate(self, api_name: str, target_org: str) -> CliResult:
        """Activate an agent."""
        return self._run([
            self.sf_binary, "agent", "activate",
            "--api-name", api_name,
            "-o", target_org,
        ])

    def deactivate(self, api_name: str, target_org: str) -> CliResult:
        """Deactivate an agent."""
        return self._run([
            self.sf_binary, "agent", "deactivate",
            "--api-name", api_name,
            "-o", target_org,
        ])

    def preview(
        self,
        api_name: str,
        target_org: str,
        client_app: str = "",
    ) -> CliResult:
        """Start an interactive agent preview session.

        Note: This launches an interactive terminal session. The --client-app
        flag is required by the CLI and must reference a previously linked app.
        """
        cmd = [
            self.sf_binary, "agent", "preview",
            "--api-name", api_name,
            "-o", target_org,
        ]
        if client_app:
            cmd.extend(["--client-app", client_app])
        return self._run(cmd)

    def list_metadata(
        self,
        metadata_type: str,
        target_org: str,
    ) -> CliResult:
        """List metadata components of a given type (Flow, ApexClass, etc.).

        Args:
            metadata_type: Salesforce metadata type name (e.g. Flow, ApexClass).
            target_org: Target org username or alias.
        """
        return self._run([
            self.sf_binary, "org", "list", "metadata",
            "-m", metadata_type,
            "-o", target_org,
            "--json",
        ])

    def query_soql(self, query: str, target_org: str) -> CliResult:
        """Run a SOQL query against the org.

        Args:
            query: SOQL query string.
            target_org: Target org username or alias.
        """
        return self._run([
            self.sf_binary, "data", "query",
            "-q", query,
            "-o", target_org,
            "--json",
        ])

    def run_flow(
        self,
        flow_api_name: str,
        inputs: dict,
        target_org: str,
    ) -> CliResult:
        """Invoke a flow via REST API.

        Args:
            flow_api_name: The flow's API name.
            inputs: Dictionary of input variable names to values.
            target_org: Target org username or alias.
        """
        body = json.dumps({"inputs": [inputs]})
        return self._run([
            self.sf_binary, "api", "request", "rest",
            f"/services/data/v66.0/actions/custom/flow/{flow_api_name}",
            "--method", "POST",
            "--body", body,
            "-o", target_org,
        ])

    def run_apex_action(
        self,
        class_name: str,
        inputs: dict,
        target_org: str,
    ) -> CliResult:
        """Invoke an @InvocableMethod via REST API.

        Args:
            class_name: The Apex class name containing the @InvocableMethod.
            inputs: Dictionary of input variable names to values.
            target_org: Target org username or alias.
        """
        body = json.dumps({"inputs": [inputs]})
        return self._run([
            self.sf_binary, "api", "request", "rest",
            f"/services/data/v66.0/actions/custom/apex/{class_name}",
            "--method", "POST",
            "--body", body,
            "-o", target_org,
        ])

    def _run(self, cmd: list[str]) -> CliResult:
        """Execute a CLI command and return the result."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return CliResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except FileNotFoundError:
            return CliResult(
                returncode=1,
                stdout="",
                stderr=f"'{self.sf_binary}' not found. Install the Salesforce CLI: https://developer.salesforce.com/tools/salesforcecli",
            )
        except subprocess.TimeoutExpired:
            return CliResult(
                returncode=1,
                stdout="",
                stderr="Command timed out after 300 seconds.",
            )
