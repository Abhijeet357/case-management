from django.core.management.base import BaseCommand
from django.utils import timezone
from ...models import Case

class Command(BaseCommand):
    help = 'Update days in current stage and total pending for all pending cases'

    def handle(self, *args, **kwargs):
        pending_cases = Case.objects.filter(is_completed=False)
        for case in pending_cases:
            previous_days_current = case.days_in_current_stage
            delta = timezone.now() - case.last_update_date
            new_days_current = delta.days
            increment = new_days_current - previous_days_current
            case.days_in_current_stage = new_days_current
            case.total_days_pending += increment
            case.save(update_fields=['days_in_current_stage', 'total_days_pending'])
        self.stdout.write(self.style.SUCCESS('Successfully updated days for pending cases'))