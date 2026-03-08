---
name: ScheduleTourAction
description: Schedule a tour at a Lennar community welcome center
agentforce:
  target: "apex://ScheduleTourAction"
  inputs:
    community_name:
      type: string
      description: "Name of the Lennar community to visit"
      required: true
    preferred_date:
      type: string
      description: "Preferred tour date in YYYY-MM-DD format"
      required: true
    buyer_name:
      type: string
      description: "Full name of the prospective buyer"
      required: true
    buyer_email:
      type: string
      description: "Buyer's email address"
      required: true
    buyer_phone:
      type: string
      description: "Buyer's phone number"
      required: false
  outputs:
    confirmation_id:
      type: string
      description: "Tour confirmation ID"
    scheduled_datetime:
      type: string
      description: "Confirmed date and time of the tour"
    welcome_center_address:
      type: string
      description: "Address of the welcome center"
---
Schedule a tour at a Lennar community welcome center.
Collect buyer info and preferred date, then call the scheduling API.

```bash
curl -X POST "https://api.lennar.com/v1/tours/schedule" \
  -H "Authorization: Bearer $LENNAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"community":"Riverview Meadows","date":"2026-03-15","name":"Jane Doe","email":"jane@example.com","phone":"555-0123"}'
```
