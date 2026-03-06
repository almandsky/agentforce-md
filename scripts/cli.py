"""CLI entry point for agentforce-md."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path


def _cli_name() -> str:
    """Return a user-friendly CLI invocation name for hint messages."""
    # When invoked via the wrapper script, PYTHONPATH is set to the install dir
    install_dir = os.environ.get("PYTHONPATH", "")
    if install_dir and "agentforce-md" in install_dir:
        return os.path.join(install_dir, "bin", "agentforce-md")
    return "python3 -m scripts.cli"

from .convert import convert
from .deploy.sf_cli import SfAgentCli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentforce-md",
        description="Convert Claude Code markdown to Agentforce Agent Script (.agent) files",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # convert command
    convert_parser = subparsers.add_parser("convert", help="Convert markdown to .agent file")
    convert_parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Root of the Claude Code project (default: current dir)",
    )
    convert_parser.add_argument(
        "--agent-name",
        required=True,
        help="Name for the generated agent",
    )
    convert_parser.add_argument(
        "--agent-type",
        choices=["AgentforceServiceAgent", "AgentforceEmployeeAgent"],
        default="AgentforceServiceAgent",
        help="Agent type (default: AgentforceServiceAgent)",
    )
    convert_parser.add_argument(
        "--default-agent-user",
        default="",
        help="Default agent user email",
    )
    convert_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: <project-root>/force-app/main/default)",
    )
    convert_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any tools are missing agentforce: target in their SKILL.md",
    )

    # deploy command — publish bundle + optional activate
    # `sf agent publish authoring-bundle` handles the full lifecycle:
    #   compile -> publish -> retrieve metadata -> deploy bundle
    deploy_parser = subparsers.add_parser(
        "deploy",
        help="Publish agent bundle to Salesforce org (compile + deploy + optional activate)",
    )
    deploy_parser.add_argument(
        "--api-name",
        required=True,
        help="Agent API/developer name (e.g. AcmeAgent)",
    )
    deploy_parser.add_argument("-o", "--target-org", required=True, help="Target Salesforce org")
    deploy_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the bundle only, don't publish",
    )
    deploy_parser.add_argument(
        "--activate",
        action="store_true",
        help="Also activate the agent after publishing",
    )
    deploy_parser.add_argument(
        "--skip-retrieve",
        action="store_true",
        help="Don't retrieve the generated metadata back to the DX project",
    )

    # preview command
    preview_parser = subparsers.add_parser("preview", help="Preview agent in Salesforce org")
    preview_parser.add_argument("--api-name", required=True, help="Agent API name")
    preview_parser.add_argument("-o", "--target-org", required=True, help="Target Salesforce org")
    preview_parser.add_argument(
        "--client-app",
        default="",
        help="Linked client app name (required by sf CLI)",
    )

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize from a template")
    init_parser.add_argument(
        "--template",
        choices=["hello-world", "multi-topic", "verification-gate"],
        default="hello-world",
        help="Template to use (default: hello-world)",
    )
    init_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Where to create the project (default: current dir)",
    )

    # setup command — query org for ASA user
    setup_parser = subparsers.add_parser(
        "setup",
        help="Query the org for Agent Service Account (ASA) users",
    )
    setup_parser.add_argument("-o", "--target-org", required=True, help="Target Salesforce org")

    # discover command — check org for SKILL.md targets
    discover_parser = subparsers.add_parser(
        "discover",
        help="Check which SKILL.md targets exist in the org",
    )
    discover_parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Root of the Claude Code project (default: current dir)",
    )
    discover_parser.add_argument("-o", "--target-org", required=True, help="Target Salesforce org")

    # scaffold command — generate metadata stubs for missing targets
    scaffold_parser = subparsers.add_parser(
        "scaffold",
        help="Generate metadata stubs (Flow XML, Apex classes) for missing SKILL.md targets",
    )
    scaffold_parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Root of the Claude Code project (default: current dir)",
    )
    scaffold_parser.add_argument("-o", "--target-org", required=True, help="Target Salesforce org")
    scaffold_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: force-app/main/default/)",
    )
    scaffold_parser.add_argument(
        "--skip-discover",
        action="store_true",
        help="Scaffold all targets without checking the org",
    )

    # run command — execute a SKILL.md action against a live org
    run_parser = subparsers.add_parser(
        "run",
        help="Execute a SKILL.md action against a live org",
    )
    run_parser.add_argument(
        "--skill",
        type=Path,
        required=True,
        help="Path to the SKILL.md file or skill directory",
    )
    run_parser.add_argument("-o", "--target-org", required=True, help="Target Salesforce org")
    run_parser.add_argument(
        "--input",
        type=str,
        default=None,
        help='Inputs as JSON string (e.g. \'{"order_id":"12345"}\')',
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be called without executing",
    )

    args = parser.parse_args(argv)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    handlers = {
        "convert": _cmd_convert,
        "deploy": _cmd_deploy,
        "preview": _cmd_preview,
        "init": _cmd_init,
        "setup": _cmd_setup,
        "discover": _cmd_discover,
        "scaffold": _cmd_scaffold,
        "run": _cmd_run,
    }
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    return 1


def _ensure_sfdx_project_json() -> None:
    """Write a minimal sfdx-project.json to the current directory if absent.

    The sf CLI walks up from CWD looking for sfdx-project.json to locate the
    project root.  Without it, 'sf agent validate/publish authoring-bundle'
    searches in the wrong directory and fails with "Cannot find an authoring
    bundle named '...' in the project."
    """
    sfdx_path = Path.cwd() / "sfdx-project.json"
    if sfdx_path.exists():
        return
    sfdx_content = {
        "packageDirectories": [{"path": "force-app/main/default", "default": True}],
        "namespace": "",
        "sfdcLoginUrl": "https://login.salesforce.com",
        "sourceApiVersion": "66.0",
    }
    sfdx_path.write_text(json.dumps(sfdx_content, indent=2) + "\n", encoding="utf-8")
    logging.info("Created %s", sfdx_path)


def _cmd_convert(args: argparse.Namespace) -> int:
    if args.agent_type == "AgentforceServiceAgent" and not args.default_agent_user:
        print(
            "Warning: --default-agent-user not set. Service agents require an ASA user.\n"
            f"  Run: {_cli_name()} setup -o <YourOrg>\n"
            "  to find available ASA users in your org.",
            file=sys.stderr,
        )

    try:
        bundle_dir = convert(
            project_root=args.project_root.resolve(),
            agent_name=args.agent_name,
            agent_type=args.agent_type,
            default_agent_user=args.default_agent_user,
            output_dir=args.output_dir.resolve() if args.output_dir else None,
            strict=args.strict,
        )
        print(f"Generated bundle: {bundle_dir}")
        print(f"  {bundle_dir.name}.agent")
        print(f"  {bundle_dir.name}.bundle-meta.xml")
        _ensure_sfdx_project_json()
        return 0
    except ValueError as e:
        logging.error("Validation error: %s", e)
        return 1
    except FileNotFoundError as e:
        logging.error("File not found: %s", e)
        return 1
    except OSError as e:
        logging.error("File system error: %s", e)
        return 1
    except Exception as e:
        logging.error("Unexpected error: %s", e)
        if args.verbose:
            logging.debug("Traceback:", exc_info=True)
        return 1


def _cmd_deploy(args: argparse.Namespace) -> int:
    """Publish an authoring bundle to the org.

    Uses `sf agent publish authoring-bundle` which handles the full lifecycle:
    compile -> publish -> retrieve metadata -> deploy bundle.
    """
    cli = SfAgentCli()

    if args.dry_run:
        # Validate only
        print(f"Validating bundle {args.api_name}...")
        result = cli.validate_bundle(args.api_name, args.target_org)
        if result.returncode != 0:
            print("Validation failed:", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            return 1
        print("Bundle validation passed.")
        return 0

    # Publish (compile + deploy)
    step = "[1/2]" if args.activate else "[1/1]"
    print(f"{step} Publishing bundle {args.api_name}...")
    result = cli.publish_bundle(
        args.api_name,
        args.target_org,
        skip_retrieve=args.skip_retrieve,
    )
    if result.returncode != 0:
        print("Publish failed:", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        return 1
    print("Bundle published — agent is now visible in the org.")

    # Optional: Activate
    if args.activate:
        print(f"[2/2] Activating {args.api_name}...")
        result = cli.activate(args.api_name, args.target_org)
        if result.returncode != 0:
            print(f"Activation failed:", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            return 1
        print("Agent is now active.")

    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    """Query the org for ASA users and display them."""
    cli = SfAgentCli()

    print(f"Querying {args.target_org} for Agent Service Account (ASA) users...")
    result = cli.query_asa_users(args.target_org)

    if result.returncode != 0:
        print("Query failed:", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        return 1

    try:
        data = json.loads(result.stdout)
        records = data.get("result", {}).get("records", [])
    except (json.JSONDecodeError, KeyError):
        print("Could not parse query results.", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        return 1

    if not records:
        print("No ASA users found in the org.")
        print("You may need to create one in Setup > Agent Service Accounts.")
        return 0

    print(f"\nFound {len(records)} ASA user(s):\n")
    print(f"  {'#':<4} {'Username':<55} {'Name'}")
    print(f"  {'─'*4} {'─'*55} {'─'*30}")
    for i, record in enumerate(records, 1):
        username = record.get("Username", "")
        name = record.get("Name", "")
        print(f"  {i:<4} {username:<55} {name}")

    print(f"\nUse the Username value with --default-agent-user when converting:")
    print(f'  {_cli_name()} convert --agent-name MyAgent \\')
    print(f'    --default-agent-user "{records[0].get("Username", "<username>")}"')

    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    cli = SfAgentCli()

    if not args.client_app:
        print(
            "Error: --client-app is required. Use a linked client app name.\n"
            'See: sf org login web --client-app <name>',
            file=sys.stderr,
        )
        return 1

    print(f"Starting preview for {args.api_name}...")
    result = cli.preview(args.api_name, args.target_org, client_app=args.client_app)
    if result.returncode != 0:
        print(f"Preview failed:\n{result.stderr}", file=sys.stderr)
        return 1
    print(result.stdout)
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    template_name = args.template
    templates_dir = Path(__file__).parent.parent / "templates" / template_name

    if not templates_dir.is_dir():
        print(f"Template '{template_name}' not found at {templates_dir}", file=sys.stderr)
        return 1

    dest = args.output_dir.resolve()

    # Copy template files
    for src_file in templates_dir.rglob("*"):
        if src_file.is_file():
            rel = src_file.relative_to(templates_dir)
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst)
            print(f"  Created {rel}")

    print(f"\nInitialized '{template_name}' template in {dest}")
    print("Next steps:")
    print("  1. Edit CLAUDE.md with your agent instructions")
    print("  2. Edit .claude/agents/*.md for your topics")
    print(f"  3. Run: {_cli_name()} convert --agent-name YourAgent")
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    """Check which SKILL.md targets exist in the org."""
    from .discover import discover

    print(f"Discovering targets in {args.target_org}...")
    report = discover(
        project_root=args.project_root.resolve(),
        target_org=args.target_org,
    )

    if not report.targets:
        print("No SKILL.md files with agentforce targets found.")
        return 0

    # Print results table
    print(f"\n  {'Skill':<30} {'Target':<40} {'Status'}")
    print(f"  {'─'*30} {'─'*40} {'─'*10}")
    for t in report.targets:
        status = "found" if t.found else "MISSING"
        print(f"  {t.skill_name:<30} {t.target:<40} {status}")

    found_count = len(report.found)
    missing_count = len(report.missing)
    print(f"\n  {found_count} found, {missing_count} missing")

    if report.missing:
        print("\n  To generate stubs for missing targets, run:")
        print(f"    {_cli_name()} scaffold --project-root {args.project_root} -o {args.target_org}")
        return 1

    print("\n  All targets found in the org.")
    return 0


def _cmd_scaffold(args: argparse.Namespace) -> int:
    """Generate metadata stubs for missing SKILL.md targets."""
    from .scaffold import scaffold_all, scaffold_from_skills

    project_root = args.project_root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else None

    if args.skip_discover:
        print("Scaffolding all targets (skipping org check)...")
        result = scaffold_all(project_root, output_dir)
    else:
        print(f"Discovering targets in {args.target_org}...")
        result = scaffold_from_skills(project_root, args.target_org, output_dir)

    if not result.files_created and not result.warnings:
        print("No stubs to generate — all targets exist or no SKILL.md targets found.")
        return 0

    if result.files_created:
        print(f"\nCreated {len(result.files_created)} file(s):")
        for f in result.files_created:
            print(f"  {f}")

    for warning in result.warnings:
        print(f"  Warning: {warning}", file=sys.stderr)

    print("\nNext steps:")
    print("  1. Review and fill in business logic in the generated stubs")
    print("  2. Deploy: sf project deploy start --source-dir force-app/main/default -o <org>")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute a SKILL.md action against a live org."""
    from .local_run import run_action

    # Resolve skill path
    skill_path = args.skill.resolve()
    if skill_path.is_dir():
        skill_path = skill_path / "SKILL.md"
    if not skill_path.exists():
        print(f"SKILL.md not found at {skill_path}", file=sys.stderr)
        return 1

    # Parse inputs
    inputs = {}
    if args.input:
        try:
            inputs = json.loads(args.input)
        except json.JSONDecodeError:
            print("Error: --input must be valid JSON", file=sys.stderr)
            return 1

    if args.dry_run:
        print("Dry run — showing invocation plan:")

    result = run_action(
        skill_path=skill_path,
        target_org=args.target_org,
        inputs=inputs,
        dry_run=args.dry_run,
    )

    if not result.success:
        print(f"Action failed: {result.error}", file=sys.stderr)
        if result.raw_response:
            print(f"Response: {result.raw_response}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(result.raw_response)
    else:
        print("Action succeeded.")
        if result.outputs:
            print("\nOutputs:")
            for key, value in result.outputs.items():
                print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
