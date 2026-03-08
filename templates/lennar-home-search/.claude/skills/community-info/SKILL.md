---
name: CommunityInfoAction
description: Answer general questions about Lennar communities, home features, and the buying process
agentforce:
  target: "flow://Get_Community_Info"
  inputs:
    query:
      type: string
      description: "The buyer's question about Lennar communities or home features"
      required: true
  outputs:
    answer:
      type: string
      description: "Answer from the Lennar knowledge base"
---
Use this to answer general questions about Lennar.
Topics include: Everything's Included program, Wi-Fi CERTIFIED homes, energy efficiency,
floor plan options, community amenities, and the new home buying process.
If the buyer asks about specific pricing or availability, redirect to the home search action.
