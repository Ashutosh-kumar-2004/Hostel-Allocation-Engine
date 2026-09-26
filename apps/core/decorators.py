from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from apps.inventory.models import WardenHostelAssignment

def warden_or_admin_required(view_func):
    """
    Authoritative permission decorator:
    1. Rejects anonymous visitors (forces redirect to login).
    2. Allows Superusers and Staff.
    3. Strictly checks database-backed WardenHostelAssignment for the user.
       No guessable username substrings.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Authentication required: Please log in to access this console.")
            return redirect("login")

        if request.user.is_superuser or request.user.is_staff:
            return view_func(request, *args, **kwargs)

        # Authoritative database check
        warden_assign = WardenHostelAssignment.objects.filter(
            user=request.user
        ).first()
        if not warden_assign and request.user.email:
            warden_assign = WardenHostelAssignment.objects.filter(
                warden_email__iexact=request.user.email
            ).first()

        if not warden_assign:
            messages.error(request, "Access restricted: You must be an assigned Warden or Administrator to access this section.")
            return redirect("dashboard")

        # Attach assignment to request for downstream view consumption
        request.warden_assignment = warden_assign
        return view_func(request, *args, **kwargs)

    return _wrapped_view
