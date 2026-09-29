from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Notification
from .services import NotificationService

@login_required
def mark_read_and_redirect_view(request, notification_id):
    """
    Marks a notification as read and forwards to its action_url if provided.
    """
    notif = get_object_or_404(Notification, id=notification_id, recipient_user=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read", "updated_at"])
    
    if notif.action_url:
        return redirect(notif.action_url)
    return redirect(request.META.get("HTTP_REFERER", "dashboard"))

@login_required
def mark_all_read_view(request):
    """
    Marks all notifications for the user as read.
    """
    NotificationService.mark_all_as_read(request.user)
    return redirect(request.META.get("HTTP_REFERER", "dashboard"))
