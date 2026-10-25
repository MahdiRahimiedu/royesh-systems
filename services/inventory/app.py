"""Run from the repository root: python -m uvicorn services.inventory.app:app --port 8002."""
from shared.app import create_app
from shared.database import make_database

from .routes import router
from .seed import seed

engine, SessionLocal, Base = make_database("inventory")
app = create_app("inventory", "سامانه انبار و تدارکات رویش", Base, engine, SessionLocal, seed)
app.include_router(router)
