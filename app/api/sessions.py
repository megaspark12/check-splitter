"""
Sessions API routes.

Handles session creation, retrieval, QR codes, summaries, and WebSocket connections.
"""
from __future__ import annotations

import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Request, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.logging_config import get_logger
from app.schemas.session import SessionCreate, SessionResponse, SessionSummary, ParticipantSummary, NearbySession, NearbySessionsResponse
from app.services.session_service import SessionService
from app.services.qr_service import QRService
from app.services.calculator import BillCalculator
from app.services.ocr_service import OCRService
from app.services.storage_service import get_storage_backend
from app.services.geolocation import create_location_hash, get_geohash_neighbors
from app.models.item import Item
from app.models.discount import Discount, DiscountType
from app.models.session import Session, SessionStatus
from app.api.dependencies import require_host_token, get_session_or_404
from app.websocket_manager import manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = get_logger("api.sessions")


# Adapter dataclasses for BillCalculator (prefixed with _ to avoid pytest collection)
@dataclass
class _Item:
    id: str
    name: str
    price: Decimal
    quantity: int
    is_tax: bool
    is_tip_suggestion: bool
    is_refund: bool


@dataclass
class _Participant:
    id: str
    name: str
    tip_percentage: Decimal | None
    tip_amount: Decimal | None


@dataclass
class _Assignment:
    item_id: str
    participant_id: str
    share_count: int


@dataclass
class _Discount:
    id: str
    name: str
    discount_type: str
    value: Decimal
    participant_id: str | None


@router.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str):
    """
    WebSocket endpoint for real-time session updates.
    
    Clients connect to receive instant notifications when session data changes.
    When a notification is received, clients should fetch the latest data.
    """
    session_code = code.upper()
    await manager.connect(websocket, session_code)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_code": session_code,
        })
        
        # Keep connection alive and listen for client messages
        while True:
            try:
                # Wait for any message from client (ping/pong or disconnect)
                data = await websocket.receive_text()
                
                # Client can send ping to keep alive
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                break
                
    except Exception as e:
        logger.error(f"WebSocket error for session {session_code}: {e}")
    finally:
        await manager.disconnect(websocket, session_code)


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
    lat: float | None = Query(None, ge=-90, le=90, description="GPS latitude"),
    lng: float | None = Query(None, ge=-180, le=180, description="GPS longitude"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get sessions nearby.
    
    Matches sessions by:
    1. Same network (IP-based) - automatic, no permission needed
    2. Same location (GPS-based) - if lat/lng provided, requires location permission
    
    Both methods are combined with OR logic to maximize discovery.
    """
    network_hash = get_client_network_hash(request)
    
    # Build query conditions
    conditions = [Session.network_hash == network_hash]
    
    # If location provided, also match by geohash (including neighbor cells)
    if lat is not None and lng is not None:
        try:
            location_hash = create_location_hash(lat, lng)
            neighbor_hashes = get_geohash_neighbors(location_hash)
            conditions.append(Session.location_hash.in_(neighbor_hashes))
        except ValueError:
            pass
    
    # Find active sessions matching either network OR location
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.participants))
        .where(or_(*conditions))
        .where(Session.expires_at > datetime.now(timezone.utc))
        .where(Session.status != SessionStatus.COMPLETED)
        .order_by(Session.created_at.desc())
    )
    sessions = result.scalars().all()
    
    # Deduplicate (a session could match both network and location)
    seen_codes = set()
    nearby_sessions = []
    for session in sessions:
        if session.code in seen_codes:
            continue
        seen_codes.add(session.code)
        
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
    
    # Generate location hash if coordinates provided
    location_hash = None
    if session_data.latitude is not None and session_data.longitude is not None:
        try:
            location_hash = create_location_hash(session_data.latitude, session_data.longitude)
        except ValueError:
            pass
    
    service = SessionService(db)
    session, host_token = await service.create_session(
        session_data.host_name, 
        network_hash=network_hash,
        location_hash=location_hash
    )
    
    # Build response with host_token included (only on creation)
    response_data = SessionResponse.model_validate(session)
    response_data.host_token = host_token
    return response_data


@router.patch("/{code}/location")
async def update_session_location(
    code: str,
    request: Request,
    session: Session = Depends(require_host_token),
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db)
):
    """Update a session's location hash. Requires host token. Called when host grants location after session creation."""
    try:
        location_hash = create_location_hash(lat, lng)
        session.location_hash = location_hash
        await db.commit()
        return {"status": "ok", "location_hash": location_hash}
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid coordinates")


@router.get("/{code}", response_model=SessionResponse)
async def get_session(
    code: str,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """Get a session by its code."""
    return session


@router.delete("/{code}", status_code=204)
async def delete_session(
    code: str,
    session: Session = Depends(require_host_token),
    db: AsyncSession = Depends(get_db)
):
    """Delete a session. Requires host token."""
    service = SessionService(db)
    deleted = await service.delete_session(code)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return Response(status_code=204)


@router.post("/{code}/receipt")
async def upload_receipt(
    code: str,
    session: Session = Depends(require_host_token),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a receipt image and extract items using OCR. Requires host token.
    
    This will:
    1. Save the image
    2. Run OCR to extract text
    3. Parse the text into items
    4. Add the items to the session
    """
    settings = get_settings()
    
    # Session is already validated by require_host_token dependency
    
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
    
    # Save via storage backend (local or GCS)
    storage = get_storage_backend()
    filepath = await storage.save(image_bytes, filename)
    
    # Update session with image path
    session.receipt_image_path = filepath
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
            is_refund = item_data.get("is_refund", False)
            
            # For items with quantity > 1, split into individual items
            # Calculate per-item price (skip splitting for tax/tip/refund items)
            if quantity > 1 and not item_data["is_tax"] and not item_data["is_tip_suggestion"] and not is_refund:
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
                        is_refund=False,
                        position=position,
                    )
                    db.add(item)
                    position += 1
                    total_items += 1
            else:
                # Single item, tax/tip, or refund — add as-is
                item = Item(
                    session_id=session.id,
                    name=item_data["name"],
                    price=price,
                    quantity=1,
                    is_tax=item_data["is_tax"],
                    is_tip_suggestion=item_data["is_tip_suggestion"],
                    is_refund=is_refund,
                    position=position,
                )
                db.add(item)
                position += 1
                total_items += 1
        
        # Auto-create Discount records from OCR-extracted discounts
        discounts_created = 0
        for disc_data in result.get("discounts", []):
            disc_type = (
                DiscountType.PERCENTAGE 
                if disc_data["type"] == "percentage" 
                else DiscountType.FIXED
            )
            discount = Discount(
                session_id=session.id,
                participant_id=None,  # Bill-wide discount
                name=disc_data["name"],
                discount_type=disc_type,
                value=Decimal(disc_data["value"]),
            )
            db.add(discount)
            discounts_created += 1
        
        # Handle edge case: no items detected
        if total_items == 0:
            session.status = SessionStatus.PENDING
            await db.commit()
            raise HTTPException(
                status_code=422,
                detail="No receipt items detected. Please try a clearer photo, or add items manually."
            )
        
        session.status = SessionStatus.READY
        await db.commit()
        
        # Notify all connected clients about new items
        await manager.notify_session_update(code.upper())
        
        # Build response
        response_data = {
            "message": "Receipt processed successfully",
            "items_found": total_items,
            "discounts_found": discounts_created,
            "raw_text": result["raw_text"],
            "summary": result["summary"],
            "mismatch_retried": result.get("mismatch_retried", False),
        }
        
        # Include warnings if any
        warnings = result.get("warnings", [])
        if warnings:
            response_data["warnings"] = warnings
        
        return response_data
        
    except HTTPException:
        raise
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
    
    items = [
        _Item(
            id=item.id,
            name=item.name,
            price=item.price,
            quantity=item.quantity,
            is_tax=item.is_tax,
            is_tip_suggestion=item.is_tip_suggestion,
            is_refund=item.is_refund,
        )
        for item in session.items
    ]
    
    participants = [
        _Participant(
            id=p.id,
            name=p.name,
            tip_percentage=p.tip_percentage,
            tip_amount=p.tip_amount,
        )
        for p in session.participants
    ]
    
    # Flatten all assignments
    assignments = [
        _Assignment(
            item_id=assignment.item_id,
            participant_id=assignment.participant_id,
            share_count=assignment.share_count,
        )
        for item in session.items
        for assignment in item.assignments
    ]
    
    # Build discounts list
    discounts = [
        _Discount(
            id=d.id,
            name=d.name,
            discount_type=d.discount_type.value,  # Convert enum to string
            value=d.value,
            participant_id=d.participant_id,
        )
        for d in session.discounts
    ]
    
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
