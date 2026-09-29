from .models import Notification

def notifications_context(request):
    """
    Context processor to provide real-time notification data across all views:
    - unread_notifications: list of latest unread notifications for current user
    - unread_notifications_count: total number of unread notifications
    - recent_notifications: latest 5 notifications regardless of read status
    """
    if not hasattr(request, "user") or not request.user or not request.user.is_authenticated:
        return {
            "unread_notifications": [],
            "unread_notifications_count": 0,
            "recent_notifications": [],
        }

    user = request.user
    unread_qs = Notification.objects.filter(recipient_user=user, is_read=False).order_by("-created_at")
    unread_count = unread_qs.count()
    unread_list = list(unread_qs[:5])
    recent_list = list(Notification.objects.filter(recipient_user=user).order_by("-created_at")[:5])

    return {
        "unread_notifications": unread_list,
        "unread_notifications_count": unread_count,
        "recent_notifications": recent_list,
    }
