"""
CIRO — GeoGemma Service
=========================
Uses Google Gemini Vision (GeoGemma) to analyze satellite imagery
for flood detection, water body expansion, and urban inundation.

GeoGemma = Gemini's geospatial understanding capability.
We feed it Sentinel-2 imagery (RGB + NDWI maps) and get structured
flood analysis back.

Requires: GOOGLE_API_KEY in environment (Gemini API key).
"""
import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from config.settings import settings

logger = logging.getLogger("ciro.geogemma")

# Gemini API configuration
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = settings.DEBATE_LLM_MODEL


class GeoGemmaAnalysis:
    """Structured result from GeoGemma analysis."""

    def __init__(self, raw: Dict[str, Any]):
        self.flood_detected: bool = raw.get("flood_detected", False)
        self.water_expansion_percent: float = raw.get("water_expansion_percent", 0.0)
        self.affected_area_description: str = raw.get("affected_area_description", "")
        self.estimated_flood_extent_km2: float = raw.get("estimated_flood_extent_km2", 0.0)
        self.confidence: float = raw.get("confidence", 0.0)
        self.risk_factors: List[str] = raw.get("risk_factors", [])
        self.severity: int = raw.get("severity", 1)
        self.recommendations: List[str] = raw.get("recommendations", [])
        self.land_use_changes: str = raw.get("land_use_changes", "")
        self.vegetation_stress: str = raw.get("vegetation_stress", "")
        self.raw = raw

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flood_detected": self.flood_detected,
            "water_expansion_percent": self.water_expansion_percent,
            "affected_area_description": self.affected_area_description,
            "estimated_flood_extent_km2": self.estimated_flood_extent_km2,
            "confidence": self.confidence,
            "risk_factors": self.risk_factors,
            "severity": self.severity,
            "recommendations": self.recommendations,
            "land_use_changes": self.land_use_changes,
            "vegetation_stress": self.vegetation_stress,
        }


class GeoGemmaService:
    """
    GeoGemma (Gemini Vision) service for satellite image interpretation.
    
    Capabilities:
      - Analyze before/after satellite image pairs for flood detection
      - Assess NDWI change maps for water body expansion
      - Provide natural-language flood extent descriptions
      - Estimate affected areas and severity
      - Generate risk factor analysis and recommendations
    """

    def __init__(self):
        self._api_key = os.getenv("GOOGLE_API_KEY", "")
        self._model = GEMINI_MODEL
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_available(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def analyze_satellite_imagery(
        self,
        zone: Dict[str, Any],
        current_image_url: Optional[str] = None,
        baseline_image_url: Optional[str] = None,
        ndwi_data: Optional[Dict] = None,
        change_data: Optional[Dict] = None,
    ) -> GeoGemmaAnalysis:
        """
        Analyze satellite imagery for a zone using Gemini Vision.
        
        Can work with:
          1. Image URLs (preferred — sends actual satellite images)
          2. Numeric data only (fallback — sends NDWI/change metrics for text analysis)
        
        Returns:
            GeoGemmaAnalysis with structured flood assessment
        """
        if not self.is_available:
            logger.warning("Gemini API key not configured — using rule-based fallback")
            return self._rule_based_analysis(zone, ndwi_data, change_data)

        try:
            # Build the prompt
            parts = self._build_analysis_parts(
                zone, current_image_url, baseline_image_url, ndwi_data, change_data
            )
            
            # Call Gemini
            response = await self._call_gemini(parts)
            
            # Parse structured response
            analysis = self._parse_response(response)
            logger.info(
                f"GeoGemma analysis for {zone['id']}: "
                f"flood={'YES' if analysis.flood_detected else 'no'}, "
                f"severity={analysis.severity}, confidence={analysis.confidence:.2f}"
            )
            return analysis

        except Exception as e:
            logger.error(f"GeoGemma analysis failed for {zone['id']}: {e}")
            return self._rule_based_analysis(zone, ndwi_data, change_data)

    def _build_analysis_parts(
        self,
        zone: Dict,
        current_url: Optional[str],
        baseline_url: Optional[str],
        ndwi_data: Optional[Dict],
        change_data: Optional[Dict],
    ) -> List[Dict]:
        """Build Gemini API request parts (text + images)."""
        parts = []

        # System context
        context = f"""You are a geospatial flood analyst specializing in Pakistan's urban crisis zones.

Zone: {zone.get('name', zone['id'])}
Province: {zone.get('province', 'Unknown')}
Coordinates: {zone['lat']:.4f}°N, {zone['lng']:.4f}°E
Elevation: {zone.get('elevation_m', 'N/A')}m
Drainage Capacity: {zone.get('drainage_capacity', 'N/A')} (0=poor, 1=excellent)
Population Density: {zone.get('population_density', 'N/A')} per km²
Analysis Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""

        if ndwi_data:
            context += f"""
Satellite Measurements:
  - Current NDWI: {ndwi_data.get('current_ndwi', 'N/A')}
  - Baseline NDWI: {ndwi_data.get('baseline_ndwi', 'N/A')}
  - NDWI Delta: {ndwi_data.get('ndwi_delta', 'N/A')} (positive = more water)
  - Water Expansion Detected: {ndwi_data.get('water_expansion_detected', False)}
"""

        if change_data:
            context += f"""
Change Detection Results:
  - Flood Signal Strength: {change_data.get('flood_signal_strength', 0.0)}
  - Water Fraction: {change_data.get('water_fraction', 'N/A')}
  - Water Area: {change_data.get('water_area_km2', 'N/A')} km²
"""

        parts.append({"text": context})

        # Add images if available
        if current_url:
            parts.append({
                "text": "Current satellite image (most recent Sentinel-2 capture):"
            })
            parts.append({"image_url": current_url})

        if baseline_url:
            parts.append({
                "text": "Baseline satellite image (30 days prior):"
            })
            parts.append({"image_url": baseline_url})

        # Analysis prompt
        prompt = """Based on the above satellite data and imagery, provide a flood risk analysis.

Respond ONLY with valid JSON (no markdown, no code fences):
{
  "flood_detected": true/false,
  "water_expansion_percent": 0-100 (estimated % increase in water pixels),
  "affected_area_description": "Brief description of affected areas",
  "estimated_flood_extent_km2": float (estimated flooded area),
  "confidence": 0.0-1.0 (your confidence in this assessment),
  "risk_factors": ["list", "of", "contributing", "factors"],
  "severity": 1-10 (1=minimal, 10=catastrophic),
  "recommendations": ["list", "of", "actionable", "recommendations"],
  "land_use_changes": "Description of any land use changes observed",
  "vegetation_stress": "Description of vegetation health (NDVI-related)"
}

Consider Pakistan-specific factors:
- Monsoon season (Jul-Sep) dramatically increases flood risk
- Poor urban drainage in most cities
- River proximity (Indus, Chenab, Jhelum systems)
- Flash flood vulnerability in KPK and Balochistan
- Coastal flooding risk in Karachi
"""
        parts.append({"text": prompt})

        return parts

    async def _call_gemini(self, parts: List[Dict]) -> str:
        """Call Gemini API with text and optional image parts."""
        client = await self._get_client()

        url = f"{GEMINI_API_BASE}/models/{self._model}:generateContent"

        # Build content parts for Gemini API format
        api_parts = []
        for part in parts:
            if "text" in part:
                api_parts.append({"text": part["text"]})
            elif "image_url" in part:
                # Fetch image and encode as base64
                try:
                    img_response = await client.get(part["image_url"])
                    if img_response.status_code == 200:
                        img_b64 = base64.b64encode(img_response.content).decode()
                        api_parts.append({
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": img_b64
                            }
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch image: {e}")
                    api_parts.append({"text": "[Image unavailable]"})

        payload = {
            "contents": [{"parts": api_parts}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json",
            }
        }

        response = await client.post(
            url,
            params={"key": self._api_key},
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code != 200:
            raise Exception(f"Gemini API error {response.status_code}: {response.text[:500]}")

        data = response.json()
        
        # Extract text from response
        candidates = data.get("candidates", [])
        if not candidates:
            raise Exception("No candidates in Gemini response")

        content = candidates[0].get("content", {})
        text_parts = content.get("parts", [])
        
        return "".join(p.get("text", "") for p in text_parts)

    def _parse_response(self, response_text: str) -> GeoGemmaAnalysis:
        """Parse Gemini's JSON response into structured analysis."""
        try:
            # Try direct JSON parse
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Last resort: find first { ... }
                brace_match = re.search(r'\{[\s\S]*\}', response_text)
                if brace_match:
                    data = json.loads(brace_match.group(0))
                else:
                    logger.error(f"Cannot parse GeoGemma response: {response_text[:200]}")
                    data = {"flood_detected": False, "confidence": 0.0, "severity": 1}

        return GeoGemmaAnalysis(data)

    def _rule_based_analysis(
        self,
        zone: Dict,
        ndwi_data: Optional[Dict],
        change_data: Optional[Dict]
    ) -> GeoGemmaAnalysis:
        """
        Fallback rule-based analysis when Gemini is unavailable.
        Uses NDWI delta and zone characteristics.
        """
        ndwi_delta = 0.0
        if ndwi_data:
            ndwi_delta = ndwi_data.get("ndwi_delta", 0.0)
        elif change_data:
            ndwi_delta = change_data.get("ndwi_delta", 0.0)

        # Determine flood detection
        flood_detected = ndwi_delta > 0.05
        
        # Severity based on delta magnitude and zone vulnerability
        drainage = zone.get("drainage_capacity", 0.5)
        severity = 1
        if ndwi_delta > 0.20:
            severity = 9
        elif ndwi_delta > 0.15:
            severity = 7
        elif ndwi_delta > 0.10:
            severity = 5
        elif ndwi_delta > 0.05:
            severity = 3

        # Poor drainage amplifies severity
        if drainage < 0.4:
            severity = min(10, severity + 2)

        # Estimate flood extent
        aoi_km2 = 78.5  # π * 5² km
        water_expansion = max(0, ndwi_delta * 200)  # rough %
        flood_extent = aoi_km2 * (water_expansion / 100.0) * 0.3  # 30% of expansion is actual flood

        risk_factors = []
        if ndwi_delta > 0.05:
            risk_factors.append("Water body expansion detected")
        if drainage < 0.4:
            risk_factors.append(f"Poor drainage capacity ({drainage})")
        if zone.get("elevation_m", 500) < 100:
            risk_factors.append("Low elevation (flood plain)")
        
        month = datetime.utcnow().month
        if month in (7, 8, 9):
            risk_factors.append("Active monsoon season")
            severity = min(10, severity + 1)

        return GeoGemmaAnalysis({
            "flood_detected": flood_detected,
            "water_expansion_percent": round(water_expansion, 1),
            "affected_area_description": f"{'Significant' if flood_detected else 'Minimal'} water changes in {zone.get('name', zone['id'])}",
            "estimated_flood_extent_km2": round(flood_extent, 2),
            "confidence": 0.50,  # Lower confidence for rule-based
            "risk_factors": risk_factors if risk_factors else ["No significant risk factors"],
            "severity": severity,
            "recommendations": self._generate_recommendations(severity, zone),
            "land_use_changes": "Unable to assess without imagery",
            "vegetation_stress": "Unable to assess without imagery",
        })

    def _generate_recommendations(self, severity: int, zone: Dict) -> List[str]:
        """Generate zone-appropriate recommendations based on severity."""
        recs = []
        if severity >= 7:
            recs.extend([
                "URGENT: Issue flood warning for affected areas",
                "Activate emergency evacuation routes",
                f"Alert NDMA and {zone.get('province', '')} PDMA",
            ])
        elif severity >= 4:
            recs.extend([
                "Monitor water levels closely (hourly updates)",
                "Pre-position relief supplies",
                "Issue advisory to low-lying area residents",
            ])
        else:
            recs.extend([
                "Continue routine monitoring",
                "No immediate action required",
            ])
        return recs

    async def analyze_with_context(
        self,
        zone: Dict,
        weather_data: Optional[Dict] = None,
        satellite_data: Optional[Dict] = None,
    ) -> GeoGemmaAnalysis:
        """
        Enhanced analysis combining satellite + weather context.
        Provides more accurate predictions by correlating rainfall with water expansion.
        """
        # Merge all available data
        ndwi_data = satellite_data or {}
        
        # Add weather context to the analysis
        if weather_data:
            if "current_ndwi" not in ndwi_data:
                ndwi_data["current_ndwi"] = 0.0
            ndwi_data["recent_rainfall_mm"] = weather_data.get("rain_mm", 0)
            ndwi_data["temperature_c"] = weather_data.get("temp_c", 30)
            ndwi_data["humidity_pct"] = weather_data.get("humidity", 50)

        return await self.analyze_satellite_imagery(
            zone=zone,
            current_image_url=ndwi_data.get("current_image_url"),
            baseline_image_url=ndwi_data.get("baseline_image_url"),
            ndwi_data=ndwi_data,
            change_data=satellite_data,
        )

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton
_geogemma_service: Optional[GeoGemmaService] = None


def get_geogemma_service() -> GeoGemmaService:
    """Get or create the GeoGemma service singleton."""
    global _geogemma_service
    if _geogemma_service is None:
        _geogemma_service = GeoGemmaService()
    return _geogemma_service
