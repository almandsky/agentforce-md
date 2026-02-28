"""Write generated Agent Script files to disk."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_bundle(
    output_dir: Path,
    agent_name: str,
    agent_content: str,
    bundle_meta_content: str,
) -> Path:
    """Write the .agent and bundle-meta.xml files to the output directory.

    Creates:
        <output_dir>/aiAuthoringBundles/<agent_name>/
            <agent_name>.agent
            <agent_name>.bundle-meta.xml

    Returns the path to the bundle directory.
    """
    bundle_dir = output_dir / "aiAuthoringBundles" / agent_name
    bundle_dir.mkdir(parents=True, exist_ok=True)

    agent_file = bundle_dir / f"{agent_name}.agent"
    agent_file.write_text(agent_content, encoding="utf-8")
    logger.info("Wrote %s", agent_file)

    meta_file = bundle_dir / f"{agent_name}.bundle-meta.xml"
    meta_file.write_text(bundle_meta_content, encoding="utf-8")
    logger.info("Wrote %s", meta_file)

    return bundle_dir
