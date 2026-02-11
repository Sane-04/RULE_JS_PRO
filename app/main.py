import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import SessionLocal
from app.routers import admin, auth, chat, data, importer, metric, cockpit
from app.schemas.response import ErrorResponse


def create_app() -> FastAPI:
    app = FastAPI(title="Edu Cockpit API", version="1.0.0")

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(data.router, prefix="/api/data", tags=["data"])
    app.include_router(importer.router, tags=["import"])
    app.include_router(metric.router, tags=["metric"])
    app.include_router(cockpit.router, tags=["cockpit"])

    @app.get("/healthz")
    def healthz():
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {exc.__class__.__name__}") from exc
        finally:
            db.close()
        return {"status": "ok"}

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
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
