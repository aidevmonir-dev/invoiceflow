from django.core.management.base import BaseCommand

from invoices.services.files import purge_expired


class Command(BaseCommand):
    help = "Delete uploaded documents older than RETENTION_HOURS. Safe to run from cron."

    def handle(self, *args, **options):
        self.stdout.write(f"Deleted {purge_expired()} expired documents.")
