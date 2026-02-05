"""
Utility API routes.

Handles utility functions like currency inference.
"""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["utilities"])

# Currency mapping by country code
COUNTRY_CURRENCIES = {
    # Middle East
    "IL": {"code": "ILS", "symbol": "₪", "name": "Israeli Shekel"},
    "AE": {"code": "AED", "symbol": "د.إ", "name": "UAE Dirham"},
    "SA": {"code": "SAR", "symbol": "ر.س", "name": "Saudi Riyal"},
    
    # North America
    "US": {"code": "USD", "symbol": "$", "name": "US Dollar"},
    "CA": {"code": "CAD", "symbol": "C$", "name": "Canadian Dollar"},
    "MX": {"code": "MXN", "symbol": "$", "name": "Mexican Peso"},
    
    # Europe
    "GB": {"code": "GBP", "symbol": "£", "name": "British Pound"},
    "DE": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "FR": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "IT": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "ES": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "NL": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "BE": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "AT": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "IE": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "PT": {"code": "EUR", "symbol": "€", "name": "Euro"},
    "CH": {"code": "CHF", "symbol": "CHF", "name": "Swiss Franc"},
    "SE": {"code": "SEK", "symbol": "kr", "name": "Swedish Krona"},
    "NO": {"code": "NOK", "symbol": "kr", "name": "Norwegian Krone"},
    "DK": {"code": "DKK", "symbol": "kr", "name": "Danish Krone"},
    "PL": {"code": "PLN", "symbol": "zł", "name": "Polish Zloty"},
    "CZ": {"code": "CZK", "symbol": "Kč", "name": "Czech Koruna"},
    "HU": {"code": "HUF", "symbol": "Ft", "name": "Hungarian Forint"},
    "RU": {"code": "RUB", "symbol": "₽", "name": "Russian Ruble"},
    
    # Asia Pacific
    "JP": {"code": "JPY", "symbol": "¥", "name": "Japanese Yen"},
    "CN": {"code": "CNY", "symbol": "¥", "name": "Chinese Yuan"},
    "KR": {"code": "KRW", "symbol": "₩", "name": "South Korean Won"},
    "IN": {"code": "INR", "symbol": "₹", "name": "Indian Rupee"},
    "AU": {"code": "AUD", "symbol": "A$", "name": "Australian Dollar"},
    "NZ": {"code": "NZD", "symbol": "NZ$", "name": "New Zealand Dollar"},
    "SG": {"code": "SGD", "symbol": "S$", "name": "Singapore Dollar"},
    "HK": {"code": "HKD", "symbol": "HK$", "name": "Hong Kong Dollar"},
    "TW": {"code": "TWD", "symbol": "NT$", "name": "Taiwan Dollar"},
    "TH": {"code": "THB", "symbol": "฿", "name": "Thai Baht"},
    "MY": {"code": "MYR", "symbol": "RM", "name": "Malaysian Ringgit"},
    "PH": {"code": "PHP", "symbol": "₱", "name": "Philippine Peso"},
    "ID": {"code": "IDR", "symbol": "Rp", "name": "Indonesian Rupiah"},
    "VN": {"code": "VND", "symbol": "₫", "name": "Vietnamese Dong"},
    
    # South America
    "BR": {"code": "BRL", "symbol": "R$", "name": "Brazilian Real"},
    "AR": {"code": "ARS", "symbol": "$", "name": "Argentine Peso"},
    "CL": {"code": "CLP", "symbol": "$", "name": "Chilean Peso"},
    "CO": {"code": "COP", "symbol": "$", "name": "Colombian Peso"},
    
    # Africa
    "ZA": {"code": "ZAR", "symbol": "R", "name": "South African Rand"},
    "EG": {"code": "EGP", "symbol": "E£", "name": "Egyptian Pound"},
    "NG": {"code": "NGN", "symbol": "₦", "name": "Nigerian Naira"},
    "KE": {"code": "KES", "symbol": "KSh", "name": "Kenyan Shilling"},
}

# Default currency
DEFAULT_CURRENCY = {"code": "USD", "symbol": "$", "name": "US Dollar"}


@router.get("/currency")
async def get_currency(
    request: Request,
    country_code: str = None,
    timezone: str = None,
):
    """
    Infer the user's currency based on location.
    
    Priority:
    1. Explicit country_code parameter
    2. Timezone-based inference
    3. Accept-Language header
    4. Default to USD
    """
    # 1. If country code is provided explicitly
    if country_code:
        country_code = country_code.upper()
        if country_code in COUNTRY_CURRENCIES:
            return COUNTRY_CURRENCIES[country_code]
    
    # 2. Try timezone-based inference
    if timezone:
        tz_country = infer_country_from_timezone(timezone)
        if tz_country and tz_country in COUNTRY_CURRENCIES:
            return COUNTRY_CURRENCIES[tz_country]
    
    # 3. Try Accept-Language header
    accept_language = request.headers.get("Accept-Language", "")
    if accept_language:
        country = infer_country_from_language(accept_language)
        if country and country in COUNTRY_CURRENCIES:
            return COUNTRY_CURRENCIES[country]
    
    # 4. Default
    return DEFAULT_CURRENCY


def infer_country_from_timezone(timezone: str) -> str:
    """Infer country code from timezone string."""
    # Timezone to country mapping
    tz_mapping = {
        "Asia/Jerusalem": "IL",
        "Asia/Tel_Aviv": "IL",
        "America/New_York": "US",
        "America/Los_Angeles": "US",
        "America/Chicago": "US",
        "America/Denver": "US",
        "America/Toronto": "CA",
        "America/Vancouver": "CA",
        "Europe/London": "GB",
        "Europe/Paris": "FR",
        "Europe/Berlin": "DE",
        "Europe/Rome": "IT",
        "Europe/Madrid": "ES",
        "Europe/Amsterdam": "NL",
        "Europe/Brussels": "BE",
        "Europe/Vienna": "AT",
        "Europe/Dublin": "IE",
        "Europe/Lisbon": "PT",
        "Europe/Zurich": "CH",
        "Europe/Stockholm": "SE",
        "Europe/Oslo": "NO",
        "Europe/Copenhagen": "DK",
        "Europe/Warsaw": "PL",
        "Europe/Prague": "CZ",
        "Europe/Budapest": "HU",
        "Europe/Moscow": "RU",
        "Asia/Tokyo": "JP",
        "Asia/Shanghai": "CN",
        "Asia/Hong_Kong": "HK",
        "Asia/Singapore": "SG",
        "Asia/Seoul": "KR",
        "Asia/Taipei": "TW",
        "Asia/Bangkok": "TH",
        "Asia/Kolkata": "IN",
        "Asia/Dubai": "AE",
        "Asia/Riyadh": "SA",
        "Australia/Sydney": "AU",
        "Australia/Melbourne": "AU",
        "Pacific/Auckland": "NZ",
        "America/Mexico_City": "MX",
        "America/Sao_Paulo": "BR",
        "America/Argentina/Buenos_Aires": "AR",
        "Africa/Johannesburg": "ZA",
        "Africa/Cairo": "EG",
    }
    
    return tz_mapping.get(timezone, "")


def infer_country_from_language(accept_language: str) -> str:
    """Infer country code from Accept-Language header."""
    # Parse the first language preference
    # Format: en-US,en;q=0.9,he;q=0.8
    parts = accept_language.split(",")
    if parts:
        first_lang = parts[0].strip().split(";")[0]
        
        # Check for region code (e.g., en-US, he-IL)
        if "-" in first_lang:
            region = first_lang.split("-")[1].upper()
            if region in COUNTRY_CURRENCIES:
                return region
        
        # Map language to likely country
        lang_mapping = {
            "he": "IL",
            "en": "US",
            "de": "DE",
            "fr": "FR",
            "es": "ES",
            "it": "IT",
            "pt": "BR",
            "ja": "JP",
            "zh": "CN",
            "ko": "KR",
            "ru": "RU",
            "ar": "SA",
            "nl": "NL",
            "pl": "PL",
            "sv": "SE",
            "no": "NO",
            "da": "DK",
            "fi": "FI",
            "th": "TH",
            "vi": "VN",
        }
        
        lang_code = first_lang.split("-")[0].lower()
        return lang_mapping.get(lang_code, "")
    
    return ""
