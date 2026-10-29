from dependency_injector import containers, providers

from app.core.config import configs
from app.core.database import Database
from app.repository import *
from app.services import *


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.api.v1.endpoints.auth",
            "app.api.v1.endpoints.post",
            "app.api.v1.endpoints.tag",
            "app.api.v1.endpoints.user",
            "app.api.v2.endpoints.auth",
            "app.core.dependencies",
            "app.api.v1.endpoints.invoice",
        ]
    )

    db = providers.Singleton(Database, db_url=configs.DATABASE_URI)

    post_repository = providers.Factory(
        PostRepository, session_factory=db.provided.session
    )
    tag_repository = providers.Factory(
        TagRepository, session_factory=db.provided.session
    )
    user_repository = providers.Factory(
        UserRepository, session_factory=db.provided.session
    )
    invoice_repository = providers.Factory(
        InvoiceRepository, session_factory=db.provided.session
    )

    storage_service = providers.Singleton(
        StorageService,
        endpoint=configs.MINIO_ENDPOINT,
        access_key=configs.MINIO_ACCESS_KEY,
        secret_key=configs.MINIO_SECRET_KEY,
        bucket=configs.MINIO_BUCKET,
        public_url=configs.MINIO_PUBLIC_URL,
        secure=configs.MINIO_SECURE,
    )

    auth_service = providers.Factory(
        AuthService,
        user_repository=user_repository,
        storage_service=storage_service,
    )
    post_service = providers.Factory(
        PostService, post_repository=post_repository, tag_repository=tag_repository
    )
    tag_service = providers.Factory(TagService, tag_repository=tag_repository)
    user_service = providers.Factory(UserService, user_repository=user_repository)
    invoice_service = providers.Factory(
        InvoiceService, invoice_repository=invoice_repository
    )

    # invoice
    image_processor_service = providers.Factory(ImageProcessorService)
    orc_service = providers.Singleton(OrcService) #singleton để khởi tạo 1 lần đỡ tốn resource
    gemini_service = providers.Factory(GeminiService)
