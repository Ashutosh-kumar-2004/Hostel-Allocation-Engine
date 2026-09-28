from django.shortcuts import render
from .models import AuditEntry

def audit_log_view(request):
    entries = AuditEntry.objects.all()[:100]
    return render(request, "audit/log.html", {"entries": entries})
