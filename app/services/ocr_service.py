"""
AI-powered Receipt Recognition Service using Google Gemini.

Uses Gemini's vision capabilities to extract structured data from receipt images.
Includes retry logic with exponential backoff for API resilience.
"""

from __future__ import annotations

import asyncio
import io
import json
import threading
from datetime import date
from decimal import Decimal
from typing import Any

import tenacity
from PIL import Image

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("ocr_service")


class DailyCallLimiter:
    """Thread-safe daily API call counter.

    Tracks the number of calls made today and rejects once the limit is hit.
    Resets automatically at midnight (server time).
    """

    def __init__(self, daily_limit: int):
        self._limit = daily_limit
        self._count = 0
        self._date = date.today()
        self._lock = threading.Lock()

    def _maybe_reset(self) -> None:
        """Reset counter if the date has rolled over."""
        today = date.today()
        if today != self._date:
            self._count = 0
            self._date = today

    def acquire(self) -> bool:
        """Try to acquire a call slot. Returns True if allowed."""
        if self._limit <= 0:  # 0 = unlimited
            return True
        with self._lock:
            self._maybe_reset()
            if self._count >= self._limit:
                return False
            self._count += 1
            return True

    @property
    def remaining(self) -> int:
        """Number of calls remaining today."""
        if self._limit <= 0:
            return -1  # unlimited
        with self._lock:
            self._maybe_reset()
            return max(0, self._limit - self._count)


# Module-level singleton — shared across all requests in this process
_daily_limiter: DailyCallLimiter | None = None


def _get_daily_limiter() -> DailyCallLimiter:
    global _daily_limiter
    if _daily_limiter is None:
        settings = get_settings()
        _daily_limiter = DailyCallLimiter(settings.gemini_daily_limit)
        logger.info(
            f"Gemini daily limit set to {settings.gemini_daily_limit} calls/day"
        )
    return _daily_limiter


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

    RECEIPT_PROMPT = """You are a human reading a restaurant receipt. Your job is to understand what was ordered, exactly the way a person sitting at that table would.

Think step by step:
1. First, read the ENTIRE receipt from top to bottom.
2. Understand the context — what kind of restaurant/bar/café is this? What cuisine?
3. Then extract every ordered item, understanding what each line ACTUALLY means.

Return a JSON object with this EXACT structure:
{
    "items": [
        {
            "name": "Human-readable item name",
            "price": 12.99,
            "quantity": 1,
            "is_tax": false,
            "is_tip_suggestion": false,
            "is_refund": false
        }
    ],
    "discounts": [
        {
            "name": "Discount description",
            "type": "fixed",
            "value": 5.00
        }
    ],
    "currency": "USD",
    "subtotal": 0.00,
    "tax": 0.00,
    "total": 0.00
}

=== HOW TO READ ITEM NAMES (THINK LIKE A HUMAN) ===

1. INFER UNCLEAR TEXT: Receipt printers often produce abbreviated, truncated, or garbled text. Do NOT output the raw garbled text. Instead, INFER what the item actually is based on context:
   - "HMBRG" or "HMBRGR" → "Hamburger"
   - "CHS FRIES" or "CHS FRS" → "Cheese Fries"
   - "CHKN WNGS" → "Chicken Wings"
   - "ESP DBL" → "Double Espresso"
   - "MGR PIZZA" → "Margherita Pizza"
   - "S.CHARGED" or "SRVC CHG" → "Service Charge"
   - "קפה הפ" or truncated Hebrew → infer the full word (e.g., "קפה הפוך")
   - If a word is partially cut off or corrupted, use the restaurant context + surrounding items + price to figure out what it most likely is
   - Use the FULL human-readable name, not the abbreviation. A person reading this receipt would say "Hamburger", not "HMBRG".

2. USE CONTEXT TO RESOLVE AMBIGUITY: If you're unsure what an item is, consider:
   - What other items were ordered? (helps identify the restaurant type)
   - What's the price? (a $2 item at a café is probably a coffee, not a steak)
   - What language is the receipt in? (Hebrew receipt at a café → "הפוך" is likely "קפה הפוך")
   - Common menu item patterns for that cuisine/restaurant type

=== MODIFIERS AND ADD-ONS (MERGE WITH PARENT) ===

3. ADDITIONS/MODIFIERS BELONG TO THE ITEM ABOVE THEM: Lines like "Add Cheese", "Extra Shot", "+Bacon", "תוספת גבינה", "ללא בצל" are NOT separate dishes — they are customizations of the item directly above them on the receipt.
   
   MERGE the modifier into the parent item:
   - "Hamburger $15.00" then "Add Cheese +$2.00" → ONE item: {"name": "Hamburger + Cheese", "price": 17.00, "quantity": 1}
   - "Pasta $22.00" then "Extra Sauce $1.50" then "Add Chicken $4.00" → ONE item: {"name": "Pasta + Extra Sauce + Chicken", "price": 27.50, "quantity": 1}
   - "Espresso 12₪" then "חלב שקדים +3₪" → ONE item: {"name": "Espresso + חלב שקדים", "price": 15.00, "quantity": 1}
   - "Salad $11.00" then "No Onions" (no price) → ONE item: {"name": "Salad (No Onions)", "price": 11.00, "quantity": 1}
   
   How to recognize modifiers:
   - Lines starting with "Add", "Extra", "+", "Sub:", "No ", "Without", "With", "תוספת", "ללא", "עם"
   - Lines with a small price (e.g., $0.50–$3.00) right after a main dish
   - Lines with NO price that describe a variation (e.g., "No Ice", "Well Done", "ללא בצל")
   - Indented lines or lines with a different formatting than main items

=== STACKED/REPEATED ITEMS ===

4. SAME ITEM ON CONSECUTIVE LINES = MULTIPLE QUANTITY:
   If the SAME item name appears on consecutive lines with the SAME unit price, combine them:
   - "Beer  $8.00" then "Beer  $8.00" → {"name": "Beer", "price": 16.00, "quantity": 2}
   - "Espresso 12₪" × 3 lines → {"name": "Espresso", "price": 36.00, "quantity": 3}
   
   The "price" field = unit_price × quantity (the TOTAL for all units).
   
   BUT: If stacked items each have DIFFERENT modifiers, keep them separate:
   - "Burger $15" + "Add Cheese $2" then "Burger $15" + "Add Bacon $3" → TWO separate items

5. EXPLICIT QUANTITY MARKERS: "2 x Coffee $8.00", "Coffee x2 $8.00", "Qty: 3 Soda $12.00" → use the stated quantity, price is the total shown.

=== SPECIAL LINE TYPES ===

6. TAX/VAT: Lines like "Tax", "VAT", "Sales Tax", "מע״מ", "GST", "TVA" → is_tax: true

7. TIP SUGGESTIONS: Lines like "Suggested tip: 18% = $5.40", "Tip 15%" → is_tip_suggestion: true. These are suggestions printed on the receipt, NOT actual charges.

8. REFUNDED/VOIDED ITEMS: Items marked "VOID", "REFUND", "CANCEL", "CR", with a minus sign, or struck through → is_refund: true, price as a POSITIVE number.

9. SERVICE CHARGES: "Service Charge", "שירות", "Gratuity" that are actual charges (not suggestions) → treat as regular items.

=== DISCOUNTS ===

10. Extract ALL discounts, coupons, promos, loyalty rewards, happy hour reductions into the "discounts" array:
    - Percentage: {"name": "10% Loyalty Discount", "type": "percentage", "value": 10}
    - Fixed: {"name": "$5 Coupon", "type": "fixed", "value": 5.00}
    - Item-level discounts (e.g., "Happy Hour Beer -$2.00"): fixed discount with descriptive name
    
    Discounts are NOT items. Do NOT put them in the items array.
    Discounts are NOT refunds. A refund removes a specific item; a discount reduces the price.

=== TOTALS ===

11. Read the printed subtotal, tax, and total EXACTLY as shown on the receipt.
12. SELF-CHECK: Sum of non-tax, non-tip, non-refund item prices − discount values ≈ printed subtotal. If they don't match, re-examine for missed or duplicated items before returning.
13. The "total" = final amount paid (after tax, after discounts).

=== GENERAL ===

14. Prices must be numbers (not strings).
15. If a price is COMPLETELY unreadable, skip that item. But if the item name is unclear, INFER it — don't skip.
16. Keep text in the ORIGINAL language but clean it up to be human-readable. "HMBRG" → "Hamburger", but "המבורגר" stays "המבורגר".
17. Currency: Hebrew receipts with ₪ → "ILS". € → "EUR". Default "USD".
18. Do NOT include: receipt headers, addresses, phone numbers, payment method details, change amounts, loyalty point balances, or marketing messages.

Return ONLY valid JSON, no other text."""

    CORRECTION_PROMPT_TEMPLATE = """I previously extracted these items from a receipt, but the total doesn't match.

My extracted items (total: {items_total}):
{items_list}

My extracted discounts (total: {discounts_total}):
{discounts_list}

Receipt's printed subtotal: {receipt_subtotal}
Receipt's printed tax: {receipt_tax}
Receipt's printed total: {receipt_total}

The difference is {difference}. Please re-examine the receipt image very carefully and return the CORRECTED JSON.

Common problems to check:
- Items that were DUPLICATED (same item listed twice when it should be quantity: 1)
- Items that were MISSED entirely
- Stacked items (same item on consecutive lines) that should be combined into one with higher quantity
- Discounts or credits that were missed or wrongly included as items
- Prices that were misread (e.g., reading $18.00 as $1.80)
- Modifier/add-on lines that should be MERGED into the parent item above them (e.g., "Add Cheese +$2" belongs to the burger above it)
- Abbreviated or garbled item names that need to be inferred (e.g., "HMBRG" = "Hamburger")

Remember:
- Modifier lines (Add, Extra, +, תוספת, etc.) should be merged into the item above them, combining their prices
- Infer unclear/abbreviated item names from context
- The "price" for items with quantity > 1 should be unit_price × quantity

Return the full corrected JSON in the same format as before. Return ONLY valid JSON, no other text."""

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

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(
            (ConnectionError, TimeoutError, OSError)
        ),
        before_sleep=lambda retry_state: logger.warning(
            f"Gemini API call failed (attempt {retry_state.attempt_number}), retrying..."
        ),
        reraise=True,
    )
    async def parse_receipt(self, image_bytes: bytes) -> dict[str, Any]:
        """
        Parse a receipt image and extract structured data.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, or WebP)

        Returns:
            Dict with items, currency, subtotal, tax, total

        Retries up to 3 times with exponential backoff on transient errors.
        """
        # Check daily call limit
        limiter = _get_daily_limiter()
        if not limiter.acquire():
            remaining = limiter.remaining
            logger.warning(f"Gemini daily limit reached ({limiter._limit} calls/day)")
            raise RuntimeError(
                "Daily receipt scan limit reached. Please try again tomorrow."
            )

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not configured. "
                "Get a free API key at https://aistudio.google.com/apikey"
            )

        # Prepare image for Gemini
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (Gemini doesn't like RGBA)
        if image.mode == "RGBA":
            image = image.convert("RGB")

        # Get Gemini client
        model = self._get_client()

        # Call Gemini with the image (run in thread to avoid blocking event loop)
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, [self.RECEIPT_PROMPT, image]),
                timeout=60,  # 60s timeout for Gemini API call
            )
        except asyncio.TimeoutError:
            logger.error("Gemini API call timed out after 60s")
            raise TimeoutError("Receipt processing timed out. Please try again.")

        # Parse the JSON response
        try:
            # Extract JSON from response
            response_text = response.text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```"):
                # Remove ```json and ``` markers
                lines = response_text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```"):
                        in_json = not in_json
                        continue
                    if in_json or not line.startswith("```"):
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

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
                "error": f"Failed to parse AI response: {str(e)}",
            }

    def _validate_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Validate and clean the parsed result."""
        validated_items = []

        for item in result.get("items", []):
            try:
                # Ensure required fields
                name = str(item.get("name", "")).strip()
                price = float(item.get("price", 0))
                quantity = int(item.get("quantity", 1))
                is_refund = bool(item.get("is_refund", False))

                # Skip invalid items (refund items must also have positive price)
                if not name or price <= 0:
                    continue

                # Ensure quantity is reasonable
                if quantity < 1:
                    quantity = 1
                elif quantity > 100:
                    quantity = 1  # Probably an error

                validated_items.append(
                    {
                        "name": name,
                        "price": Decimal(str(price)).quantize(Decimal("0.01")),
                        "quantity": quantity,
                        "is_tax": bool(item.get("is_tax", False)),
                        "is_tip_suggestion": bool(item.get("is_tip_suggestion", False)),
                        "is_refund": is_refund,
                    }
                )
            except (ValueError, TypeError):
                continue

        # Validate discounts
        validated_discounts = []
        for discount in result.get("discounts", []):
            try:
                name = str(discount.get("name", "")).strip()
                dtype = str(discount.get("type", "fixed")).strip().lower()
                value = float(discount.get("value", 0))

                if not name or value <= 0:
                    continue

                # Normalize discount type
                if dtype not in ("percentage", "fixed"):
                    dtype = "fixed"

                # Percentage must be <= 100
                if dtype == "percentage" and value > 100:
                    continue

                validated_discounts.append(
                    {
                        "name": name,
                        "type": dtype,
                        "value": Decimal(str(value)).quantize(Decimal("0.01")),
                    }
                )
            except (ValueError, TypeError):
                continue

        return {
            "items": validated_items,
            "discounts": validated_discounts,
            "currency": result.get("currency", "USD"),
            "subtotal": Decimal(str(result.get("subtotal", 0))).quantize(
                Decimal("0.01")
            ),
            "tax": Decimal(str(result.get("tax", 0))).quantize(Decimal("0.01")),
            "total": Decimal(str(result.get("total", 0))).quantize(Decimal("0.01")),
        }

    async def _retry_with_correction(
        self, image_bytes: bytes, original_result: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Make a second Gemini call to correct a mismatch between items and totals.

        Args:
            image_bytes: Original image bytes
            original_result: The first parse result with items/discounts/totals

        Returns:
            Corrected result dict, or original if retry fails
        """
        # Build items list for the correction prompt
        items_lines = []
        for item in original_result["items"]:
            flags = []
            if item["is_tax"]:
                flags.append("TAX")
            if item["is_refund"]:
                flags.append("REFUND")
            if item["is_tip_suggestion"]:
                flags.append("TIP")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            items_lines.append(
                f"  - {item['name']} × {item['quantity']} = {item['price']}{flag_str}"
            )

        discounts_lines = []
        discounts_total = Decimal("0.00")
        for d in original_result.get("discounts", []):
            if d["type"] == "percentage":
                discounts_lines.append(f"  - {d['name']}: {d['value']}%")
            else:
                discounts_lines.append(f"  - {d['name']}: {d['value']}")
                discounts_total += d["value"]

        # Calculate items total (non-tax, non-tip, non-refund)
        items_total = sum(
            item["price"] * item["quantity"]
            for item in original_result["items"]
            if not item["is_tax"]
            and not item["is_tip_suggestion"]
            and not item["is_refund"]
        )

        difference = items_total - discounts_total - original_result["subtotal"]

        correction_prompt = self.CORRECTION_PROMPT_TEMPLATE.format(
            items_total=items_total,
            items_list="\n".join(items_lines) if items_lines else "  (none)",
            discounts_total=discounts_total,
            discounts_list=(
                "\n".join(discounts_lines) if discounts_lines else "  (none)"
            ),
            receipt_subtotal=original_result["subtotal"],
            receipt_tax=original_result["tax"],
            receipt_total=original_result["total"],
            difference=difference,
        )

        # Check daily limit for retry call
        limiter = _get_daily_limiter()
        if not limiter.acquire():
            logger.warning("Daily limit reached, skipping correction retry")
            return original_result

        try:
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode == "RGBA":
                image = image.convert("RGB")

            model = self._get_client()

            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, [correction_prompt, image]),
                timeout=60,
            )

            response_text = response.text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```"):
                        in_json = not in_json
                        continue
                    if in_json or not line.startswith("```"):
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

            corrected = json.loads(response_text)
            corrected_result = self._validate_result(corrected)

            logger.info("Correction retry succeeded, using corrected result")
            return corrected_result

        except Exception as e:
            logger.warning(f"Correction retry failed: {e}, using original result")
            return original_result


# Mismatch threshold: if item sum vs receipt subtotal differs by more than this, retry
MISMATCH_THRESHOLD = Decimal("1.00")


class OCRService:
    """
    Main service for processing receipt images.

    Uses Google Gemini for AI-powered receipt recognition.
    Includes mismatch detection with automatic corrective retry.
    """

    def __init__(self):
        self.parser = GeminiReceiptParser()

    async def process_receipt(self, image_bytes: bytes) -> dict[str, Any]:
        """
        Process a receipt image and extract items.

        Args:
            image_bytes: Raw image bytes

        Returns:
            Dict containing:
                - raw_text: Description of what was found
                - items: List of extracted items (with is_refund flag)
                - discounts: List of extracted discounts
                - summary: Receipt summary
                - warnings: List of warning messages
                - mismatch_retried: Whether a correction retry was attempted
        """
        result = await self.parser.parse_receipt(image_bytes)

        warnings = []
        mismatch_retried = False

        # Check for errors from parse_receipt (e.g., JSON decode failure)
        if result.get("error"):
            warnings.append(result["error"])

        # Calculate items subtotal (non-tax, non-tip, non-refund)
        items_subtotal = sum(
            item["price"] * item["quantity"]
            for item in result["items"]
            if not item["is_tax"]
            and not item["is_tip_suggestion"]
            and not item["is_refund"]
        )

        # Calculate discount total (fixed discounts only for subtotal comparison)
        fixed_discounts_total = sum(
            d["value"] for d in result.get("discounts", []) if d["type"] == "fixed"
        )

        # Check for total mismatch — compare computed items subtotal against receipt's subtotal
        receipt_subtotal = result.get("subtotal", Decimal("0.00"))
        receipt_total = result.get("total", Decimal("0.00"))

        if receipt_subtotal > Decimal("0"):
            difference = abs(items_subtotal - fixed_discounts_total - receipt_subtotal)
            if difference > MISMATCH_THRESHOLD:
                logger.warning(
                    f"Total mismatch detected: items={items_subtotal}, "
                    f"discounts={fixed_discounts_total}, receipt_subtotal={receipt_subtotal}, "
                    f"difference={difference}"
                )

                # Attempt corrective retry
                corrected = await self.parser._retry_with_correction(
                    image_bytes, result
                )
                mismatch_retried = True

                # Check if corrected result is better
                corrected_subtotal = sum(
                    item["price"] * item["quantity"]
                    for item in corrected["items"]
                    if not item["is_tax"]
                    and not item["is_tip_suggestion"]
                    and not item["is_refund"]
                )
                corrected_fixed_discounts = sum(
                    d["value"]
                    for d in corrected.get("discounts", [])
                    if d["type"] == "fixed"
                )
                corrected_diff = abs(
                    corrected_subtotal - corrected_fixed_discounts - receipt_subtotal
                )

                if corrected_diff < difference:
                    logger.info(
                        f"Corrected result is better: diff {corrected_diff} < {difference}"
                    )
                    result = corrected
                    items_subtotal = corrected_subtotal
                    fixed_discounts_total = corrected_fixed_discounts

                    if corrected_diff > MISMATCH_THRESHOLD:
                        warnings.append(
                            f"Items may not match receipt total. "
                            f"Extracted items: {items_subtotal}, Receipt subtotal: {receipt_subtotal}. "
                            f"Please review items manually."
                        )
                else:
                    warnings.append(
                        f"Items may not match receipt total. "
                        f"Extracted items: {items_subtotal}, Receipt subtotal: {receipt_subtotal}. "
                        f"Please review items manually."
                    )

        # Convert to format expected by the rest of the app
        items = []
        for item in result["items"]:
            items.append(
                {
                    "name": item["name"],
                    "price": str(item["price"]),
                    "quantity": item["quantity"],
                    "is_tax": item["is_tax"],
                    "is_tip_suggestion": item["is_tip_suggestion"],
                    "is_refund": item.get("is_refund", False),
                }
            )

        # Convert discounts
        discounts = []
        for d in result.get("discounts", []):
            discounts.append(
                {
                    "name": d["name"],
                    "type": d["type"],
                    "value": str(d["value"]),
                }
            )

        # Recalculate summary with final values
        tax_total = sum(
            Decimal(i["price"]) * i["quantity"] for i in items if i["is_tax"]
        )

        return {
            "raw_text": f"Gemini AI parsed {len(items)} items from receipt",
            "items": items,
            "discounts": discounts,
            "summary": {
                "currency": result["currency"],
                "items_subtotal": str(items_subtotal),
                "tax_total": str(tax_total),
                "estimated_total": str(items_subtotal + tax_total),
                "receipt_subtotal": str(result.get("subtotal", Decimal("0.00"))),
                "receipt_total": str(result.get("total", Decimal("0.00"))),
            },
            "warnings": warnings,
            "mismatch_retried": mismatch_retried,
        }
