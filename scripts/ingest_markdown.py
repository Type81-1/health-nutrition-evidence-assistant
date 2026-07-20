from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.document_ingestion import ingest_file
from app.services.evidence_store import EvidenceStore


parser = argparse.ArgumentParser(description="把 PDF 或 Markdown 资料切分并导入健康营养证据库")
source_group = parser.add_mutually_exclusive_group(required=True)
source_group.add_argument("--pdf", type=Path, help="要导入的 PDF 文件")
source_group.add_argument("--markdown", type=Path, help="要导入的 Markdown 文件")
parser.add_argument("--title", required=True, help="资料标题")
parser.add_argument("--source-url", required=True, help="来源网页或出版物链接")
args = parser.parse_args()

source = args.pdf or args.markdown
if not source.exists():
    raise SystemExit(f"找不到文件：{source}")

count = ingest_file(EvidenceStore(), source, args.title, args.source_url)
print(f"已导入 {count} 个证据片段。")
