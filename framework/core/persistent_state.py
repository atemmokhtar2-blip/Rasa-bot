from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from framework.core.state import Session, SessionManager
from framework.infrastructure.sql import SQLDatabase, SessionORM

class PersistentSessionManager(SessionManager):
    def __init__(self, database: SQLDatabase, timeout_minutes: int = 30):
        super().__init__(timeout_minutes)
        self.database = database

    @staticmethod
    def _to_domain(row: SessionORM) -> Session:
        return Session(project_id=row.project_id, user_id=row.user_id, conversation_id=row.conversation_id, id=row.id, state=row.state, context=dict(row.context or {}), dialogue=list(row.dialogue or []), created_at=row.created_at, updated_at=row.updated_at)

    async def get_or_create(self, project_id: str, user_id: str, conversation_id: str) -> Session:
        async with self.database.session() as db:
            row = (await db.execute(select(SessionORM).where(SessionORM.project_id == project_id, SessionORM.user_id == user_id, SessionORM.conversation_id == conversation_id))).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row is None or now - row.updated_at > self.timeout or row.state == "ended":
                row = SessionORM(id=__import__('uuid').uuid4().hex, project_id=project_id, user_id=user_id, conversation_id=conversation_id, state="active", context={}, dialogue=[], created_at=now, updated_at=now)
                db.add(row)
            else:
                row.updated_at = now
            await db.commit()
            return self._to_domain(row)

    async def update(self, session: Session, **changes) -> Session:
        async with self.database.session() as db:
            row = await db.get(SessionORM, session.id)
            if row is None: raise KeyError(f"Session not found: {session.id}")
            for key, value in changes.items():
                if key == "context": row.context = value
                elif key == "state": row.state = value
                elif key == "dialogue": row.dialogue = value
            row.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return self._to_domain(row)

    async def end(self, session: Session) -> None:
        await self.update(session, state="ended")
