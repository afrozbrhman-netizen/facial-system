import datetime
from backend.models.database import db

class AuditService:
    """Enterprise Audit Logging & Notification Service for security compliance and tracking."""

    @staticmethod
    def log_action(action: str, user_id: int = None, username: str = None, 
                   entity_type: str = None, entity_id: str = None, 
                   details: str = None, ip_address: str = None):
        """Records an event in the audit_logs table."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO audit_logs (user_id, username, action, entity_type, entity_id, details, ip_address, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, username, action, entity_type, str(entity_id) if entity_id is not None else None, details, ip_address, now_str))
                conn.commit()
        except Exception as e:
            print(f"[AuditService] Failed to log action: {e}")

    @staticmethod
    def get_logs(limit: int = 100, offset: int = 0, action_filter: str = None, search: str = None) -> list:
        """Retrieves audit trail with filtering and pagination."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            query = "SELECT * FROM audit_logs WHERE 1=1"
            params = []

            if action_filter:
                query += " AND action = ?"
                params.append(action_filter)

            if search:
                query += " AND (username LIKE ? OR details LIKE ? OR entity_id LIKE ?)"
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def create_notification(title: str, message: str, user_id: int = None, notif_type: str = "info"):
        """Creates a system notification."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO notifications (user_id, title, message, type, is_read, created_at)
                    VALUES (?, ?, ?, ?, 0, ?)
                """, (user_id, title, message, notif_type, now_str))
                conn.commit()
        except Exception as e:
            print(f"[AuditService] Failed to create notification: {e}")

    @staticmethod
    def get_notifications(user_id: int = None, limit: int = 20) -> list:
        """Fetches notifications for a user or system-wide broadcast."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            query = "SELECT * FROM notifications WHERE (user_id = ? OR user_id IS NULL) ORDER BY created_at DESC LIMIT ?"
            cur.execute(query, (user_id, limit))
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def mark_all_read(user_id: int = None):
        """Marks all notifications as read."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            if user_id:
                cur.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? OR user_id IS NULL", (user_id,))
            else:
                cur.execute("UPDATE notifications SET is_read = 1")
            conn.commit()

audit_service = AuditService()
