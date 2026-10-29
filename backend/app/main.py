from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.routes import routers as v1_routers
from app.api.v2.routes import routers as v2_routers
from app.core.config import configs
from app.core.container import Container
from app.core.exceptions_handler import (
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from app.core.middleware import ResponseFormatMiddleware
from app.util.class_object import singleton


@singleton
class AppCreator:
    def __init__(self):
        # set app default
        self.app = FastAPI(
            title=configs.PROJECT_NAME,
            openapi_url=f"{configs.API}/openapi.json",
            version="0.0.1",
        )
        self.app.add_middleware(ResponseFormatMiddleware)
        self.app.add_exception_handler(
            RequestValidationError, validation_exception_handler
        )
        self.app.add_exception_handler(HTTPException, http_exception_handler)
        self.app.add_exception_handler(Exception, unexpected_exception_handler)

        # set db and container
        self.container = Container()
        self.db = self.container.db()
        # self.db.create_database()

        # set cors
        if configs.BACKEND_CORS_ORIGINS:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=[str(origin) for origin in configs.BACKEND_CORS_ORIGINS],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # set routes
        @self.app.get("/")
        def root():
            return "service is working"

        self.app.include_router(v1_routers, prefix=configs.API_V1_STR)
        self.app.include_router(v2_routers, prefix=configs.API_V2_STR)


app_creator = AppCreator()
app = app_creator.app
db = app_creator.db
container = app_creator.container
