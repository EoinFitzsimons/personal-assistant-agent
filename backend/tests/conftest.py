import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["RUN_JOBS_INLINE"] = "true"
os.environ["LLM_PROVIDER"] = ""
