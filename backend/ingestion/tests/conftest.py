import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Never let a developer's live raw database leak into mock/SQLite test pipelines.
os.environ["RAW_DATABASE_URL"] = ""
