"""Tests for the deployment wrapper (mocked)."""

from unittest.mock import MagicMock, patch

from scripts.deploy.sf_cli import CliResult, SfAgentCli


def test_deploy_metadata_command():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = cli.deploy_metadata("force-app/main/default", "TestOrg")
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert "project" in cmd
        assert "deploy" in cmd
        assert "start" in cmd
        assert "--source-dir" in cmd


def test_deploy_metadata_dry_run():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = cli.deploy_metadata("src", "TestOrg", dry_run=True)
        cmd = mock_run.call_args[0][0]
        assert "--dry-run" in cmd


def test_create_from_spec_command():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = cli.create_from_spec("My Agent", "spec.yaml", "TestOrg", api_name="My_Agent")
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert "agent" in cmd
        assert "create" in cmd
        assert "--name" in cmd
        assert "--spec" in cmd
        assert "--api-name" in cmd


def test_create_from_spec_preview():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        cli.create_from_spec("Agent", "spec.yaml", "Org", preview=True)
        cmd = mock_run.call_args[0][0]
        assert "--preview" in cmd


def test_validate_bundle_command():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = cli.validate_bundle("MyAgent", "TestOrg")
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert "agent" in cmd
        assert "validate" in cmd
        assert "authoring-bundle" in cmd
        assert "--api-name" in cmd
        assert "MyAgent" in cmd


def test_publish_bundle_command():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = cli.publish_bundle("MyAgent", "TestOrg")
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert "agent" in cmd
        assert "publish" in cmd
        assert "authoring-bundle" in cmd
        assert "--api-name" in cmd
        assert "MyAgent" in cmd


def test_publish_bundle_skip_retrieve():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        cli.publish_bundle("MyAgent", "TestOrg", skip_retrieve=True)
        cmd = mock_run.call_args[0][0]
        assert "--skip-retrieve" in cmd


def test_query_asa_users():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = cli.query_asa_users("TestOrg")
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert "data" in cmd
        assert "query" in cmd
        assert "Einstein Agent User" in " ".join(cmd)


def test_activate_command():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = cli.activate("MyAgent", "TestOrg")
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert "activate" in cmd


def test_deactivate_command():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = cli.deactivate("MyAgent", "TestOrg")
        cmd = mock_run.call_args[0][0]
        assert "deactivate" in cmd


def test_preview_command():
    cli = SfAgentCli()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        result = cli.preview("MyAgent", "TestOrg", client_app="my-app")
        cmd = mock_run.call_args[0][0]
        assert "preview" in cmd
        assert "--client-app" in cmd
        assert "my-app" in cmd


def test_sf_not_found():
    cli = SfAgentCli(sf_binary="nonexistent-sf")
    result = cli.deploy_metadata("src", "TestOrg")
    assert result.returncode == 1
    assert "not found" in result.stderr
