from typing import Optional, List
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

class NotificationService:
    @staticmethod
    def send_in_app(
        recipient_user: User,
        subject: str,
        body: str,
        notification_type: str = "GENERAL",
        action_url: str = "",
        action_label: str = "Review Request & Profile",
        institution_id: str = "inst_default"
    ) -> Notification:
        """
        Creates and dispatches an in-app notification with an action link.
        """
        return Notification.objects.create(
            recipient_user=recipient_user,
            recipient_email=getattr(recipient_user, "email", "") or "",
            channel="IN_APP",
            notification_type=notification_type,
            subject=subject,
            body=body,
            action_url=action_url,
            action_label=action_label,
            is_read=False,
            is_sent=True,
            sent_at=timezone.now(),
            institution_id=institution_id
        )

    @staticmethod
    def get_unread_for_user(user: User, limit: int = 5) -> List[Notification]:
        """
        Returns latest unread notifications for a user.
        """
        if not user or not user.is_authenticated:
            return []
        return list(
            Notification.objects.filter(recipient_user=user, is_read=False)
            .order_by("-created_at")[:limit]
        )

    @staticmethod
    def get_all_for_user(user: User, limit: int = 20) -> List[Notification]:
        """
        Returns recent notifications for a user.
        """
        if not user or not user.is_authenticated:
            return []
        return list(
            Notification.objects.filter(recipient_user=user)
            .order_by("-created_at")[:limit]
        )

    @staticmethod
    def mark_as_read(notification_id: str, user: User) -> bool:
        """
        Marks a specific notification as read for the user.
        """
        if not user or not user.is_authenticated:
            return False
        updated = Notification.objects.filter(id=notification_id, recipient_user=user).update(is_read=True)
        return updated > 0

    @staticmethod
    def mark_all_as_read(user: User) -> int:
        """
        Marks all notifications as read for the user.
        """
        if not user or not user.is_authenticated:
            return 0
        return Notification.objects.filter(recipient_user=user, is_read=False).update(is_read=True)
