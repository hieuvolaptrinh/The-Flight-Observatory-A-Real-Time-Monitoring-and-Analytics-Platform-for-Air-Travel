from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy.orm import Session

from app.core.exceptions_handler import NotFoundError
from app.model.user import User
from app.repository.base_repository import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self.session_factory = session_factory
        super().__init__(session_factory, User)

    def find_by_email(self, email: str) -> User | None:
        with self.session_factory() as session:
            return session.query(User).filter(User.email == email).first()

    def update_profile(self, user_id: int, data: dict) -> User:
        with self.session_factory() as session:
            user = session.query(User).filter(User.id == user_id).first()

            if user is None:
                raise NotFoundError("User not found")

            for field, value in data.items():
                setattr(user, field, value)

            session.commit()
            session.refresh(user)

            return user
