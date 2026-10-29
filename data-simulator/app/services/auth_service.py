from datetime import timedelta

from fastapi import UploadFile

from app.core.config import configs
from app.core.exceptions_handler import AuthError
from app.core.security import create_access_token, get_password_hash, verify_password
from app.model.user import User
from app.repository.user_repository import UserRepository
from app.schema.auth_schema import SignIn, SignUp, UpdateUser
from app.services.storage_service import StorageService


def to_user_response(user: User) -> dict:
    return {
        "id": user.id,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "address": user.address,
        "secondary_address": user.secondary_address,
        "third_address": user.third_address,
        "email": user.email,
        "business_name": user.business_name,
        "company_size": user.company_size,
        "logo_img_url": user.logo_img_url,
        "website_url": user.website_url,
        "business_owner_name": user.business_owner_name,
        "mobile_number": user.mobile_number,
        "phone_number": user.phone_number,
        "region": user.region,
        "tax_number": user.tax_number,
    }


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        storage_service: StorageService,
    ):
        self.user_repository = user_repository
        self.storage_service = storage_service

    def sign_in(self, sign_in_info: SignIn) -> dict:
        user = self.user_repository.find_by_email(sign_in_info.email)
        if user is None or not verify_password(sign_in_info.password, user.password):
            raise AuthError(detail="Incorrect email or password")

        return self._create_auth_response(user)

    def _create_auth_response(self, user: User) -> dict:
        token_lifespan = timedelta(minutes=configs.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token, expiration = create_access_token(
            {"id": user.id, "email": user.email},
            token_lifespan,
        )
        return {
            "access_token": access_token,
            "expiration": expiration,
            "user_info": to_user_response(user),
        }

    def sign_up(self, user_info: SignUp, logo_file: UploadFile | None = None) -> dict:
        user_data = user_info.model_dump(exclude={"password"})
        if logo_file:
            user_data["logo_img_url"] = self.storage_service.upload_image(
                logo_file, "users/logos"
            )
        user = User(
            **user_data,
            password=get_password_hash(user_info.password),
        )
        created_user = self.user_repository.create(user)
        return self._create_auth_response(created_user)

    def update_profile(
        self, user_id: int, user_info: UpdateUser, logo_file: UploadFile | None = None
    ) -> dict:
        # chuyển thành dict nhưng chỉ lấy những field có giá trị khác None (nhớ là =true)
        update_data = user_info.model_dump(exclude_unset=True)
        if logo_file is not None:
            logo_url = self.storage_service.upload_image(logo_file, f"users/{user_id}")
            update_data["logo_img_url"] = logo_url

        if not update_data:
            raise ValueError("No data provided for update")

        updated_user = self.user_repository.update_profile(user_id, data=update_data)

        return to_user_response(updated_user)
