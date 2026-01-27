from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import auth, admin, data
from app.schemas.response import ErrorResponse


def create_app() -> FastAPI:
    app = FastAPI(title="Edu Cockpit API", version="1.0.0")

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(data.router, tags=["data"])

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        payload = ErrorResponse(code=exc.status_code, message=str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=payload.dict())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        payload = ErrorResponse(code=400, message="Validation error", details=exc.errors())
        return JSONResponse(status_code=400, content=payload.dict())

    return app


app = create_app()
