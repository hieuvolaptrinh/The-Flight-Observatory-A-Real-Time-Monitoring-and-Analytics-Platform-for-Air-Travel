from typing import Annotated

from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends, File, UploadFile

from app.core.container import Container
from app.core.dependencies import get_current_user
from app.core.middleware import inject
from app.model.user import User
from app.schema.auth_schema import (
    SignIn,
    SignInResponse,
    SignUp,
    UpdateUser,
    UserResponse,
)
from app.services.auth_service import AuthService, to_user_response

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/sign-in", response_model=SignInResponse)
@inject
def sign_in(
    user_info: SignIn, service: AuthService = Depends(Provide[Container.auth_service])
):
    return service.sign_in(user_info)


@router.post("/sign-up", response_model=SignInResponse, status_code=201)
@inject
def sign_up(
    user_info: SignUp = Depends(SignUp.as_form),
    logo_file: Annotated[UploadFile | None, File()] = None,
    service: AuthService = Depends(Provide[Container.auth_service]),
):
    return service.sign_up(user_info=user_info, logo_file=logo_file)


@router.get("/me", response_model=UserResponse)
@inject
def get_me(current_user: User = Depends(get_current_user)):
    return to_user_response(current_user)


@router.patch("/me", response_model=UserResponse)
@inject
def update_me(
    user_info: UpdateUser = Depends(UpdateUser.as_form),
    logo_file: Annotated[UploadFile | None, File()] = None,
    current_user: User = Depends(get_current_user),
    service=Depends(Provide[Container.auth_service]),
):
    return service.update_profile(
        user_id=current_user.id, user_info=user_info, logo_file=logo_file
    )
