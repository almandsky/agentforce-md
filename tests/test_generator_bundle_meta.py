"""Tests for bundle-meta.xml generation."""

from scripts.generator.bundle_meta import generate_bundle_meta


def test_returns_valid_xml():
    xml = generate_bundle_meta()
    assert '<?xml version="1.0" encoding="UTF-8"?>' in xml


def test_contains_bundle_type():
    xml = generate_bundle_meta()
    assert "<bundleType>AGENT</bundleType>" in xml


def test_contains_namespace():
    xml = generate_bundle_meta()
    assert 'xmlns="http://soap.sforce.com/2006/04/metadata"' in xml


def test_is_deterministic():
    assert generate_bundle_meta() == generate_bundle_meta()
