from app.repositories.crm_repository import CRMRepository


class AdminOnlyCRMRepository(CRMRepository):
    """Allow CRM activity scheduling only for users with the admin role."""

    @property
    def can_schedule_activities(self) -> bool:
        return str(self.current_user.role).strip().lower() == "admin"

    def schedule(
        self,
        lead_id: int,
        kind: str,
        subject: str,
        notes: str,
        due_local: str,
        priority: str,
        owner: int | None,
    ) -> None:
        if not self.can_schedule_activities:
            raise ValueError("جدولة الأنشطة متاحة للأدمن فقط")
        super().schedule(
            lead_id,
            kind,
            subject,
            notes,
            due_local,
            priority,
            owner,
        )


__all__ = ["AdminOnlyCRMRepository"]
