"""CLI entry point for agentforce-md."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

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
    }
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    return 1


def _cmd_convert(args: argparse.Namespace) -> int:
    if args.agent_type == "AgentforceServiceAgent" and not args.default_agent_user:
        print(
            "Warning: --default-agent-user not set. Service agents require an ASA user.\n"
            "  Run: python3 -m scripts.cli setup -o <YourOrg>\n"
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
        )
        print(f"Generated bundle: {bundle_dir}")
        print(f"  {bundle_dir.name}.agent")
        print(f"  {bundle_dir.name}.bundle-meta.xml")
        return 0
    except Exception as e:
        logging.error("Conversion failed: %s", e)
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
    print(f'  python3 -m scripts.cli convert --agent-name MyAgent \\')
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
    print("  3. Run: agentforce-md convert --agent-name YourAgent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
