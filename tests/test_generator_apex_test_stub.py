"""Tests for the Apex test class generator."""

from __future__ import annotations

from scripts.generator.apex_test_stub import generate_apex_test_class
from scripts.ir.models import ActionInput, ActionOutput


def test_minimal_test_class():
    """Generates a valid @isTest class with no inputs/outputs."""
    result = generate_apex_test_class("MyAction")

    assert "@isTest" in result
    assert "private class MyActionTest" in result
    assert "MyAction.Request req = new MyAction.Request();" in result
    assert "MyAction.invoke(requests)" in result
    assert "System.assertNotEquals(null, responses" in result


def test_test_class_with_inputs():
    """Placeholder values are set for each input type."""
    inputs = [
        ActionInput(name="order_number", input_type="string", description="Order num"),
        ActionInput(name="quantity", input_type="number", description="Qty"),
        ActionInput(name="is_active", input_type="boolean"),
    ]
    result = generate_apex_test_class("OrderAction", inputs=inputs)

    assert "req.order_number = 'test';" in result
    assert "req.quantity = 1;" in result
    assert "req.is_active = true;" in result


def test_test_class_with_outputs():
    """Asserts are generated for each output field."""
    outputs = [
        ActionOutput(name="status", output_type="string", description="Order status"),
        ActionOutput(name="total", output_type="number", description="Total amount"),
    ]
    result = generate_apex_test_class("OrderAction", outputs=outputs)

    assert "responses[0].status" in result
    assert "responses[0].total" in result
    assert "should not be null" in result


def test_test_class_http_mock():
    """Test class includes HttpCalloutMock inner class."""
    result = generate_apex_test_class("MyAction")

    assert "MockHttpResponse implements HttpCalloutMock" in result
    assert "res.setStatusCode(200)" in result
    assert "res.setBody('{}')" in result
    assert "Test.setMock(HttpCalloutMock.class, new MockHttpResponse())" in result


def test_test_class_name_convention():
    """Test class name follows {ClassName}Test convention."""
    result = generate_apex_test_class("GetOrderStatus")

    assert "private class GetOrderStatusTest" in result
    # Should reference the original class, not the test class
    assert "GetOrderStatus.Request" in result
    assert "GetOrderStatus.Response" in result
    assert "GetOrderStatus.invoke" in result
