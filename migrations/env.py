"""Use SERVICE=personnel|inventory|commerce to migrate that service only."""
import importlib
import os
from alembic import context

service = os.getenv('SERVICE', 'personnel')
if service not in ('personnel', 'inventory', 'commerce'):
    raise RuntimeError('Unknown SERVICE')
module = importlib.import_module(f'services.{service}.app')
target_metadata = module.Base.metadata

if context.is_offline_mode():
    context.configure(url=str(module.engine.url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with module.engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
