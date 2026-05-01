import logging
from pathlib import Path
import os

from jd_matcher.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

db_path = Path(os.environ.get("DB_PATH", Path.home() / ".jd-matcher" / "jd-matcher.db"))
summary = run_pipeline(db_path=db_path)

print(f"\nPipeline run complete — run_id={summary.run_id}")
print(f"Duration: {(summary.finished_at - summary.started_at).total_seconds():.1f}s")
print(f"Total new postings: {summary.total_new_postings}")
print("\nPer-source results:")
for s in summary.sources:
    status_icon = "OK" if s.health_status == "healthy" else "FAIL"
    print(f"  [{status_icon}] {s.source:<25} {s.health_status}")
    if s.failure_reason:
        print(f"        reason: {s.failure_reason}")
