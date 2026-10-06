"""Scheduled report sends (reports-weekly.timer, reports-monthly.timer):
    venv/bin/python send_reports.py weekly
Sends last week's or last month's reports once; a rerun sends nothing new."""
import sys

from app import create_app
from app.modules.reports.lib.send import run_scheduled

KINDS = ('weekly', 'monthly')

if __name__ == '__main__':
    kind = sys.argv[1] if len(sys.argv) > 1 else ''
    if kind not in KINDS:
        sys.exit('usage: send_reports.py weekly|monthly')
    app = create_app()
    with app.app_context():
        print(run_scheduled(kind))
