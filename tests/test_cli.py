"""Tests for the CLI entry point."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.cli import main


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class TestConvertCommand:
    def test_convert_hello_world(self, tmp_path: Path):
        rc = main([
            "convert",
            "--project-root", str(TEMPLATES_DIR / "hello-world"),
            "--agent-name", "TestAgent",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        assert (tmp_path / "aiAuthoringBundles" / "TestAgent" / "TestAgent.agent").exists()

    def test_convert_with_agent_type(self, tmp_path: Path):
        rc = main([
            "convert",
            "--project-root", str(TEMPLATES_DIR / "hello-world"),
            "--agent-name", "EmpAgent",
            "--agent-type", "AgentforceEmployeeAgent",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        content = (tmp_path / "aiAuthoringBundles" / "EmpAgent" / "EmpAgent.agent").read_text()
        assert "AgentforceEmployeeAgent" in content

    def test_convert_with_default_agent_user(self, tmp_path: Path):
        rc = main([
            "convert",
            "--project-root", str(TEMPLATES_DIR / "hello-world"),
            "--agent-name", "UserAgent",
            "--default-agent-user", "bot@acme.com",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        content = (tmp_path / "aiAuthoringBundles" / "UserAgent" / "UserAgent.agent").read_text()
        assert 'default_agent_user: "bot@acme.com"' in content

    def test_convert_invalid_project_root(self, tmp_path: Path):
        rc = main([
            "convert",
            "--project-root", str(tmp_path / "nonexistent"),
            "--agent-name", "Bad",
            "--output-dir", str(tmp_path),
        ])
        # Should succeed even with no input files (empty agent)
        assert rc == 0


class TestInitCommand:
    def test_init_hello_world(self, tmp_path: Path):
        rc = main([
            "init",
            "--template", "hello-world",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / ".claude" / "agents" / "greeter.md").exists()

    def test_init_multi_topic(self, tmp_path: Path):
        rc = main([
            "init",
            "--template", "multi-topic",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / ".claude" / "agents" / "order-support.md").exists()
        assert (tmp_path / ".claude" / "agents" / "general-faq.md").exists()

    def test_init_verification_gate(self, tmp_path: Path):
        rc = main([
            "init",
            "--template", "verification-gate",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
        assert (tmp_path / ".claude" / "agents" / "identity-verification.md").exists()
        assert (tmp_path / ".claude" / "agents" / "account-management.md").exists()
        assert (tmp_path / ".claude" / "agents" / "escalation.md").exists()


class TestDeployCommand:
    def test_deploy_publish(self):
        """Publish bundle (no activate)."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(returncode=0, stdout="{}", stderr="")

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg"])
            assert rc == 0
            instance.publish_bundle.assert_called_once_with(
                "MyAgent", "TestOrg", skip_retrieve=False,
            )

    def test_deploy_dry_run(self):
        """Dry run: validate only."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.validate_bundle.return_value = MagicMock(returncode=0, stdout="{}", stderr="")

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg", "--dry-run"])
            assert rc == 0
            instance.validate_bundle.assert_called_once_with("MyAgent", "TestOrg")
            instance.publish_bundle.assert_not_called()

    def test_deploy_with_activate(self):
        """Publish + activate."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
            instance.activate.return_value = MagicMock(returncode=0, stdout="", stderr="")

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg", "--activate"])
            assert rc == 0
            instance.activate.assert_called_once_with("MyAgent", "TestOrg")

    def test_deploy_publish_failure(self):
        """Publish fails."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(
                returncode=1, stdout="", stderr="Publish error"
            )

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg"])
            assert rc == 1

    def test_deploy_activate_failure(self):
        """Publish succeeds but activate fails."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
            instance.activate.return_value = MagicMock(
                returncode=1, stdout="", stderr="Activate error"
            )

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg", "--activate"])
            assert rc == 1

    def test_deploy_skip_retrieve(self):
        """Skip retrieving metadata back."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(returncode=0, stdout="{}", stderr="")

            rc = main([
                "deploy", "--api-name", "MyAgent", "-o", "TestOrg", "--skip-retrieve",
            ])
            assert rc == 0
            instance.publish_bundle.assert_called_once_with(
                "MyAgent", "TestOrg", skip_retrieve=True,
            )

    def test_deploy_validation_failure(self):
        """Dry run validation fails."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.validate_bundle.return_value = MagicMock(
                returncode=1, stdout='{"error":"bad"}', stderr=""
            )

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg", "--dry-run"])
            assert rc == 1

    def test_deploy_cosmetic_retrieve_failure(self, capsys):
        """Returncode=1 but JSON status=0 is a cosmetic error — should succeed."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(
                returncode=1,
                stdout=json.dumps({"status": 0, "message": "Metadata retrieval failed"}),
                stderr="Warning: retrieve step failed",
            )

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg"])
            assert rc == 0
            captured = capsys.readouterr()
            assert "Bundle published" in captured.out
            assert "cosmetic" in captured.err

    def test_deploy_real_failure_with_json_status(self, capsys):
        """Returncode=1 with JSON status=1 is a real failure."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(
                returncode=1,
                stdout=json.dumps({"status": 1, "message": "Compile error"}),
                stderr="Error",
            )

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg"])
            assert rc == 1

    def test_deploy_failure_unparseable_json(self):
        """Returncode=1 with non-JSON stdout is treated as failure."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.publish_bundle.return_value = MagicMock(
                returncode=1,
                stdout="not json at all",
                stderr="Error",
            )

            rc = main(["deploy", "--api-name", "MyAgent", "-o", "TestOrg"])
            assert rc == 1


class TestPreviewCommand:
    def test_preview_success(self):
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.preview.return_value = MagicMock(returncode=0, stdout="{}", stderr="")

            rc = main([
                "preview", "--api-name", "MyAgent", "-o", "TestOrg",
                "--client-app", "my-app",
            ])
            assert rc == 0
            instance.preview.assert_called_once_with("MyAgent", "TestOrg", client_app="my-app")

    def test_preview_missing_client_app(self):
        rc = main(["preview", "--api-name", "MyAgent", "-o", "TestOrg"])
        assert rc == 1

    def test_preview_failure(self):
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.preview.return_value = MagicMock(returncode=1, stdout="", stderr="Failed")

            rc = main([
                "preview", "--api-name", "MyAgent", "-o", "TestOrg",
                "--client-app", "app",
            ])
            assert rc == 1


class TestSetupCommand:
    def test_setup_displays_asa_users(self):
        """Setup lists ASA users from the org."""
        query_result = json.dumps({
            "result": {
                "records": [
                    {"Username": "agent@org.ext", "Name": "Agent User"},
                    {"Username": "bot@org.ext", "Name": "Bot User"},
                ]
            }
        })
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.query_asa_users.return_value = MagicMock(
                returncode=0, stdout=query_result, stderr=""
            )

            rc = main(["setup", "-o", "TestOrg"])
            assert rc == 0
            instance.query_asa_users.assert_called_once_with("TestOrg")

    def test_setup_no_users_found(self):
        """Setup with no ASA users."""
        query_result = json.dumps({"result": {"records": []}})
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.query_asa_users.return_value = MagicMock(
                returncode=0, stdout=query_result, stderr=""
            )

            rc = main(["setup", "-o", "TestOrg"])
            assert rc == 0

    def test_setup_query_failure(self):
        """Setup fails when query fails."""
        with patch("scripts.cli.SfAgentCli") as MockCli:
            instance = MockCli.return_value
            instance.query_asa_users.return_value = MagicMock(
                returncode=1, stdout="", stderr="Auth error"
            )

            rc = main(["setup", "-o", "TestOrg"])
            assert rc == 1


class TestConvertWarning:
    def test_warns_missing_asa_for_service_agent(self, tmp_path: Path, capsys):
        """Service agent without --default-agent-user prints warning."""
        main([
            "convert",
            "--project-root", str(TEMPLATES_DIR / "hello-world"),
            "--agent-name", "WarnAgent",
            "--output-dir", str(tmp_path),
        ])
        captured = capsys.readouterr()
        assert "--default-agent-user not set" in captured.err

    def test_no_warning_for_employee_agent(self, tmp_path: Path, capsys):
        """Employee agent without --default-agent-user does NOT warn."""
        main([
            "convert",
            "--project-root", str(TEMPLATES_DIR / "hello-world"),
            "--agent-name", "EmpAgent",
            "--agent-type", "AgentforceEmployeeAgent",
            "--output-dir", str(tmp_path),
        ])
        captured = capsys.readouterr()
        assert "--default-agent-user not set" not in captured.err

    def test_no_warning_when_asa_provided(self, tmp_path: Path, capsys):
        """No warning when --default-agent-user is provided."""
        main([
            "convert",
            "--project-root", str(TEMPLATES_DIR / "hello-world"),
            "--agent-name", "GoodAgent",
            "--default-agent-user", "bot@org.ext",
            "--output-dir", str(tmp_path),
        ])
        captured = capsys.readouterr()
        assert "--default-agent-user not set" not in captured.err


class TestConvertErrorHandling:
    def test_strict_mode_returns_error_code(self, tmp_path: Path):
        """Strict mode with unresolved actions returns exit code 1."""
        rc = main([
            "convert",
            "--project-root", str(TEMPLATES_DIR / "verification-gate"),
            "--agent-name", "StrictAgent",
            "--output-dir", str(tmp_path),
            "--strict",
        ])
        assert rc == 1

    def test_validation_error_returns_error_code(self, tmp_path: Path):
        """Duplicate topic names cause a validation error."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "CLAUDE.md").write_text("Test agent.")
        agents_dir = project / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "orders.md").write_text(
            "---\nname: orders\ndescription: Orders\n---\nHandle orders."
        )
        (agents_dir / "orders-v2.md").write_text(
            "---\nname: orders\ndescription: Orders v2\n---\nHandle orders v2."
        )

        rc = main([
            "convert",
            "--project-root", str(project),
            "--agent-name", "DupAgent",
            "--output-dir", str(tmp_path / "out"),
        ])
        assert rc == 1


class TestVerboseFlag:
    def test_verbose_does_not_crash(self, tmp_path: Path):
        rc = main([
            "-v", "convert",
            "--project-root", str(TEMPLATES_DIR / "hello-world"),
            "--agent-name", "VerboseAgent",
            "--output-dir", str(tmp_path),
        ])
        assert rc == 0
