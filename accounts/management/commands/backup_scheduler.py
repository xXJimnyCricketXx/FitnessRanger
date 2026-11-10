import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from accounts.backup import run_due_backup

logger = logging.getLogger(__name__)
CHECK_EVERY_SECONDS = 60


class Command(BaseCommand):
    help = 'Creates automatic backups according to the system settings.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Check once and exit instead of running forever.')

    def handle(self, *args, **options):
        if options['once']:
            self.stdout.write('Backup erstellt.' if run_due_backup() else 'Kein Backup fällig.')
            return

        while True:
            close_old_connections()
            try:
                run_due_backup()
            except Exception:
                # A temporary problem must not end the loop, or backups stop silently.
                logger.exception('Backup scheduler check failed')
            time.sleep(CHECK_EVERY_SECONDS)
