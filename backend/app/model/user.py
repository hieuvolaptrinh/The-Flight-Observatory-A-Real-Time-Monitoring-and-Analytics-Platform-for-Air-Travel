from sqlmodel import Field

from app.model.base_model import BaseModel


class User(BaseModel, table=True):
    __tablename__ = "users"

    address: str | None = Field(default=None, nullable=True)
    secondary_address: str | None = Field(default=None, nullable=True)
    third_address: str | None = Field(default=None, nullable=True)
    email: str = Field(
        unique=True,
        index=True,
        max_length=255,
    )
    password: str = Field()
    business_name: str = Field(default=None, nullable=True)
    company_size: int | None = Field(default=None, nullable=True)
    logo_img_url: str | None = Field(default=None, nullable=True)
    website_url: str | None = Field(default=None, nullable=True)
    business_owner_name: str | None = Field(default=None, nullable=True)
    mobile_number: str | None = Field(
        default=None,
        nullable=True,
    )
    phone_number: str = Field()
    region: str | None = Field(
        default=None,
        max_length=100,
    )
    tax_number: str | None = Field(
        default=None,
        max_length=100,
        nullable=True,
        index=True,
    )
