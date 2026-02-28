---
name: CheckOrderStatus
description: Look up the current status of a customer order by order number
agentforce:
  target: "flow://Get_Order_Status"
  inputs:
    order_number:
      type: string
      description: "The customer's order number"
      required: true
  outputs:
    order_status:
      type: string
      description: "Current status of the order"
    order_date:
      type: string
      description: "Date the order was placed"
---
Use this to check the status of a customer order.
Ask the customer for their order number before calling this action.
