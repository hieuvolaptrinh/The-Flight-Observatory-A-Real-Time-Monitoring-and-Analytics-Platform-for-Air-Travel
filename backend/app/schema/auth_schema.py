from datetime import datetime
from typing import Annotated

from fastapi import Form
from pydantic import BaseModel, EmailStr, Field


class SignIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=255)


class SignUp(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=255)
    phone_number: str = Field(min_length=1, max_length=30)
    address: str | None = None
    secondary_address: str | None = None
    third_address: str | None = None
    business_name: str | None = None
    company_size: int | None = Field(default=None, ge=0)
    website_url: str | None = None
    business_owner_name: str | None = None
    mobile_number: str | None = None
    region: str | None = None
    tax_number: str | None = None

    @classmethod
    def as_form(
        cls,
        email: Annotated[EmailStr, Form()],
        password: Annotated[str, Form(min_length=6, max_length=255)],
        phone_number: Annotated[str, Form(min_length=1, max_length=30)],
        address: Annotated[str | None, Form()] = None,
        secondary_address: Annotated[str | None, Form()] = None,
        third_address: Annotated[str | None, Form()] = None,
        business_name: Annotated[str | None, Form()] = None,
        company_size: Annotated[int | None, Form(ge=0)] = None,
        website_url: Annotated[str | None, Form()] = None,
        business_owner_name: Annotated[str | None, Form()] = None,
        mobile_number: Annotated[str | None, Form()] = None,
        region: Annotated[str | None, Form()] = None,
        tax_number: Annotated[str | None, Form()] = None,
    ) -> "SignUp":
        return cls(
            email=email,
            password=password,
            phone_number=phone_number,
            address=address,
            secondary_address=secondary_address,
            third_address=third_address,
            business_name=business_name,
            company_size=company_size,
            website_url=website_url,
            business_owner_name=business_owner_name,
            mobile_number=mobile_number,
            region=region,
            tax_number=tax_number,
        )


class UpdateUser(BaseModel):
    email: EmailStr | None = None
    phone_number: str | None = Field(default=None, min_length=1, max_length=30)
    address: str | None = None
    secondary_address: str | None = None
    third_address: str | None = None
    business_name: str | None = None
    company_size: int | None = Field(default=None, ge=0)
    website_url: str | None = None
    business_owner_name: str | None = None
    mobile_number: str | None = None
    region: str | None = Field(default=None, max_length=100)
    tax_number: str | None = Field(default=None, max_length=100)

    @classmethod
    def as_form(
        cls,
        email: Annotated[EmailStr | None, Form()] = None,
        phone_number: Annotated[str | None, Form(min_length=1, max_length=30)] = None,
        address: Annotated[str | None, Form()] = None,
        secondary_address: Annotated[str | None, Form()] = None,
        third_address: Annotated[str | None, Form()] = None,
        business_name: Annotated[str | None, Form()] = None,
        company_size: Annotated[int | None, Form(ge=0)] = None,
        website_url: Annotated[str | None, Form()] = None,
        business_owner_name: Annotated[str | None, Form()] = None,
        mobile_number: Annotated[str | None, Form()] = None,
        region: Annotated[str | None, Form(max_length=100)] = None,
        tax_number: Annotated[str | None, Form(max_length=100)] = None,
    ) -> "UpdateUser":
        values = {
            "email": email,
            "phone_number": phone_number,
            "address": address,
            "secondary_address": secondary_address,
            "third_address": third_address,
            "business_name": business_name,
            "company_size": company_size,
            "website_url": website_url,
            "business_owner_name": business_owner_name,
            "mobile_number": mobile_number,
            "region": region,
            "tax_number": tax_number,
        }
        return cls(**{key: value for key, value in values.items() if value is not None})


class Payload(BaseModel):
    id: int
    email: str


class UserResponse(BaseModel):
    id: int
    created_at: datetime | None
    updated_at: datetime | None
    address: str | None
    secondary_address: str | None
    third_address: str | None
    email: str
    business_name: str | None
    company_size: int | None
    logo_img_url: str | None
    website_url: str | None
    business_owner_name: str | None
    mobile_number: str | None
    phone_number: str
    region: str | None
    tax_number: str | None


class SignInResponse(BaseModel):
    access_token: str
    expiration: str
    user_info: UserResponse
