"""
WhatsApp Manager for SSCP Desktop (Honest Option 1: 1-Clic Real Mode).
Stores the clinic's reference phone without faking background socket connections
or unattended message delivery.
"""
import json
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, Optional

from app.database import DATA_DIR

SESSION_FILE = DATA_DIR / "whatsapp_session.json"


class WhatsAppGatewayManager:
    """Manages local WhatsApp 1-Clic reference configuration and telemetry."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WhatsAppGatewayManager, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        self.status = "manual_only"
        self.connected_phone: Optional[str] = None
        self.connected_at: Optional[str] = None
        self.last_activity: Optional[str] = None
        self.last_error: Optional[str] = None
        self.messages_sent_count = 0
        self.messages_sent_today = 0
        self._count_date: Optional[str] = None
        self._load_saved_session()

    def _load_saved_session(self):
        """Loads persisted reference config if present on disk (never forces fake 'connected')."""
        try:
            if SESSION_FILE.exists():
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        phone = (data.get("phone") or "").strip() or None
                        self.connected_phone = phone
                        self.connected_at = data.get("connected_at")
                        self.last_activity = data.get("last_activity") or data.get("updated_at")
                        self.messages_sent_count = int(data.get("messages_sent_count") or 0)
                        today_iso = date.today().isoformat()
                        if data.get("count_date") == today_iso:
                            self.messages_sent_today = int(data.get("messages_sent_today") or 0)
                            self._count_date = today_iso
        except Exception as e:
            print(f"[WhatsApp 1-Clic] Aviso al cargar configuración: {e}")

    def _save_session(self):
        """Persists reference phone and honest manual_only mode on disk."""
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "is_connected": False,
                        "status": "manual_only",
                        "mode": "wa_link",
                        "phone": self.connected_phone,
                        "connected_at": self.connected_at,
                        "last_activity": self.last_activity,
                        "messages_sent_count": self.messages_sent_count,
                        "messages_sent_today": self.messages_sent_today,
                        "count_date": self._count_date or date.today().isoformat(),
                        "updated_at": datetime.now().isoformat(),
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            print(f"[WhatsApp 1-Clic] Aviso al guardar configuración: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns honest 1-Clic status (never claims simulated gateway delivery)."""
        return {
            "status": "manual_only",
            "is_connected": False,
            "mode": "wa_link",
            "mode_label": "Modo 1-Clic Real (WhatsApp del Doctor)",
            "connected_phone": self.connected_phone,
            "connected_at": self.connected_at,
            "has_active_qr": False,
            "messages_sent_count": self.messages_sent_count,
            "messages_sent_today": self.messages_sent_today,
            "last_activity": self.last_activity,
            "last_error": self.last_error,
            "fallback_channel": "wa_me_direct",
        }

    def generate_pairing_qr(self, custom_phone: Optional[str] = None) -> Dict[str, Any]:
        """In Option 1, QR gateway pairing is retired in favor of honest 1-Clic links."""
        self.status = "manual_only"
        self.last_error = None
        return {
            "success": True,
            "mode": "wa_link",
            "status": "manual_only",
            "is_connected": False,
            "qr_image": None,
            "qr_image_base64": None,
            "detail": "SSCP opera en Modo 1-Clic Real desde el WhatsApp del propio doctor.",
        }

    def confirm_pairing(self, phone: str = "") -> Dict[str, Any]:
        """Stores the clinic/secretary reference phone under honest manual_only mode."""
        cleaned = (phone or "").strip() or None
        self.status = "manual_only"
        self.connected_phone = cleaned
        self.connected_at = datetime.now().strftime("%d/%m/%Y %H:%M") if cleaned else None
        self.last_activity = datetime.now().isoformat()
        self._save_session()

        return {
            "success": True,
            "mode": "wa_link",
            "status": "manual_only",
            "is_connected": False,
            "connected_phone": self.connected_phone,
            "phone": self.connected_phone,
            "connected_at": self.connected_at,
        }

    def record_confirmed_send(self) -> None:
        """Tracks confirmed 1-Clic sends without affecting gateway connection honesty."""
        today_iso = date.today().isoformat()
        if self._count_date != today_iso:
            self._count_date = today_iso
            self.messages_sent_today = 0
        self.messages_sent_today += 1
        self.messages_sent_count += 1
        self.last_activity = datetime.now().isoformat()
        self._save_session()

    def disconnect(self) -> Dict[str, Any]:
        """Clears the stored reference clinic phone."""
        self.status = "manual_only"
        self.connected_phone = None
        self.connected_at = None
        self.last_activity = datetime.now().isoformat()
        self._save_session()
        return {
            "success": True,
            "mode": "wa_link",
            "status": "manual_only",
            "is_connected": False,
            "connected_phone": None,
        }

    def send_message(self, phone: str, message: str) -> Dict[str, Any]:
        """Unattended gateway sending is disabled in Option 1."""
        return {
            "success": False,
            "mode": "wa_link",
            "status": "manual_only",
            "error": "El envío desatendido está deshabilitado. Utiliza el enlace WhatsApp 1-Clic.",
        }


# Singleton instance accessible across the app
gateway_manager = WhatsAppGatewayManager()
