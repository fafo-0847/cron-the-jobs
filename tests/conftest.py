import sys
from pathlib import Path

repoRoot = Path(__file__).resolve().parent.parent
if str(repoRoot) not in sys.path:
	sys.path.insert(0, str(repoRoot))
