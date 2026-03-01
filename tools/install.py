#!/usr/bin/env python3
"""
agentforce-md Installer for Claude Code

Usage:
    curl -sSL https://raw.githubusercontent.com/almandsky/agentforce-md/main/tools/install.py | python3

    # Or with options:
    python3 install.py                # Install
    python3 install.py --update       # Check for updates and apply if available
    python3 install.py --force-update # Force reinstall even if up-to-date
    python3 install.py --uninstall    # Remove agentforce-md
    python3 install.py --status       # Show installation status
    python3 install.py --dry-run      # Preview changes without writing
    python3 install.py --force        # Skip confirmations

Requirements:
    - Python 3.10+ (standard library only)
    - Claude Code installed (~/.claude/ directory exists)
"""

import argparse
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

INSTALLER_VERSION = "0.1.0"

# GitHub repository
GITHUB_OWNER = "almandsky"
GITHUB_REPO = "agentforce-md"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main"

# Installation paths
CLAUDE_DIR = Path.home() / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
INSTALL_DIR = CLAUDE_DIR / "agentforce-md"
META_FILE = CLAUDE_DIR / ".agentforce-md.json"
INSTALLER_DEST = CLAUDE_DIR / "agentforce-md-install.py"

# Skill prefix (only manage our own skills, never touch sf-* skills)
SKILL_PREFIX = "agentforce-"

# ============================================================================
# OUTPUT HELPERS
# ============================================================================

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"


def print_step(msg: str):
    print(f"\n{c('▸', Colors.BLUE)} {c(msg, Colors.BOLD)}")


def print_substep(msg: str):
    print(f"  {c('✓', Colors.GREEN)} {msg}")


def print_info(msg: str):
    print(f"  {c('ℹ', Colors.BLUE)} {msg}")


def print_warn(msg: str):
    print(f"  {c('⚠', Colors.YELLOW)} {msg}")


def print_error(msg: str):
    print(f"  {c('✗', Colors.RED)} {msg}")


# ============================================================================
# FILESYSTEM HELPERS
# ============================================================================

def safe_rmtree(path):
    """Remove a directory tree, handling symlinks safely."""
    p = Path(path)
    if p.is_symlink():
        p.unlink()
    elif p.exists():
        shutil.rmtree(p)


def _find_python3() -> str:
    """Find the python3 executable path reliably.

    sys.executable can be empty or wrong when piped via curl | python3.
    Falls back to searching PATH.
    """
    exe = sys.executable
    if exe and os.path.isfile(exe):
        return exe

    # Fallback: search PATH
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, "python3")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # Last resort
    return "python3"


# ============================================================================
# SSL HELPERS
# ============================================================================

_SSL_CONTEXT_CACHE: Optional[ssl.SSLContext] = None
_SSL_ERROR_SHOWN = False


def _build_ssl_context() -> ssl.SSLContext:
    """Build best available SSL context for urllib."""
    cert_file = os.environ.get("SSL_CERT_FILE")
    if cert_file and os.path.isfile(cert_file):
        return ssl.create_default_context(cafile=cert_file)

    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    return ssl.create_default_context()


def _get_ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT_CACHE
    if _SSL_CONTEXT_CACHE is None:
        _SSL_CONTEXT_CACHE = _build_ssl_context()
    return _SSL_CONTEXT_CACHE


def _handle_ssl_error(e: Exception) -> bool:
    global _SSL_ERROR_SHOWN
    is_ssl = False
    if isinstance(e, urllib.error.URLError) and hasattr(e, "reason"):
        if isinstance(e.reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
            is_ssl = True
    elif isinstance(e, (ssl.SSLCertVerificationError, ssl.SSLError)):
        is_ssl = True

    if is_ssl and not _SSL_ERROR_SHOWN:
        _SSL_ERROR_SHOWN = True
        print()
        print_error("SSL certificate verification failed")
        print_info("This is common with python.org installs on macOS.")
        print()
        print(c("  Fix options (try in order):", Colors.BOLD))
        print()
        print("  1. Run the macOS certificate installer:")
        print("     /Applications/Python\\ 3.*/Install\\ Certificates.command")
        print()
        print("  2. Install certifi and set SSL_CERT_FILE:")
        print("     pip3 install certifi")
        print('     export SSL_CERT_FILE="$(python3 -c \'import certifi; print(certifi.where())\')"')
        print()

    return is_ssl


# ============================================================================
# METADATA
# ============================================================================

def write_metadata(version: str, skills: List[str], commit_sha: Optional[str] = None):
    """Write install metadata to ~/.claude/.agentforce-md.json."""
    META_FILE.write_text(json.dumps({
        "method": "unified",
        "version": version,
        "commit_sha": commit_sha,
        "installed_at": datetime.now().isoformat(),
        "installer_version": INSTALLER_VERSION,
        "install_dir": str(INSTALL_DIR),
        "skills": skills,
    }, indent=2) + "\n")


def read_metadata() -> Optional[Dict[str, Any]]:
    """Read install metadata."""
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return None
    return None


# ============================================================================
# DOWNLOAD & VERSION
# ============================================================================

def download_repo_zip(target_dir: Path, ref: str = "main") -> bool:
    """Download repo zip from GitHub and extract to target_dir."""
    zip_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{ref}.zip"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            print_info(f"Downloading from {zip_url}...")
            with urllib.request.urlopen(zip_url, timeout=60, context=_get_ssl_context()) as resp:
                tmp_file.write(resp.read())

        with zipfile.ZipFile(tmp_path, "r") as zf:
            # GitHub zips contain a top-level directory like "agentforce-md-main/"
            top_dirs = {name.split("/")[0] for name in zf.namelist() if "/" in name}
            if len(top_dirs) != 1:
                print_error("Unexpected zip structure")
                return False
            top_dir = top_dirs.pop()

            # Extract to a temp location, then move contents
            with tempfile.TemporaryDirectory() as extract_tmp:
                zf.extractall(extract_tmp)
                extracted = Path(extract_tmp) / top_dir

                # Clear target and move
                safe_rmtree(target_dir)
                shutil.copytree(extracted, target_dir)

        return True

    except (urllib.error.URLError, zipfile.BadZipFile, IOError) as e:
        if not _handle_ssl_error(e):
            print_error(f"Download failed: {e}")
        return False
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def fetch_remote_version(ref: str = "main") -> Optional[str]:
    """Fetch the VERSION file from the remote repo."""
    url = f"{GITHUB_RAW_URL}/VERSION"
    try:
        with urllib.request.urlopen(url, timeout=15, context=_get_ssl_context()) as resp:
            return resp.read().decode().strip()
    except (urllib.error.URLError, IOError) as e:
        if not _handle_ssl_error(e):
            print_error(f"Failed to check remote version: {e}")
        return None


def fetch_remote_commit_sha(ref: str = "main") -> Optional[str]:
    """Fetch the latest commit SHA from the GitHub API."""
    url = f"{GITHUB_API_URL}/commits/{ref}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=15, context=_get_ssl_context()) as resp:
            data = json.loads(resp.read().decode())
            return data.get("sha", "")[:12]
    except (urllib.error.URLError, IOError, json.JSONDecodeError, KeyError):
        return None


def get_local_commit_sha(repo_root: Path) -> Optional[str]:
    """Get the current commit SHA from a local git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


# ============================================================================
# VENV MANAGEMENT
# ============================================================================

def create_venv(install_dir: Path, dry_run: bool = False) -> bool:
    """Create a bundled venv with pyyaml inside the install directory."""
    venv_dir = install_dir / ".venv"

    if dry_run:
        print_info(f"Would create venv at {venv_dir}")
        print_info("Would install pyyaml into venv")
        return True

    python_exe = _find_python3()

    # Create venv
    print_info("Creating virtual environment...")
    try:
        subprocess.run(
            [python_exe, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create venv: {e.stderr}")
        return False

    # Install pyyaml
    pip = venv_dir / "bin" / "pip3"
    if not pip.exists():
        pip = venv_dir / "bin" / "pip"
    if not pip.exists():
        print_error("pip not found in created venv")
        return False

    print_info("Installing pyyaml...")
    try:
        subprocess.run(
            [str(pip), "install", "pyyaml"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install pyyaml: {e.stderr}")
        return False

    return True


# ============================================================================
# SKILL INSTALLATION
# ============================================================================

def copy_skills(source_dir: Path, dry_run: bool = False) -> List[str]:
    """Copy .claude/skills/agentforce-*/ to ~/.claude/skills/agentforce-*/."""
    skills_src = source_dir / ".claude" / "skills"
    installed = []

    if not skills_src.exists():
        print_warn("No .claude/skills/ directory found in repo")
        return installed

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    for skill_dir in sorted(skills_src.iterdir()):
        if not skill_dir.is_dir() or not skill_dir.name.startswith(SKILL_PREFIX):
            continue

        target = SKILLS_DIR / skill_dir.name
        if dry_run:
            print_info(f"Would install skill: {skill_dir.name}")
        else:
            safe_rmtree(target)
            shutil.copytree(skill_dir, target)
            print_substep(f"Installed skill: {skill_dir.name}")

        installed.append(skill_dir.name)

    return installed


def prune_orphan_skills(current_skills: List[str], dry_run: bool = False) -> int:
    """Remove agentforce-* skills that are no longer in the repo."""
    pruned = 0
    if not SKILLS_DIR.exists():
        return pruned

    current_set = set(current_skills)
    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and item.name.startswith(SKILL_PREFIX) and item.name not in current_set:
            if dry_run:
                print_info(f"Would remove orphan skill: {item.name}")
            else:
                safe_rmtree(item)
                print_substep(f"Removed orphan skill: {item.name}")
            pruned += 1

    return pruned


def remove_skills(dry_run: bool = False) -> int:
    """Remove all installed agentforce-* skills from ~/.claude/skills/."""
    removed = 0
    if not SKILLS_DIR.exists():
        return removed

    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and item.name.startswith(SKILL_PREFIX):
            if dry_run:
                print_info(f"Would remove skill: {item.name}")
            else:
                safe_rmtree(item)
                print_substep(f"Removed skill: {item.name}")
            removed += 1

    return removed


# ============================================================================
# VALIDATION
# ============================================================================

def validate_installation() -> List[str]:
    """Validate that installation completed correctly. Returns list of issues."""
    issues = []

    # Check install dir
    if not INSTALL_DIR.exists():
        issues.append(f"Install directory missing: {INSTALL_DIR}")
        return issues  # Nothing else to check

    # Check wrapper script
    wrapper = INSTALL_DIR / "bin" / "agentforce-md"
    if not wrapper.exists():
        issues.append(f"CLI wrapper missing: {wrapper}")
    elif not os.access(wrapper, os.X_OK):
        issues.append(f"CLI wrapper not executable: {wrapper}")

    # Check venv
    venv_python = INSTALL_DIR / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        issues.append(f"Venv python missing: {venv_python}")

    # Check that pyyaml is importable in the venv
    if venv_python.exists():
        try:
            result = subprocess.run(
                [str(venv_python), "-c", "import yaml"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                issues.append("pyyaml not importable in venv")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            issues.append("Could not verify pyyaml in venv")

    # Check skills
    if SKILLS_DIR.exists():
        found_skills = [
            d.name for d in sorted(SKILLS_DIR.iterdir())
            if d.is_dir() and d.name.startswith(SKILL_PREFIX)
        ]
        for skill_name in found_skills:
            skill_md = SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_md.exists():
                issues.append(f"SKILL.md missing in installed skill: {skill_name}")
    else:
        issues.append(f"Skills directory missing: {SKILLS_DIR}")

    # Check metadata
    if not META_FILE.exists():
        issues.append(f"Metadata file missing: {META_FILE}")

    return issues


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_install(dry_run: bool = False, force: bool = False,
                called_from_bash: bool = False) -> int:
    """Install agentforce-md to ~/.claude/agentforce-md/."""
    if not called_from_bash:
        print(f"\n{c('agentforce-md installer', Colors.BOLD)}")

    # Check prerequisites
    if not CLAUDE_DIR.exists():
        print_error(f"Claude Code directory not found: {CLAUDE_DIR}")
        print_info("Install Claude Code first: https://docs.anthropic.com/en/docs/claude-code")
        return 1

    # Check existing installation
    meta = read_metadata()
    if meta and not force:
        version = meta.get("version", "unknown")
        print_info(f"agentforce-md v{version} is already installed.")
        print_info("Use --force to reinstall, or --update to check for updates.")
        return 0

    # Detect local clone vs remote install
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    local_version_file = repo_root / "VERSION"
    commit_sha = None

    if local_version_file.exists():
        # Installing from local clone
        print_step("Installing from local clone")
        version = local_version_file.read_text().strip()
        commit_sha = get_local_commit_sha(repo_root)

        if dry_run:
            print_info(f"Would install v{version} from {repo_root}")
            print_info(f"Would copy repo to {INSTALL_DIR}")
            create_venv(INSTALL_DIR, dry_run=True)
            skills = copy_skills(repo_root, dry_run=True)
            print_info(f"Would copy installer to {INSTALLER_DEST}")
            print_info(f"Would write metadata to {META_FILE}")
            print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
            return 0

        print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))

        # Copy repo to install dir
        print_step("Copying repo to install directory")
        safe_rmtree(INSTALL_DIR)
        shutil.copytree(repo_root, INSTALL_DIR, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", ".venv", "force-app",
        ))
        print_substep(f"Copied to {INSTALL_DIR}")

    else:
        # Remote install (curl | python3)
        print_step("Downloading agentforce-md")
        version_str = fetch_remote_version()
        if not version_str:
            print_error("Could not determine remote version")
            return 1
        version = version_str
        commit_sha = fetch_remote_commit_sha()

        if dry_run:
            print_info(f"Would install v{version} from GitHub")
            print_info(f"Would download repo to {INSTALL_DIR}")
            create_venv(INSTALL_DIR, dry_run=True)
            print_info(f"Would install skills to {SKILLS_DIR}")
            print_info(f"Would copy installer to {INSTALLER_DEST}")
            print_info(f"Would write metadata to {META_FILE}")
            print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
            return 0

        print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))

        if not download_repo_zip(INSTALL_DIR):
            return 1
        print_substep(f"Extracted to {INSTALL_DIR}")

    # Create venv
    print_step("Setting up Python environment")
    if not create_venv(INSTALL_DIR):
        return 1
    print_substep("Virtual environment ready with pyyaml")

    # Make wrapper executable
    print_step("Configuring CLI wrapper")
    wrapper = INSTALL_DIR / "bin" / "agentforce-md"
    if wrapper.exists():
        wrapper.chmod(0o755)
        print_substep(f"Wrapper script: {wrapper}")
    else:
        print_warn(f"Wrapper script not found at {wrapper}")

    # Copy skills + prune orphans
    print_step("Installing skills")
    skills = copy_skills(INSTALL_DIR)
    if skills:
        print_substep(f"{len(skills)} skill(s) installed")
    else:
        print_warn("No skills found to install")

    pruned = prune_orphan_skills(skills)
    if pruned:
        print_substep(f"{pruned} orphan skill(s) removed")

    # Copy installer for self-update
    print_step("Setting up self-updater")
    installer_src = INSTALL_DIR / "tools" / "install.py"
    if installer_src.exists():
        shutil.copy2(installer_src, INSTALLER_DEST)
        print_substep(f"Installer copied to {INSTALLER_DEST}")
    else:
        print_warn("Installer source not found; self-update won't work")

    # Write metadata
    write_metadata(version, skills, commit_sha=commit_sha)
    print_substep(f"Metadata written to {META_FILE}")

    # Post-install validation
    print_step("Validating installation")
    issues = validate_installation()
    if issues:
        for issue in issues:
            print_warn(issue)
        print_warn("Installation completed with warnings")
    else:
        print_substep("All checks passed")

    # Summary
    print(f"\n{c('Installation complete!', Colors.GREEN)}")
    print()
    print(f"  Version:  {version}" + (f" ({commit_sha})" if commit_sha else ""))
    print(f"  CLI:      {INSTALL_DIR / 'bin' / 'agentforce-md'}")
    print(f"  Skills:   {', '.join(skills) if skills else 'none'}")
    print()
    print(f"  Update:   python3 {INSTALLER_DEST} --update")
    print(f"  Status:   python3 {INSTALLER_DEST} --status")
    print(f"  Remove:   python3 {INSTALLER_DEST} --uninstall")
    print()

    return 0


def cmd_update(dry_run: bool = False, force_update: bool = False) -> int:
    """Check for updates and apply if available."""
    print(f"\n{c('agentforce-md updater', Colors.BOLD)}")

    meta = read_metadata()
    if not meta:
        print_info("agentforce-md is not installed. Running install...")
        return cmd_install(dry_run=dry_run)

    local_version = meta.get("version", "unknown")
    local_sha = meta.get("commit_sha")
    print_info(f"Installed version: {local_version}" + (f" ({local_sha})" if local_sha else ""))

    # Fetch remote version + commit SHA
    print_step("Checking for updates")
    remote_version = fetch_remote_version()
    if not remote_version:
        print_error("Could not check remote version")
        return 1

    remote_sha = fetch_remote_commit_sha()
    print_info(f"Remote version: {remote_version}" + (f" ({remote_sha})" if remote_sha else ""))

    # Detect changes: version bump OR content change (same version, different SHA)
    version_changed = remote_version != local_version
    content_changed = (
        remote_sha and local_sha
        and remote_sha != local_sha
        and not version_changed
    )

    if not version_changed and not content_changed and not force_update:
        print(f"\n{c('Already up to date.', Colors.GREEN)}")
        return 0

    if force_update:
        print_info("Force update requested")
    elif version_changed:
        print_info(f"Version update available: {local_version} -> {remote_version}")
    elif content_changed:
        print_info(f"Content update available: {local_sha} -> {remote_sha}")

    # Reinstall
    return cmd_install(dry_run=dry_run, force=True)


def cmd_uninstall(dry_run: bool = False, force: bool = False) -> int:
    """Remove agentforce-md installation."""
    print(f"\n{c('agentforce-md uninstaller', Colors.BOLD)}")

    meta = read_metadata()
    if not meta and not INSTALL_DIR.exists():
        print_info("agentforce-md is not installed.")
        return 0

    if not force:
        print()
        print("  This will remove:")
        print(f"    - {INSTALL_DIR}")
        print(f"    - {SKILLS_DIR}/agentforce-* skills")
        print(f"    - {META_FILE}")
        print(f"    - {INSTALLER_DEST}")
        print()
        try:
            answer = input("  Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if answer not in ("y", "yes"):
            print_info("Cancelled.")
            return 0

    # Remove install dir
    if INSTALL_DIR.exists():
        if dry_run:
            print_info(f"Would remove {INSTALL_DIR}")
        else:
            safe_rmtree(INSTALL_DIR)
            print_substep(f"Removed {INSTALL_DIR}")

    # Remove skills
    removed = remove_skills(dry_run=dry_run)
    if removed:
        print_substep(f"Removed {removed} skill(s)")

    # Remove metadata
    if META_FILE.exists():
        if dry_run:
            print_info(f"Would remove {META_FILE}")
        else:
            META_FILE.unlink()
            print_substep(f"Removed {META_FILE}")

    # Remove self-updater (but not if we're running from it)
    if INSTALLER_DEST.exists():
        running_from_dest = Path(__file__).resolve() == INSTALLER_DEST.resolve()
        if dry_run:
            print_info(f"Would remove {INSTALLER_DEST}")
        elif not running_from_dest:
            INSTALLER_DEST.unlink()
            print_substep(f"Removed {INSTALLER_DEST}")
        else:
            print_info(f"Skipping removal of running installer: {INSTALLER_DEST}")
            print_info("You can delete it manually.")

    if dry_run:
        print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
    else:
        print(f"\n{c('Uninstall complete.', Colors.GREEN)}")

    return 0


def cmd_status() -> int:
    """Show installation status."""
    print(f"\n{c('agentforce-md status', Colors.BOLD)}")

    meta = read_metadata()
    if not meta:
        print_info("agentforce-md is not installed.")
        return 1

    commit_sha = meta.get("commit_sha")
    print()
    print(f"  Version:      {meta.get('version', 'unknown')}" +
          (f" ({commit_sha})" if commit_sha else ""))
    print(f"  Installed at: {meta.get('installed_at', 'unknown')}")
    print(f"  Install dir:  {INSTALL_DIR}")
    print(f"  Metadata:     {META_FILE}")

    # Check CLI wrapper
    wrapper = INSTALL_DIR / "bin" / "agentforce-md"
    wrapper_ok = wrapper.exists() and os.access(wrapper, os.X_OK)
    print(f"  CLI wrapper:  {wrapper} {'(ok)' if wrapper_ok else '(MISSING)'}")

    # Check venv
    venv_python = INSTALL_DIR / ".venv" / "bin" / "python3"
    venv_ok = venv_python.exists()
    print(f"  Venv:         {INSTALL_DIR / '.venv'} {'(ok)' if venv_ok else '(MISSING)'}")

    # List installed skills
    print()
    print(f"  {c('Installed skills:', Colors.BOLD)}")
    if SKILLS_DIR.exists():
        found = False
        for item in sorted(SKILLS_DIR.iterdir()):
            if item.is_dir() and item.name.startswith(SKILL_PREFIX):
                skill_md = item / "SKILL.md"
                status = "ok" if skill_md.exists() else "MISSING SKILL.md"
                print(f"    - {item.name} ({status})")
                found = True
        if not found:
            print("    (none)")
    else:
        print("    (skills directory not found)")

    # Check for sf-skills coexistence
    sf_meta = CLAUDE_DIR / ".sf-skills.json"
    if sf_meta.exists():
        print()
        print_info("sf-skills is also installed (no conflicts expected)")

    print()
    return 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="agentforce-md installer for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--update", action="store_true",
                        help="Check for updates and apply if available")
    parser.add_argument("--force-update", action="store_true",
                        help="Force reinstall even if up-to-date")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove agentforce-md")
    parser.add_argument("--status", action="store_true",
                        help="Show installation status")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    parser.add_argument("--force", action="store_true",
                        help="Skip confirmations")
    parser.add_argument("--called-from-bash", action="store_true",
                        help=argparse.SUPPRESS)  # Internal: set by install.sh

    args = parser.parse_args()

    if args.status:
        sys.exit(cmd_status())
    elif args.uninstall:
        sys.exit(cmd_uninstall(dry_run=args.dry_run, force=args.force))
    elif args.update or args.force_update:
        sys.exit(cmd_update(dry_run=args.dry_run, force_update=args.force_update))
    else:
        sys.exit(cmd_install(dry_run=args.dry_run, force=args.force,
                             called_from_bash=args.called_from_bash))


if __name__ == "__main__":
    main()
