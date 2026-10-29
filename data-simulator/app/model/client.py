from sqlmodel import Field

from app.model.base_model import BaseModel


class Client(BaseModel, table=True):
    __tablename__ = "client"

    user_id: int = Field(
        foreign_key="users.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    client_name: str = Field(max_length=255)
    email: str | None = Field(
        default=None,
        max_length=255,
    )
    secondary_emails: str | None = Field(
        default=None,
        max_length=255,
    )
    mobile_number: str | None = Field(
        default=None,
        max_length=12,
    )
    phone_number: str | None = Field(
        default=None,
        max_length=12,
    )
    fax: str | None = Field(
        default=None,
        max_length=30,
    )
