"""Use the canonical document renderer with an already converted PDF on Windows.

The Windows dependency bundle has Poppler but no LibreOffice. DOCX -> PDF uses a
private invisible Microsoft Word instance, then the bundled render_docx.py
rasterizer produces page-N.png. This adapter does not modify the skill package.
"""
import argparse
import importlib.util
from pathlib import Path
import os
import shutil
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--skill-dir',required=True)
parser.add_argument('--qa-dir',required=True)
parser.add_argument('--documents',required=True)
parser.add_argument('--dpi',type=int,default=160)
args=parser.parse_args()
dependencies=Path(sys.executable).parent.parent
poppler=dependencies/'native/poppler/Library/bin'
os.environ['PATH']=str(poppler)+os.pathsep+os.environ.get('PATH','')
spec=importlib.util.spec_from_file_location('canonical_docx_renderer',Path(args.skill_dir)/'render_docx.py')
renderer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
qa=Path(args.qa_dir).resolve()


def converted_pdf(doc_path,user_profile,convert_tmp_dir,stem,verbose):
    source=qa/stem/f'{stem}.pdf'
    if not source.is_file():
        raise FileNotFoundError(f'Run render_word_guides.ps1 first: {source}')
    target=Path(convert_tmp_dir)/source.name
    shutil.copyfile(source,target)
    return str(target),'Conversion backend: private Microsoft Word instance on Windows'


renderer.convert_to_pdf=converted_pdf
for docx in sorted(Path(args.documents).rglob('*.docx')):
    pages=renderer.rasterize(str(docx),str(qa/docx.stem),dpi=args.dpi,verbose=False,emit_pdf=False)
    print(f'{docx.stem}: {len(pages)} pages',flush=True)
