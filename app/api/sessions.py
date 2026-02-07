"""
Sessions API routes.

Handles session creation, retrieval, QR codes, and summaries.
"""
import os
import re
import uuid
import hashlib
import aiofiles
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.logging_config import get_logger
from app.schemas.session import SessionCreate, SessionResponse, SessionSummary, ParticipantSummary, NearbySession, NearbySessionsResponse
from app.services.session_service import SessionService
from app.services.qr_service import QRService
from app.services.calculator import BillCalculator
from app.services.ocr_service import OCRService
from app.models.item import Item
from app.models.session import Session, SessionStatus

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = get_logger("api.sessions")


def get_client_network_hash(request: Request) -> str:
    """Generate a hash of the client's network identifier."""
    # Get client IP, handling proxies
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    # Hash the IP to create a network identifier
    # This groups all clients on the same network together
    return hashlib.sha256(client_ip.encode()).hexdigest()[:16]


@router.get("/nearby", response_model=NearbySessionsResponse)
async def get_nearby_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Get sessions on the same network (nearby).
    This uses the client's IP address to find sessions created from the same network.
    """
    network_hash = get_client_network_hash(request)
    
    # Find active sessions on the same network with eager loading of participants
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.participants))
        .where(Session.network_hash == network_hash)
        .where(Session.expires_at > datetime.utcnow())
        .where(Session.status != SessionStatus.COMPLETED)
        .order_by(Session.created_at.desc())
    )
    sessions = result.scalars().all()
    
    nearby_sessions = []
    for session in sessions:
        # Find the host
        host = next((p for p in session.participants if p.is_host), None)
        host_name = host.name if host else "Unknown"
        
        nearby_sessions.append(NearbySession(
            code=session.code,
            host_name=host_name,
            participant_count=len(session.participants),
            status=session.status,
            created_at=session.created_at
        ))
    
    return NearbySessionsResponse(sessions=nearby_sessions)


@router.post("", status_code=201, response_model=SessionResponse)
async def create_session(
    session_data: SessionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Create a new session and add the host as the first participant."""
    network_hash = get_client_network_hash(request)
    service = SessionService(db)
    session = await service.create_session(session_data.host_name, network_hash=network_hash)
    return session


@router.get("/{code}", response_model=SessionResponse)
async def get_session(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a session by its code."""
    service = SessionService(db)
    session = await service.get_session_by_code(code)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session


@router.delete("/{code}", status_code=204)
async def delete_session(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a session."""
    service = SessionService(db)
    deleted = await service.delete_session(code)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return Response(status_code=204)


@router.post("/{code}/receipt")
async def upload_receipt(
    code: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a receipt image and extract items using OCR.
    
    This will:
    1. Save the image
    2. Run OCR to extract text
    3. Parse the text into items
    4. Add the items to the session
    """
    settings = get_settings()
    service = SessionService(db)
    session = await service.get_session_by_code(code)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed. Use JPEG, PNG, or WebP."
        )
    
    # Check file size before reading (if available from headers)
    if file.size and file.size > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB."
        )
    
    # Read file content with size limit
    max_size = settings.max_upload_size_bytes
    chunks = []
    total_size = 0
    
    while True:
        chunk = await file.read(8192)  # Read in 8KB chunks
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB."
            )
        chunks.append(chunk)
    
    image_bytes = b"".join(chunks)
    logger.info(f"Processing receipt upload for session {code}", extra={"file_size": total_size})
    
    # Prepare uploads directory using config
    uploads_dir = Path(settings.uploads_dir)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize file extension (prevent path traversal)
    if file.filename:
        # Extract only the extension, sanitize it
        raw_ext = Path(file.filename).suffix.lower()
        # Only allow known safe extensions
        safe_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        file_ext = raw_ext if raw_ext in safe_extensions else ".jpg"
    else:
        file_ext = ".jpg"
    
    # Generate safe filename (no user input in path)
    filename = f"{session.id}_{uuid.uuid4().hex[:8]}{file_ext}"
    filepath = uploads_dir / filename
    
    # Write file asynchronously
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(image_bytes)
    
    # Update session with image path
    session.receipt_image_path = str(filepath)
    session.status = SessionStatus.PROCESSING
    await db.commit()
    
    try:
        # Process with OCR
        ocr_service = OCRService()
        result = await ocr_service.process_receipt(image_bytes)
        
        # Save raw OCR text
        session.raw_ocr_text = result["raw_text"]
        
        # Add extracted items to session
        # Split items with quantity > 1 into individual items for easier assignment
        position = 0
        total_items = 0
        for item_data in result["items"]:
            quantity = item_data["quantity"]
            price = Decimal(item_data["price"])
            
            # For items with quantity > 1, split into individual items
            # Calculate per-item price
            if quantity > 1 and not item_data["is_tax"] and not item_data["is_tip_suggestion"]:
                per_item_price = (price / quantity).quantize(Decimal('0.01'))
                # Handle rounding - last item gets any remainder
                remainder = price - (per_item_price * quantity)
                
                for j in range(quantity):
                    item_price = per_item_price
                    if j == quantity - 1:  # Last item gets remainder
                        item_price = per_item_price + remainder
                    
                    item = Item(
                        session_id=session.id,
                        name=item_data["name"],
                        price=item_price,
                        quantity=1,
                        is_tax=False,
                        is_tip_suggestion=False,
                        position=position,
                    )
                    db.add(item)
                    position += 1
                    total_items += 1
            else:
                # Single item or tax/tip - add as-is
                item = Item(
                    session_id=session.id,
                    name=item_data["name"],
                    price=price,
                    quantity=1,
                    is_tax=item_data["is_tax"],
                    is_tip_suggestion=item_data["is_tip_suggestion"],
                    position=position,
                )
                db.add(item)
                position += 1
                total_items += 1
        
        session.status = SessionStatus.READY
        await db.commit()
        
        return {
            "message": "Receipt processed successfully",
            "items_found": total_items,
            "raw_text": result["raw_text"],
            "summary": result["summary"],
        }
        
    except Exception as e:
        session.status = SessionStatus.PENDING
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process receipt: {str(e)}"
        )


@router.get("/{code}/qr")
async def get_session_qr(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get a QR code image for the session."""
    service = SessionService(db)
    session = await service.get_session_by_code(code)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build base URL from request headers (handles proxies like Cloudflare)
    # Check for forwarded headers first (set by reverse proxies)
    forwarded_proto = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    forwarded_host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", request.url.netloc))
    
    base_url = f"{forwarded_proto}://{forwarded_host}"
    
    qr_service = QRService(base_url=base_url)
    qr_image = qr_service.generate_session_qr(session.code)
    
    return Response(content=qr_image, media_type="image/png")


@router.get("/{code}/summary", response_model=SessionSummary)
async def get_session_summary(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the bill split summary for a session."""
    service = SessionService(db)
    session = await service.get_session_by_code(code)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build data structures for calculator
    items = []
    for item in session.items:
        items.append(type('Item', (), {
            'id': item.id,
            'name': item.name,
            'price': item.price,
            'quantity': item.quantity,
            'is_tax': item.is_tax,
            'is_tip_suggestion': item.is_tip_suggestion,
        })())
    
    participants = []
    for p in session.participants:
        participants.append(type('Participant', (), {
            'id': p.id,
            'name': p.name,
            'tip_percentage': p.tip_percentage,
            'tip_amount': p.tip_amount,
        })())
    
    # Flatten all assignments
    assignments = []
    for item in session.items:
        for assignment in item.assignments:
            assignments.append(type('Assignment', (), {
                'item_id': assignment.item_id,
                'participant_id': assignment.participant_id,
                'share_count': assignment.share_count,
            })())
    
    # Build discounts list
    discounts = []
    for d in session.discounts:
        discounts.append(type('Discount', (), {
            'id': d.id,
            'name': d.name,
            'discount_type': d.discount_type.value,  # Convert enum to string
            'value': d.value,
            'participant_id': d.participant_id,
        })())
    
    # Calculate split
    calculator = BillCalculator()
    result = calculator.calculate_full_split(items, participants, assignments, discounts)
    
    # Calculate totals
    receipt_total = sum(
        item.price * item.quantity 
        for item in session.items 
        if not item.is_tip_suggestion
    )
    tax_total = sum(
        item.price * item.quantity 
        for item in session.items 
        if item.is_tax
    )
    
    # Build participant summaries
    participant_summaries = []
    for p in session.participants:
        if p.id in result:
            p_data = result[p.id]
            participant_summaries.append(ParticipantSummary(
                participant_id=p.id,
                participant_name=p.name,
                items_subtotal=p_data["items_subtotal"],
                tax_share=p_data["tax_share"],
                tip_amount=p_data["tip_amount"],
                discount_amount=p_data.get("discount_amount", 0),
                total=p_data["total"],
                items=p_data["items"],
                applied_discounts=p_data.get("applied_discounts", []),
            ))
    
    # Get unassigned items
    unassigned = result.get("unassigned_items", [])
    total_discount = result.get("total_discount", 0)
    
    calculated_total = sum(ps.total for ps in participant_summaries)
    
    return SessionSummary(
        session_id=session.id,
        session_code=session.code,
        receipt_total=receipt_total,
        tax_total=tax_total,
        total_discount=total_discount,
        calculated_total=calculated_total,
        participants=participant_summaries,
        unassigned_items=unassigned,
    )
