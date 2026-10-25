"""Package exactly five final Word manuals per service, without QA PDFs/images."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'deliverables/word-guides'
target = ROOT / 'deliverables/royesh-15-word-guides.zip'
labels = {'personnel': 'سامانه پرسنلی', 'inventory': 'سامانه انبار', 'commerce': 'سامانه بازرگانی'}
titles = {'01': 'معماری', '02': 'دیاگرام و طراحی پایگاه داده', '03': 'ساختار بک اند', '04': 'ساختار فرانت اند', '05': 'راهنمای کاربری و API'}
files = sorted(source.rglob('*.docx'))
assert len(files) == 15, 'Expected exactly 15 final DOCX files'
assert all(sum(p.name.startswith(service+'-') for p in files) == 5 for service in labels)
with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
    for path in files:
        service, number, *_ = path.stem.split('-')
        archive.write(path, f'{labels[service]}/{number} {titles[number]} {labels[service]}.docx')
with ZipFile(target) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == 15
print(target)
