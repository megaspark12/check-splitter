"""
AI-powered Receipt Recognition Service using Google Gemini.

Uses Gemini's vision capabilities to extract structured data from receipt images.
"""
import io
import json
import base64
from typing import List, Dict, Any, Optional
from decimal import Decimal
from PIL import Image

from app.config import get_settings


class ReceiptItem:
    """Represents a parsed item from a receipt."""
    
    def __init__(
        self,
        name: str,
        price: Decimal,
        quantity: int = 1,
        is_tax: bool = False,
        is_tip_suggestion: bool = False,
    ):
        self.name = name
        self.price = price
        self.quantity = quantity
        self.is_tax = is_tax
        self.is_tip_suggestion = is_tip_suggestion


class GeminiReceiptParser:
    """
    Uses Google Gemini to parse receipts with vision AI.
    
    This replaces traditional OCR + regex parsing with a single
    AI call that understands receipt structure directly.
    """
    
    RECEIPT_PROMPT = """Analyze this receipt image and extract all items with their prices.

Return a JSON object with this exact structure:
{
    "items": [
        {
            "name": "Item name (cleaned up, human readable)",
            "price": 12.99,
            "quantity": 1,
            "is_tax": false,
            "is_tip_suggestion": false
        }
    ],
    "currency": "USD or ILS or EUR etc",
    "subtotal": 0.00,
    "tax": 0.00,
    "total": 0.00
}

Rules:
1. Extract ALL food/drink items with their prices
2. For items ordered multiple times (e.g., "2 x Coffee" or "Coffee x2" or quantity shown), set quantity accordingly
3. Keep item names in their ORIGINAL language (Hebrew stays Hebrew, English stays English) - only remove garbled OCR artifacts
4. Mark tax lines with is_tax: true
5. Mark tip suggestion lines with is_tip_suggestion: true
6. Ignore subtotals, totals, payment info, addresses, dates, receipt numbers
7. Prices should be numbers (not strings)
8. If you can't read a price clearly, skip that item
9. Handle Hebrew, English, and mixed text - DO NOT translate
10. For Hebrew receipts, the currency is likely ILS (₪)

Return ONLY valid JSON, no other text."""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model_name)
        return self._client
    
    async def parse_receipt(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Parse a receipt image and extract structured data.
        
        Args:
            image_bytes: Raw image bytes (JPEG, PNG, or WebP)
            
        Returns:
            Dict with items, currency, subtotal, tax, total
        """
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not configured. "
                "Get a free API key at https://aistudio.google.com/apikey"
            )
        
        # Prepare image for Gemini
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary (Gemini doesn't like RGBA)
        if image.mode == 'RGBA':
            image = image.convert('RGB')
        
        # Get Gemini client
        model = self._get_client()
        
        # Call Gemini with the image (run in thread to avoid blocking event loop)
        import asyncio
        response = await asyncio.to_thread(
            model.generate_content,
            [self.RECEIPT_PROMPT, image]
        )
        
        # Parse the JSON response
        try:
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Handle markdown code blocks
            if response_text.startswith('```'):
                # Remove ```json and ``` markers
                lines = response_text.split('\n')
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith('```'):
                        in_json = not in_json
                        continue
                    if in_json or not line.startswith('```'):
                        json_lines.append(line)
                response_text = '\n'.join(json_lines)
            
            result = json.loads(response_text)
            
            # Validate and clean the result
            return self._validate_result(result)
            
        except json.JSONDecodeError as e:
            # If JSON parsing fails, return empty result
            return {
                "items": [],
                "currency": "USD",
                "subtotal": 0,
                "tax": 0,
                "total": 0,
                "raw_response": response.text,
                "error": f"Failed to parse AI response: {str(e)}"
            }
    
    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean the parsed result."""
        validated_items = []
        
        for item in result.get("items", []):
            try:
                # Ensure required fields
                name = str(item.get("name", "")).strip()
                price = float(item.get("price", 0))
                quantity = int(item.get("quantity", 1))
                
                # Skip invalid items
                if not name or price <= 0:
                    continue
                
                # Ensure quantity is reasonable
                if quantity < 1:
                    quantity = 1
                elif quantity > 100:
                    quantity = 1  # Probably an error
                
                validated_items.append({
                    "name": name,
                    "price": Decimal(str(price)).quantize(Decimal('0.01')),
                    "quantity": quantity,
                    "is_tax": bool(item.get("is_tax", False)),
                    "is_tip_suggestion": bool(item.get("is_tip_suggestion", False)),
                })
            except (ValueError, TypeError):
                continue
        
        return {
            "items": validated_items,
            "currency": result.get("currency", "USD"),
            "subtotal": Decimal(str(result.get("subtotal", 0))).quantize(Decimal('0.01')),
            "tax": Decimal(str(result.get("tax", 0))).quantize(Decimal('0.01')),
            "total": Decimal(str(result.get("total", 0))).quantize(Decimal('0.01')),
        }


class OCRService:
    """
    Main service for processing receipt images.
    
    Uses Google Gemini for AI-powered receipt recognition.
    """
    
    def __init__(self):
        self.parser = GeminiReceiptParser()
    
    async def process_receipt(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Process a receipt image and extract items.
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Dict containing:
                - raw_text: Description of what was found
                - items: List of extracted items
                - summary: Receipt summary
        """
        result = await self.parser.parse_receipt(image_bytes)
        
        # Convert to format expected by the rest of the app
        items = []
        for item in result["items"]:
            items.append({
                "name": item["name"],
                "price": str(item["price"]),
                "quantity": item["quantity"],
                "is_tax": item["is_tax"],
                "is_tip_suggestion": item["is_tip_suggestion"],
            })
        
        # Calculate summary
        items_subtotal = sum(
            Decimal(i["price"]) * i["quantity"] 
            for i in items 
            if not i["is_tax"] and not i["is_tip_suggestion"]
        )
        tax_total = sum(
            Decimal(i["price"]) * i["quantity"]
            for i in items
            if i["is_tax"]
        )
        
        return {
            "raw_text": f"Gemini AI parsed {len(items)} items from receipt",
            "items": items,
            "summary": {
                "currency": result["currency"],
                "items_subtotal": str(items_subtotal),
                "tax_total": str(tax_total),
                "estimated_total": str(items_subtotal + tax_total),
            }
        }
