---
name: ProcessReturn
description: Process a return request for a customer order
agentforce:
  target: "flow://Process_Order_Return"
  inputs:
    order_number:
      type: string
      description: "The order number to return"
      required: true
    reason:
      type: string
      description: "Reason for the return"
      required: true
  outputs:
    return_id:
      type: string
      description: "The generated return case ID"
    return_status:
      type: string
      description: "Status of the return request"
---
Use this to process a return for a customer.
Confirm the order number and return reason with the customer before calling.
