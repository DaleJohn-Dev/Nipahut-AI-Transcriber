"""One version for desktop, API and UI; VERSION is packaged as a resource."""
import re
import sys
from pathlib import Path

RESOURCE_ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
APP_VERSION=(RESOURCE_ROOT/'VERSION').read_text(encoding='utf-8').strip()
if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-preview\.[1-9]\d*)?',APP_VERSION):
    raise RuntimeError('Invalid application VERSION resource.')
