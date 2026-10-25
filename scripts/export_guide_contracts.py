"""Read real ORM/OpenAPI metadata in one isolated process per service for the Word guides."""
import argparse
from importlib import import_module
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def export(service):
    module = import_module(f'services.{service}.app')
    tables = []
    for table in module.Base.metadata.sorted_tables:
        constraints = []
        for item in table.constraints:
            kind = type(item).__name__
            if kind == 'CheckConstraint':
                value = str(item.sqltext)
            else:
                value = ', '.join(column.name for column in item.columns)
            constraints.append({'kind': kind, 'name': item.name, 'value': value})
        tables.append({
            'name': table.name,
            'columns': [{
                'name': col.name, 'type': str(col.type), 'nullable': col.nullable,
                'primary_key': col.primary_key, 'unique': bool(col.unique),
                'index': bool(col.index),
                'foreign_keys': [fk.target_fullname for fk in col.foreign_keys],
                'default': (str(col.default.arg) if not callable(col.default.arg) else 'Python callable') if col.default is not None else None,
                'server_default': str(col.server_default.arg) if col.server_default is not None else None,
            } for col in table.columns],
            'constraints': sorted(constraints, key=lambda x: (x['kind'], x['value'])),
            'indexes': [{'name': index.name, 'columns': [c.name for c in index.columns], 'unique': index.unique} for index in table.indexes],
        })
    return {'service': service, 'tables': tables, 'openapi': module.app.openapi()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('service', choices=['personnel', 'inventory', 'commerce'])
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(export(args.service), ensure_ascii=False, indent=2), encoding='utf-8')
    print(target)
