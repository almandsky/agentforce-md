---
name: SearchKnowledge
description: Search the company knowledge base for answers to customer questions
agentforce:
  target: "retriever://Acme_Knowledge_Base"
  inputs:
    query:
      type: string
      description: "The search query"
      required: true
  outputs:
    answer:
      type: string
      description: "The answer found in the knowledge base"
---
Use this to find answers from the Acme Corp knowledge base.
If no relevant answer is found, offer to connect the customer with a specialist.
