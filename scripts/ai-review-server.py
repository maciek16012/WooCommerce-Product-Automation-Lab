"""Thin launcher for the internal review service."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from woo_sync.review_service import main
if __name__ == '__main__':
    raise SystemExit(main())
