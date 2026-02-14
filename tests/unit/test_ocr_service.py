"""
Tests for AI-powered receipt recognition service.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal


class TestGeminiReceiptParser:
    """Tests for Gemini receipt parser."""
    
    def test_validate_result_cleans_items(self):
        """Test that validation cleans and filters items properly."""
        from app.services.ocr_service import GeminiReceiptParser
        
        parser = GeminiReceiptParser()
        
        raw_result = {
            "items": [
                {"name": "Coffee", "price": 4.50, "quantity": 2},
                {"name": "Burger", "price": 12.99, "quantity": 1},
                {"name": "", "price": 5.00, "quantity": 1},  # Empty name - should be filtered
                {"name": "Tax", "price": 1.50, "quantity": 1, "is_tax": True},
                {"name": "Invalid", "price": -5.00, "quantity": 1},  # Negative - should be filtered
            ],
            "currency": "USD",
            "subtotal": 22.49,
            "tax": 1.50,
            "total": 23.99
        }
        
        result = parser._validate_result(raw_result)
        
        assert len(result["items"]) == 3  # Only valid items
        assert result["items"][0]["name"] == "Coffee"
        assert result["items"][0]["quantity"] == 2
        assert result["items"][0]["is_refund"] == False
        assert result["items"][1]["name"] == "Burger"
        assert result["items"][2]["is_tax"] == True
        assert result["currency"] == "USD"
        assert result["discounts"] == []
    
    def test_validate_result_handles_invalid_quantity(self):
        """Test that validation fixes invalid quantities."""
        from app.services.ocr_service import GeminiReceiptParser
        
        parser = GeminiReceiptParser()
        
        raw_result = {
            "items": [
                {"name": "Item1", "price": 10.00, "quantity": 0},  # Should become 1
                {"name": "Item2", "price": 10.00, "quantity": 999},  # Should become 1
            ],
            "currency": "USD",
            "subtotal": 20.00,
            "tax": 0,
            "total": 20.00
        }
        
        result = parser._validate_result(raw_result)
        
        assert result["items"][0]["quantity"] == 1
        assert result["items"][1]["quantity"] == 1
    
    def test_validate_result_handles_missing_fields(self):
        """Test that validation handles missing fields gracefully."""
        from app.services.ocr_service import GeminiReceiptParser
        
        parser = GeminiReceiptParser()
        
        raw_result = {
            "items": [
                {"name": "Coffee", "price": 4.50},  # Missing quantity
            ]
        }
        
        result = parser._validate_result(raw_result)
        
        assert len(result["items"]) == 1
        assert result["items"][0]["quantity"] == 1
        assert result["items"][0]["is_refund"] == False
        assert result["currency"] == "USD"  # Default
        assert result["subtotal"] == Decimal("0.00")
        assert result["discounts"] == []
    
    def test_validate_result_with_refund_items(self):
        """Test that validation correctly handles refund items."""
        from app.services.ocr_service import GeminiReceiptParser
        
        parser = GeminiReceiptParser()
        
        raw_result = {
            "items": [
                {"name": "Burger", "price": 12.99, "quantity": 1},
                {"name": "Refunded Soda", "price": 3.50, "quantity": 1, "is_refund": True},
            ],
            "currency": "USD",
            "subtotal": 9.49,
            "tax": 0,
            "total": 9.49
        }
        
        result = parser._validate_result(raw_result)
        
        assert len(result["items"]) == 2
        assert result["items"][0]["is_refund"] == False
        assert result["items"][1]["is_refund"] == True
        assert result["items"][1]["name"] == "Refunded Soda"
        assert result["items"][1]["price"] == Decimal("3.50")
    
    def test_validate_result_with_discounts(self):
        """Test that validation correctly handles discounts from Gemini."""
        from app.services.ocr_service import GeminiReceiptParser
        
        parser = GeminiReceiptParser()
        
        raw_result = {
            "items": [
                {"name": "Burger", "price": 12.99, "quantity": 1},
            ],
            "discounts": [
                {"name": "10% Loyalty", "type": "percentage", "value": 10},
                {"name": "$5 Coupon", "type": "fixed", "value": 5.00},
                {"name": "Invalid", "type": "fixed", "value": -2.00},  # Negative - filtered
                {"name": "", "type": "fixed", "value": 3.00},  # Empty name - filtered
                {"name": "Bad percentage", "type": "percentage", "value": 150},  # > 100 - filtered
            ],
            "currency": "USD",
            "subtotal": 12.99,
            "tax": 0,
            "total": 6.69
        }
        
        result = parser._validate_result(raw_result)
        
        assert len(result["discounts"]) == 2
        assert result["discounts"][0]["name"] == "10% Loyalty"
        assert result["discounts"][0]["type"] == "percentage"
        assert result["discounts"][0]["value"] == Decimal("10.00")
        assert result["discounts"][1]["name"] == "$5 Coupon"
        assert result["discounts"][1]["type"] == "fixed"
        assert result["discounts"][1]["value"] == Decimal("5.00")
    
    def test_validate_result_normalizes_discount_type(self):
        """Test that unknown discount types default to 'fixed'."""
        from app.services.ocr_service import GeminiReceiptParser
        
        parser = GeminiReceiptParser()
        
        raw_result = {
            "items": [],
            "discounts": [
                {"name": "Mystery Discount", "type": "unknown_type", "value": 5.00},
            ],
        }
        
        result = parser._validate_result(raw_result)
        
        assert len(result["discounts"]) == 1
        assert result["discounts"][0]["type"] == "fixed"


class TestOCRService:
    """Tests for the main OCR service."""
    
    @pytest.mark.asyncio
    async def test_process_receipt_formats_output(self):
        """Test that process_receipt returns properly formatted output."""
        from app.services.ocr_service import OCRService
        
        service = OCRService()
        
        # Mock the parser
        mock_result = {
            "items": [
                {"name": "Burger", "price": Decimal("12.99"), "quantity": 1, "is_tax": False, "is_tip_suggestion": False, "is_refund": False},
                {"name": "Fries", "price": Decimal("4.99"), "quantity": 2, "is_tax": False, "is_tip_suggestion": False, "is_refund": False},
                {"name": "Tax", "price": Decimal("1.80"), "quantity": 1, "is_tax": True, "is_tip_suggestion": False, "is_refund": False},
            ],
            "discounts": [],
            "currency": "USD",
            "subtotal": Decimal("22.97"),
            "tax": Decimal("1.80"),
            "total": Decimal("24.77")
        }
        
        with patch.object(service.parser, 'parse_receipt', return_value=mock_result):
            result = await service.process_receipt(b"fake_image_bytes")
        
        assert "items" in result
        assert "discounts" in result
        assert "summary" in result
        assert "warnings" in result
        assert "mismatch_retried" in result
        assert len(result["items"]) == 3
        assert result["items"][0]["name"] == "Burger"
        assert result["items"][0]["price"] == "12.99"
        assert result["items"][0]["is_refund"] == False
        assert result["summary"]["currency"] == "USD"
        assert result["mismatch_retried"] == False
    
    @pytest.mark.asyncio
    async def test_process_receipt_with_refund_and_discounts(self):
        """Test that process_receipt handles refund items and discounts."""
        from app.services.ocr_service import OCRService
        
        service = OCRService()
        
        mock_result = {
            "items": [
                {"name": "Burger", "price": Decimal("12.99"), "quantity": 1, "is_tax": False, "is_tip_suggestion": False, "is_refund": False},
                {"name": "Voided Drink", "price": Decimal("5.00"), "quantity": 1, "is_tax": False, "is_tip_suggestion": False, "is_refund": True},
            ],
            "discounts": [
                {"name": "10% Off", "type": "percentage", "value": Decimal("10.00")},
            ],
            "currency": "USD",
            "subtotal": Decimal("12.99"),
            "tax": Decimal("0.00"),
            "total": Decimal("11.69")
        }
        
        with patch.object(service.parser, 'parse_receipt', return_value=mock_result):
            result = await service.process_receipt(b"fake_image_bytes")
        
        assert len(result["items"]) == 2
        assert result["items"][1]["is_refund"] == True
        assert len(result["discounts"]) == 1
        assert result["discounts"][0]["name"] == "10% Off"
        assert result["discounts"][0]["type"] == "percentage"
        # Items subtotal should only include non-refund items
        assert result["summary"]["items_subtotal"] == "12.99"
    
    def test_service_initialization(self):
        """Test that OCR service initializes correctly."""
        from app.services.ocr_service import OCRService
        
        service = OCRService()
        assert service.parser is not None


class TestGeminiIntegration:
    """Integration tests that require a real Gemini API key."""
    
    @pytest.mark.skip(reason="Requires GEMINI_API_KEY environment variable")
    @pytest.mark.asyncio
    async def test_real_receipt_parsing(self):
        """Test with a real receipt image (requires API key)."""
        from app.services.ocr_service import OCRService
        import os
        
        # Only run if API key is set
        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")
        
        service = OCRService()
        
        # Load test image
        test_image_path = "receipt.png"
        if not os.path.exists(test_image_path):
            pytest.skip("Test image not found")
        
        with open(test_image_path, "rb") as f:
            image_bytes = f.read()
        
        result = await service.process_receipt(image_bytes)
        
        assert "items" in result
        assert len(result["items"]) > 0
        print(f"Found {len(result['items'])} items")
        for item in result["items"]:
            print(f"  - {item['name']}: {item['price']}")
