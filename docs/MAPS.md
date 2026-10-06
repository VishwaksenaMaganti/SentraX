# SentraX Map & Navigation Architecture

## 1. Google Maps Platform Integration
SentraX incorporates Google Maps Platform APIs for real-world navigation, routing, and autocomplete:
- **Routes API**: Polyline calculation and turn-by-turn navigation paths.
- **Maps JavaScript API**: Geospatial rendering and custom overlay styling.
- **Places API**: Destination search and autocompletion.

## 2. API Key Security
- **No Hardcoded Keys**: The Google API key is exclusively loaded through the `.env` environment variable `GOOGLE_MAPS_API_KEY`.
- **Zero Scraping Policy**: The platform never scrapes Google Maps web pages.
- **Automatic Offline Mock Route Provider**: If the user has not configured a Google Maps API key or when operating at an offline exhibition, the system seamlessly uses its built-in Mock Route Provider.

## 3. Route Segmentation Workflow
```
User searches destination
       ↓
Destination selected
       ↓
Calculate route polyline
       ↓
Segment route into corridor sections
       ↓
Query SentraX road-health & hazard database
       ↓
Assign segment health scores & color bands
       ↓
Render color-coded route with hazard markers
```

### Visual Color Coding
- **Green**: Good condition (85–100)
- **Yellow**: Moderate condition (65–84)
- **Orange**: Poor condition (40–64)
- **Red**: Critical hazard / collision zone (0–39)
