import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from shared.auth import router, seed_users
from shared.audit import AuditLog
from shared.models import business_today


def create_app(service, title, Base, engine, SessionLocal, seed_fn):
    business_today()  # Validate BUSINESS_TIMEZONE at startup instead of failing a later transaction.
    demo = os.getenv('SEED_DEMO', 'true').lower() == 'true'

    @asynccontextmanager
    async def lifespan(app):
        # Local bootstrap. Server deployments use the migration command before start.
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed_users(db, demo)
            if demo:
                seed_fn(db)
                db.commit()
        yield

    app = FastAPI(title=title, version='1.0.0', lifespan=lifespan, description='API مستقل مدیریت شرکت نرم‌افزاری رویش. مبالغ: تومان؛ تاریخ‌ها: ISO 8601.')
    app.state.SessionLocal = SessionLocal
    app.state.engine = engine
    app.state.login_attempts = {}
    app.state.service = service
    origins = os.getenv('CORS_ORIGINS', 'http://localhost:3001,http://localhost:3002,http://localhost:3003,http://127.0.0.1:3001,http://127.0.0.1:3002,http://127.0.0.1:3003').split(',')
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins], allow_methods=['GET','POST','PATCH','OPTIONS'], allow_headers=['Authorization','Content-Type'])

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc):
        return JSONResponse(status_code=409, content={'detail': 'شناسه تکراری یا ارتباط نامعتبر است. اطلاعات را بررسی کنید.'})

    @app.get('/health', tags=['سلامت سرویس'])
    def health():
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status': 'ok', 'service': service, 'demo': demo}

    app.include_router(router)
    return app
