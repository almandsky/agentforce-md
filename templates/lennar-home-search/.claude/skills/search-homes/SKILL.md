---
name: SearchHomesAction
description: Search for available Lennar homes by location, price range, and home type
agentforce:
  target: "apex://SearchHomesAction"
  sobject: "Property__c"
  inputs:
    state:
      type: string
      description: "US state abbreviation (e.g. FL, TX, CA)"
      required: true
    city:
      type: string
      description: "City name"
      required: false
    min_price:
      type: string
      description: "Minimum price as string (e.g. 300000)"
      required: false
    max_price:
      type: string
      description: "Maximum price as string (e.g. 600000)"
      required: false
    bedrooms:
      type: string
      description: "Minimum number of bedrooms as string (e.g. 3)"
      required: false
    home_type:
      type: string
      description: "Home type: single-family, townhome, active-adult, next-gen"
      required: false
  outputs:
    results_json:
      type: string
      description: "JSON array of matching homes with community, price, beds, baths, sqft"
    total_count:
      type: string
      description: "Total number of matching results"
---
Search the Lennar homes API for available properties.
Use this when the buyer has provided location preferences.
The API returns community listings with pricing and specs.

```bash
curl -X GET "https://api.lennar.com/v1/homes/search?state=FL&city=Tampa&minPrice=300000&maxPrice=600000&bedrooms=3&homeType=single-family" \
  -H "Authorization: Bearer $LENNAR_API_KEY" \
  -H "Content-Type: application/json"
```
