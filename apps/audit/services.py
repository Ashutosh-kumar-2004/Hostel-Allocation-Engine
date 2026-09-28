from typing import Optional, Dict, Any
from .models import AuditEntry

class AuditService:
    @staticmethod
    def record_action(
        action: str,
        target_entity: str,
        target_id: str,
        actor_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        reason: str = "",
        ip_address: Optional[str] = None,
        institution_id: str = "inst_default"
    ) -> AuditEntry:
        return AuditEntry.objects.create(
            action=action,
            target_entity=target_entity,
            target_id=str(target_id),
            actor_id=actor_id,
            actor_email=actor_email,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
            ip_address=ip_address,
            institution_id=institution_id
        )
