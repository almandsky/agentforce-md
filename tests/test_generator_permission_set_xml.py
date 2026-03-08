"""Tests for the Permission Set XML generator."""

from __future__ import annotations

from scripts.generator.permission_set_xml import generate_permission_set_xml


def test_single_class():
    """One classAccesses entry for a single Apex class."""
    result = generate_permission_set_xml("MyAgent_Action_Access", ["MyAction"])

    assert "<apexClass>MyAction</apexClass>" in result
    assert "<enabled>true</enabled>" in result
    assert result.count("<classAccesses>") == 1


def test_multiple_classes():
    """Multiple classAccesses entries for multiple Apex classes."""
    classes = ["OrderAction", "OrderActionTest", "ReturnAction", "ReturnActionTest"]
    result = generate_permission_set_xml("Agent_Access", classes)

    assert result.count("<classAccesses>") == 4
    for cls in classes:
        assert f"<apexClass>{cls}</apexClass>" in result


def test_permission_set_label():
    """Label matches the permission set name."""
    result = generate_permission_set_xml("MyAgent_Action_Access", ["Foo"])

    assert "<label>MyAgent_Action_Access</label>" in result


def test_xml_structure():
    """Valid XML structure with namespace."""
    result = generate_permission_set_xml("Test_Access", ["A", "B"])

    assert '<?xml version="1.0" encoding="UTF-8"?>' in result
    assert '<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">' in result
    assert result.strip().endswith("</PermissionSet>")
