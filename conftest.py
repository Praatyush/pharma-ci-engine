"""Pytest bootstrap: put the project root on sys.path so `import src.*` works.

There is no installed package / pyproject in v1; tests import the schema via the
``src`` namespace package. Inserting the repo root here makes that resolve
regardless of pytest's import mode or the directory tests are invoked from.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
