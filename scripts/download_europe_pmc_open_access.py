from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.source_plugins import EuropePmcOpenAccessPlugin


parser = argparse.ArgumentParser(description="批量下载 Europe PMC 开放获取文献的元数据和全文 XML")
parser.add_argument("--query", required=True, help="Europe PMC 检索词")
parser.add_argument("--limit", type=int, default=20, choices=range(1, 101), metavar="1-100")
parser.add_argument("--output", type=Path, default=Path("data/europe_pmc_batch"), help="输出目录")
args = parser.parse_args()

result = asyncio.run(EuropePmcOpenAccessPlugin().download(args.query, args.limit, args.output))
print(f"已获取 {result.records} 条记录，下载 {result.xml_files} 份全文 XML：{result.output_dir}")
