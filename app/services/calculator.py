"""
Bill Calculator Service.

Handles all calculations for splitting bills between participants,
including item sharing, tax distribution, tip calculation, and discounts.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Protocol


class ItemProtocol(Protocol):
    """Protocol for item-like objects."""
    id: str
    name: str
    price: Decimal
    quantity: int
    is_tax: bool
    is_tip_suggestion: bool


class AssignmentProtocol(Protocol):
    """Protocol for assignment-like objects."""
    item_id: str
    participant_id: str
    share_count: int


class ParticipantProtocol(Protocol):
    """Protocol for participant-like objects."""
    id: str
    name: str
    tip_percentage: Decimal | None
    tip_amount: Decimal | None


class DiscountProtocol(Protocol):
    """Protocol for discount-like objects."""
    id: str
    name: str
    discount_type: str  # "percentage" or "fixed"
    value: Decimal
    participant_id: str | None  # None = entire bill


class BillCalculator:
    """
    Calculator for splitting bills between participants.
    
    Handles:
    - Splitting individual items based on share counts
    - Calculating tips (percentage or fixed amount)
    - Distributing tax proportionally
    - Full bill split calculation
    """
    
    def __init__(self, decimal_places: int = 2):
        """
        Initialize the calculator.
        
        Args:
            decimal_places: Number of decimal places for rounding (default: 2)
        """
        self.decimal_places = decimal_places
        self.quantize_exp = Decimal(10) ** -decimal_places
    
    def _round(self, value: Decimal) -> Decimal:
        """Round a decimal value to the configured precision."""
        return value.quantize(self.quantize_exp, rounding=ROUND_HALF_UP)
    
    def _distribute_with_remainder(
        self, 
        total: Decimal, 
        shares: dict[str, int]
    ) -> dict[str, Decimal]:
        """
        Distribute a total amount based on share counts, handling remainders.
        
        This ensures the sum of distributed amounts exactly equals the total,
        with any rounding remainder given to the participant with the most shares.
        
        Args:
            total: Total amount to distribute
            shares: Dict mapping participant_id to share_count
            
        Returns:
            Dict mapping participant_id to their share amount
        """
        if not shares:
            return {}
        
        total_shares = sum(shares.values())
        if total_shares == 0:
            return {pid: Decimal("0.00") for pid in shares}
        
        result = {}
        distributed = Decimal("0.00")
        
        # Sort by share count (descending) to give remainder to largest shareholder
        sorted_participants = sorted(shares.items(), key=lambda x: x[1], reverse=True)
        
        for i, (participant_id, share_count) in enumerate(sorted_participants):
            if i == len(sorted_participants) - 1:
                # Last participant gets the remainder to ensure exact total
                result[participant_id] = self._round(total - distributed)
            else:
                share = self._round(total * Decimal(share_count) / Decimal(total_shares))
                result[participant_id] = share
                distributed += share
        
        return result
    
    def calculate_item_share(
        self, 
        item: ItemProtocol, 
        assignments: list[AssignmentProtocol]
    ) -> dict[str, Decimal]:
        """
        Calculate how much each participant pays for a single item.
        
        Args:
            item: The item to split
            assignments: List of assignments for this item
            
        Returns:
            Dict mapping participant_id to their share of the item cost
        """
        # Filter assignments to only those for this item
        item_assignments = [a for a in assignments if a.item_id == item.id]
        
        if not item_assignments:
            return {}
        
        # Calculate total item cost (price * quantity)
        total_cost = item.price * item.quantity
        
        # Build shares dict
        shares = {a.participant_id: a.share_count for a in item_assignments}
        
        return self._distribute_with_remainder(total_cost, shares)
    
    def calculate_tip(
        self,
        subtotal: Decimal,
        tip_percentage: Decimal | None,
        tip_amount: Decimal | None
    ) -> Decimal:
        """
        Calculate tip for a participant.
        
        Fixed tip_amount takes precedence over tip_percentage.
        
        Args:
            subtotal: The participant's subtotal (before tax)
            tip_percentage: Tip as a percentage (e.g., 20.00 for 20%)
            tip_amount: Fixed tip amount
            
        Returns:
            Calculated tip amount
        """
        # Fixed amount takes precedence
        if tip_amount is not None:
            return self._round(tip_amount)
        
        # Calculate from percentage
        if tip_percentage is not None:
            return self._round(subtotal * tip_percentage / Decimal("100"))
        
        # No tip
        return Decimal("0.00")
    
    def distribute_tax(
        self,
        participant_subtotals: dict[str, Decimal],
        tax_total: Decimal
    ) -> dict[str, Decimal]:
        """
        Distribute tax proportionally based on each participant's subtotal.
        
        Args:
            participant_subtotals: Dict mapping participant_id to their subtotal
            tax_total: Total tax amount to distribute
            
        Returns:
            Dict mapping participant_id to their share of tax
        """
        total_subtotal = sum(participant_subtotals.values())
        
        if total_subtotal == Decimal("0"):
            # No items ordered, no tax to distribute
            return {pid: Decimal("0.00") for pid in participant_subtotals}
        
        result = {}
        distributed = Decimal("0.00")
        
        # Sort by subtotal (descending) for consistent remainder handling
        sorted_participants = sorted(
            participant_subtotals.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        for i, (participant_id, subtotal) in enumerate(sorted_participants):
            if i == len(sorted_participants) - 1:
                # Last participant gets remainder
                result[participant_id] = self._round(tax_total - distributed)
            else:
                share = self._round(tax_total * subtotal / total_subtotal)
                result[participant_id] = share
                distributed += share
        
        return result
    
    def calculate_discount(
        self,
        subtotal: Decimal,
        discount_type: str,
        discount_value: Decimal
    ) -> Decimal:
        """
        Calculate the discount amount.
        
        Args:
            subtotal: The amount to apply discount to
            discount_type: 'percentage' or 'fixed'
            discount_value: The discount value
            
        Returns:
            The discount amount (always positive)
        """
        if discount_type == "percentage":
            return self._round(subtotal * discount_value / Decimal("100"))
        else:  # fixed
            # Fixed discount cannot exceed subtotal
            return self._round(min(discount_value, subtotal))
    
    def calculate_full_split(
        self,
        items: list[ItemProtocol],
        participants: list[ParticipantProtocol],
        assignments: list[AssignmentProtocol],
        discounts: list[DiscountProtocol] | None = None
    ) -> dict[str, Any]:
        """
        Calculate the full bill split for all participants.
        
        Args:
            items: List of all items in the bill
            participants: List of all participants
            assignments: List of all item assignments
            discounts: Optional list of discounts to apply
            
        Returns:
            Dict with participant summaries and unassigned items
        """
        discounts = discounts or []
        
        # Separate regular items from tax items
        regular_items = [i for i in items if not i.is_tax and not i.is_tip_suggestion]
        tax_items = [i for i in items if i.is_tax]
        
        # Calculate total tax
        tax_total = sum(item.price * item.quantity for item in tax_items)
        
        # Initialize participant data
        participant_data = {}
        for p in participants:
            participant_data[p.id] = {
                "participant_id": p.id,
                "participant_name": p.name,
                "items_subtotal": Decimal("0.00"),
                "tax_share": Decimal("0.00"),
                "tip_amount": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "total": Decimal("0.00"),
                "items": [],
                "applied_discounts": [],
                "_tip_percentage": p.tip_percentage,
                "_tip_amount": p.tip_amount,
            }
        
        # Track which items are assigned
        assigned_item_ids = set()
        
        # Calculate each participant's share of each item
        for item in regular_items:
            item_shares = self.calculate_item_share(item, assignments)
            
            if item_shares:
                assigned_item_ids.add(item.id)
            
            for participant_id, share_amount in item_shares.items():
                if participant_id in participant_data:
                    participant_data[participant_id]["items_subtotal"] += share_amount
                    participant_data[participant_id]["items"].append({
                        "id": item.id,
                        "name": item.name,
                        "share_amount": share_amount,
                    })
        
        # Distribute tax proportionally
        participant_subtotals = {
            pid: data["items_subtotal"] 
            for pid, data in participant_data.items()
        }
        
        if tax_total > Decimal("0"):
            tax_shares = self.distribute_tax(participant_subtotals, tax_total)
            for participant_id, tax_share in tax_shares.items():
                participant_data[participant_id]["tax_share"] = tax_share
        
        # Apply discounts
        # Separate participant-specific and bill-wide discounts
        participant_discounts = [d for d in discounts if d.participant_id]
        bill_discounts = [d for d in discounts if not d.participant_id]
        
        # Apply participant-specific discounts first
        for discount in participant_discounts:
            if discount.participant_id in participant_data:
                data = participant_data[discount.participant_id]
                discount_amount = self.calculate_discount(
                    data["items_subtotal"],
                    discount.discount_type,
                    discount.value
                )
                data["discount_amount"] += discount_amount
                data["applied_discounts"].append({
                    "id": discount.id,
                    "name": discount.name,
                    "type": discount.discount_type,
                    "value": discount.value,
                    "amount": discount_amount,
                })
        
        # Apply bill-wide discounts
        # - Percentage discounts: proportional (% of your items)
        # - Fixed discounts: split evenly between all participants with items
        total_bill_subtotal = sum(d["items_subtotal"] for d in participant_data.values())
        participants_with_items = [
            (pid, data) for pid, data in participant_data.items() 
            if data["items_subtotal"] > Decimal("0")
        ]
        
        for discount in bill_discounts:
            if not participants_with_items:
                continue
                
            if discount.discount_type == "percentage":
                # Percentage: distribute proportionally based on subtotal
                if total_bill_subtotal > Decimal("0"):
                    total_discount = self.calculate_discount(
                        total_bill_subtotal,
                        discount.discount_type,
                        discount.value
                    )
                    
                    distributed_discount = Decimal("0.00")
                    sorted_by_subtotal = sorted(
                        participants_with_items,
                        key=lambda x: x[1]["items_subtotal"],
                        reverse=True
                    )
                    
                    for i, (pid, data) in enumerate(sorted_by_subtotal):
                        if i == len(sorted_by_subtotal) - 1:
                            share = self._round(total_discount - distributed_discount)
                        else:
                            share = self._round(
                                total_discount * data["items_subtotal"] / total_bill_subtotal
                            )
                            distributed_discount += share
                        
                        data["discount_amount"] += share
                        data["applied_discounts"].append({
                            "id": discount.id,
                            "name": discount.name,
                            "type": discount.discount_type,
                            "value": discount.value,
                            "amount": share,
                        })
            else:
                # Fixed amount: split evenly between participants with items
                num_participants = len(participants_with_items)
                # Cap fixed discount at total bill
                total_discount = min(discount.value, total_bill_subtotal)
                per_person = self._round(total_discount / Decimal(num_participants))
                
                distributed_discount = Decimal("0.00")
                for i, (pid, data) in enumerate(participants_with_items):
                    if i == num_participants - 1:
                        # Last person gets remainder to ensure exact total
                        share = self._round(total_discount - distributed_discount)
                    else:
                        share = per_person
                        distributed_discount += share
                    
                    # Don't give more discount than their subtotal
                    share = min(share, data["items_subtotal"] - data["discount_amount"])
                    share = max(Decimal("0.00"), share)
                    
                    data["discount_amount"] += share
                    data["applied_discounts"].append({
                        "id": discount.id,
                        "name": discount.name,
                        "type": discount.discount_type,
                        "value": discount.value,
                        "amount": share,
                    })
        
        # Calculate tips and totals for each participant
        for participant_id, data in participant_data.items():
            # Calculate tip based on subtotal AFTER discount (before tax)
            subtotal_after_discount = data["items_subtotal"] - data["discount_amount"]
            data["tip_amount"] = self.calculate_tip(
                max(Decimal("0.00"), subtotal_after_discount),
                data["_tip_percentage"],
                data["_tip_amount"]
            )
            
            # Calculate total (subtotal + tax + tip - discount)
            data["total"] = self._round(
                data["items_subtotal"] + 
                data["tax_share"] + 
                data["tip_amount"] -
                data["discount_amount"]
            )
            
            # Ensure total is not negative
            data["total"] = max(Decimal("0.00"), data["total"])
            
            # Clean up internal fields
            del data["_tip_percentage"]
            del data["_tip_amount"]
        
        # Find unassigned items
        unassigned_items = []
        for item in regular_items:
            if item.id not in assigned_item_ids:
                unassigned_items.append({
                    "id": item.id,
                    "name": item.name,
                    "price": item.price,
                })
        
        # Build final result
        result = dict(participant_data)
        result["unassigned_items"] = unassigned_items
        
        # Calculate total discount applied
        result["total_discount"] = sum(
            d["discount_amount"] for d in participant_data.values()
        )
        
        return result
