"""
Unit tests for the BillCalculator service.

TDD: These tests are written FIRST, before the implementation.
Run with: pytest tests/unit/test_calculator.py -v
"""
import pytest
from decimal import Decimal
from dataclasses import dataclass
from typing import List, Optional


# Data classes for test inputs (mimicking our models)
# Using underscore prefix to avoid pytest collection warnings
@dataclass
class _Item:
    """Test item representation."""
    id: str
    name: str
    price: Decimal
    quantity: int = 1
    is_tax: bool = False
    is_tip_suggestion: bool = False


@dataclass
class _Assignment:
    """Test assignment representation."""
    item_id: str
    participant_id: str
    share_count: int = 1


@dataclass
class _Participant:
    """Test participant representation."""
    id: str
    name: str
    tip_percentage: Optional[Decimal] = None
    tip_amount: Optional[Decimal] = None


class TestBillCalculatorItemSplitting:
    """Tests for splitting individual items between participants."""
    
    def test_single_item_single_participant(self):
        """One person claims one item - they pay the full price."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Burger", price=Decimal("15.00"))
        assignments = [
            _Assignment(item_id="item1", participant_id="p1", share_count=1)
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        assert result["p1"] == Decimal("15.00")
    
    def test_single_item_split_equally_two_participants(self):
        """Two people share a $20 pizza equally."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Pizza", price=Decimal("20.00"))
        assignments = [
            _Assignment(item_id="item1", participant_id="p1", share_count=1),
            _Assignment(item_id="item1", participant_id="p2", share_count=1),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        assert result["p1"] == Decimal("10.00")
        assert result["p2"] == Decimal("10.00")
    
    def test_single_item_split_unequally(self):
        """One person ate 2 slices, another ate 1 slice of a $30 pizza."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Pizza", price=Decimal("30.00"))
        assignments = [
            _Assignment(item_id="item1", participant_id="p1", share_count=2),
            _Assignment(item_id="item1", participant_id="p2", share_count=1),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        assert result["p1"] == Decimal("20.00")  # 2/3 of $30
        assert result["p2"] == Decimal("10.00")  # 1/3 of $30
    
    def test_item_with_quantity(self):
        """2 burgers at $10 each = $20 total, split between 2 people."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Burger", price=Decimal("10.00"), quantity=2)
        assignments = [
            _Assignment(item_id="item1", participant_id="p1", share_count=1),
            _Assignment(item_id="item1", participant_id="p2", share_count=1),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        # Total is $20 (2 x $10), split equally
        assert result["p1"] == Decimal("10.00")
        assert result["p2"] == Decimal("10.00")
    
    def test_split_three_ways_with_rounding(self):
        """$10 split 3 ways - handle rounding correctly."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Appetizer", price=Decimal("10.00"))
        assignments = [
            _Assignment(item_id="item1", participant_id="p1", share_count=1),
            _Assignment(item_id="item1", participant_id="p2", share_count=1),
            _Assignment(item_id="item1", participant_id="p3", share_count=1),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        # $10 / 3 = $3.33... each, total should still be $10
        total = sum(result.values())
        assert total == Decimal("10.00")
        
        # Each should be approximately $3.33
        for participant_id, amount in result.items():
            assert Decimal("3.33") <= amount <= Decimal("3.34")
    
    def test_no_assignments_returns_empty(self):
        """Item with no assignments returns empty dict."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Unclaimed", price=Decimal("15.00"))
        assignments = []
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        assert result == {}


class TestBillCalculatorTipCalculation:
    """Tests for tip calculation."""
    
    def test_tip_percentage(self):
        """20% tip on $50 subtotal = $10."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        tip = calculator.calculate_tip(
            subtotal=Decimal("50.00"),
            tip_percentage=Decimal("20.00"),
            tip_amount=None
        )
        
        assert tip == Decimal("10.00")
    
    def test_tip_fixed_amount(self):
        """Fixed tip amount takes precedence."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        tip = calculator.calculate_tip(
            subtotal=Decimal("50.00"),
            tip_percentage=Decimal("20.00"),
            tip_amount=Decimal("15.00")  # Fixed amount
        )
        
        # Fixed amount takes precedence over percentage
        assert tip == Decimal("15.00")
    
    def test_no_tip(self):
        """No tip specified returns zero."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        tip = calculator.calculate_tip(
            subtotal=Decimal("50.00"),
            tip_percentage=None,
            tip_amount=None
        )
        
        assert tip == Decimal("0.00")
    
    def test_zero_tip_percentage(self):
        """0% tip is valid."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        tip = calculator.calculate_tip(
            subtotal=Decimal("50.00"),
            tip_percentage=Decimal("0.00"),
            tip_amount=None
        )
        
        assert tip == Decimal("0.00")
    
    def test_tip_on_small_amount(self):
        """15% tip on $7.50."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        tip = calculator.calculate_tip(
            subtotal=Decimal("7.50"),
            tip_percentage=Decimal("15.00"),
            tip_amount=None
        )
        
        assert tip == Decimal("1.13")  # Rounded to 2 decimal places


class TestBillCalculatorTaxDistribution:
    """Tests for distributing tax proportionally."""
    
    def test_tax_distributed_proportionally(self):
        """Tax distributed based on each participant's share of subtotal."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        
        # P1 ordered $30, P2 ordered $70 (total $100)
        participant_subtotals = {
            "p1": Decimal("30.00"),
            "p2": Decimal("70.00"),
        }
        tax_total = Decimal("10.00")
        
        result = calculator.distribute_tax(participant_subtotals, tax_total)
        
        # P1 should pay 30% of tax = $3
        assert result["p1"] == Decimal("3.00")
        # P2 should pay 70% of tax = $7
        assert result["p2"] == Decimal("7.00")
    
    def test_tax_with_single_participant(self):
        """Single participant pays all tax."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        
        participant_subtotals = {"p1": Decimal("50.00")}
        tax_total = Decimal("5.00")
        
        result = calculator.distribute_tax(participant_subtotals, tax_total)
        
        assert result["p1"] == Decimal("5.00")
    
    def test_tax_with_rounding(self):
        """Tax distribution handles rounding correctly."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        
        # Three equal subtotals, tax that doesn't divide evenly
        participant_subtotals = {
            "p1": Decimal("33.33"),
            "p2": Decimal("33.33"),
            "p3": Decimal("33.34"),
        }
        tax_total = Decimal("10.00")
        
        result = calculator.distribute_tax(participant_subtotals, tax_total)
        
        # Total distributed should equal tax total
        assert sum(result.values()) == Decimal("10.00")


class TestBillCalculatorFullBillSplit:
    """Tests for calculating the full bill split."""
    
    def test_simple_bill_two_participants(self):
        """Simple bill with 2 participants, each ordering separate items."""
        from app.services.calculator import BillCalculator
        
        items = [
            _Item(id="item1", name="Burger", price=Decimal("15.00")),
            _Item(id="item2", name="Salad", price=Decimal("12.00")),
            _Item(id="tax", name="Tax", price=Decimal("2.16"), is_tax=True),
        ]
        
        participants = [
            _Participant(id="p1", name="Alice", tip_percentage=Decimal("20.00")),
            _Participant(id="p2", name="Bob", tip_percentage=Decimal("15.00")),
        ]
        
        assignments = [
            _Assignment(item_id="item1", participant_id="p1"),  # Alice: Burger
            _Assignment(item_id="item2", participant_id="p2"),  # Bob: Salad
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_full_split(items, participants, assignments)
        
        # Alice: $15 + (15/27 * 2.16) tax + 20% tip
        alice = result["p1"]
        assert alice["items_subtotal"] == Decimal("15.00")
        
        # Bob: $12 + (12/27 * 2.16) tax + 15% tip
        bob = result["p2"]
        assert bob["items_subtotal"] == Decimal("12.00")
        
        # Verify tips
        assert alice["tip_amount"] == Decimal("3.00")  # 20% of $15
        assert bob["tip_amount"] == Decimal("1.80")    # 15% of $12
    
    def test_shared_item_split(self):
        """Bill where one item is shared between participants."""
        from app.services.calculator import BillCalculator
        
        items = [
            _Item(id="item1", name="Shared Appetizer", price=Decimal("20.00")),
            _Item(id="item2", name="Alice's Entree", price=Decimal("25.00")),
            _Item(id="item3", name="Bob's Entree", price=Decimal("22.00")),
        ]
        
        participants = [
            _Participant(id="p1", name="Alice", tip_percentage=Decimal("18.00")),
            _Participant(id="p2", name="Bob", tip_percentage=Decimal("18.00")),
        ]
        
        assignments = [
            _Assignment(item_id="item1", participant_id="p1"),  # Shared
            _Assignment(item_id="item1", participant_id="p2"),  # Shared
            _Assignment(item_id="item2", participant_id="p1"),  # Alice only
            _Assignment(item_id="item3", participant_id="p2"),  # Bob only
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_full_split(items, participants, assignments)
        
        # Alice: $10 (half appetizer) + $25 = $35
        assert result["p1"]["items_subtotal"] == Decimal("35.00")
        
        # Bob: $10 (half appetizer) + $22 = $32
        assert result["p2"]["items_subtotal"] == Decimal("32.00")
    
    def test_unassigned_items_tracked(self):
        """Unassigned items should be reported in the result."""
        from app.services.calculator import BillCalculator
        
        items = [
            _Item(id="item1", name="Burger", price=Decimal("15.00")),
            _Item(id="item2", name="Unclaimed Fries", price=Decimal("5.00")),
        ]
        
        participants = [
            _Participant(id="p1", name="Alice"),
        ]
        
        assignments = [
            _Assignment(item_id="item1", participant_id="p1"),
            # item2 is not assigned
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_full_split(items, participants, assignments)
        
        assert "unassigned_items" in result
        assert len(result["unassigned_items"]) == 1
        assert result["unassigned_items"][0]["id"] == "item2"
    
    def test_participant_with_no_items(self):
        """Participant who ordered nothing should have zero totals."""
        from app.services.calculator import BillCalculator
        
        items = [
            _Item(id="item1", name="Burger", price=Decimal("15.00")),
        ]
        
        participants = [
            _Participant(id="p1", name="Alice"),
            _Participant(id="p2", name="Bob"),  # Ordered nothing
        ]
        
        assignments = [
            _Assignment(item_id="item1", participant_id="p1"),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_full_split(items, participants, assignments)
        
        assert result["p2"]["items_subtotal"] == Decimal("0.00")
        assert result["p2"]["total"] == Decimal("0.00")
    
    def test_complete_bill_with_tax_and_tips(self):
        """Full integration: items + tax + different tips."""
        from app.services.calculator import BillCalculator
        
        items = [
            _Item(id="item1", name="Steak", price=Decimal("45.00")),
            _Item(id="item2", name="Pasta", price=Decimal("22.00")),
            _Item(id="item3", name="Wine", price=Decimal("33.00")),  # Shared
            _Item(id="tax", name="Sales Tax", price=Decimal("8.00"), is_tax=True),
        ]
        
        participants = [
            _Participant(id="p1", name="Alice", tip_percentage=Decimal("20.00")),
            _Participant(id="p2", name="Bob", tip_amount=Decimal("5.00")),  # Fixed tip
        ]
        
        assignments = [
            _Assignment(item_id="item1", participant_id="p1"),
            _Assignment(item_id="item2", participant_id="p2"),
            _Assignment(item_id="item3", participant_id="p1"),
            _Assignment(item_id="item3", participant_id="p2"),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_full_split(items, participants, assignments)
        
        # Alice: $45 + $16.50 (half wine) = $61.50 subtotal
        assert result["p1"]["items_subtotal"] == Decimal("61.50")
        
        # Bob: $22 + $16.50 (half wine) = $38.50 subtotal
        assert result["p2"]["items_subtotal"] == Decimal("38.50")
        
        # Tax distribution: Alice 61.5/100, Bob 38.5/100 of $8
        assert result["p1"]["tax_share"] == Decimal("4.92")
        assert result["p2"]["tax_share"] == Decimal("3.08")
        
        # Tips: Alice 20% of 61.50 = 12.30, Bob fixed $5
        assert result["p1"]["tip_amount"] == Decimal("12.30")
        assert result["p2"]["tip_amount"] == Decimal("5.00")
        
        # Totals
        assert result["p1"]["total"] == Decimal("78.72")  # 61.50 + 4.92 + 12.30
        assert result["p2"]["total"] == Decimal("46.58")  # 38.50 + 3.08 + 5.00


class TestBillCalculatorEdgeCases:
    """Edge case tests."""
    
    def test_empty_items_list(self):
        """Empty items list should return zero totals."""
        from app.services.calculator import BillCalculator
        
        calculator = BillCalculator()
        result = calculator.calculate_full_split(
            items=[],
            participants=[_Participant(id="p1", name="Alice")],
            assignments=[]
        )
        
        assert result["p1"]["total"] == Decimal("0.00")
    
    def test_very_small_amounts(self):
        """Handle very small amounts correctly."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Penny candy", price=Decimal("0.01"))
        assignments = [
            _Assignment(item_id="item1", participant_id="p1", share_count=1),
            _Assignment(item_id="item1", participant_id="p2", share_count=1),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        # $0.01 split 2 ways
        total = sum(result.values())
        assert total == Decimal("0.01")
    
    def test_large_amounts(self):
        """Handle large amounts correctly."""
        from app.services.calculator import BillCalculator
        
        item = _Item(id="item1", name="Expensive wine", price=Decimal("9999.99"))
        assignments = [
            _Assignment(item_id="item1", participant_id="p1", share_count=1),
        ]
        
        calculator = BillCalculator()
        result = calculator.calculate_item_share(item, assignments)
        
        assert result["p1"] == Decimal("9999.99")
