"""
QR Code generation service.

Generates QR codes for session sharing.
"""
import io
import qrcode
from qrcode.image.pil import PilImage


class QRService:
    """Service for generating QR codes."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    def generate_session_qr(self, session_code: str) -> bytes:
        """
        Generate a QR code PNG image for a session.
        
        Args:
            session_code: The session code to encode
            
        Returns:
            PNG image bytes
        """
        url = f"{self.base_url}/join/{session_code}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img: PilImage = qr.make_image(fill_color="black", back_color="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        return buffer.getvalue()
