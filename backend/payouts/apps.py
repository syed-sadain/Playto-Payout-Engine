from django.apps import AppConfig


class PayoutsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payouts"

    def ready(self):
        # Register Celery beat schedule when app starts
        from django.db import connection
        try:
            # Only attempt if DB is ready (not during migrations)
            if "django_celery_beat_periodictask" in connection.introspection.table_names():
                self._setup_beat_schedule()
        except Exception:
            pass

    def _setup_beat_schedule(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask
        import json

        schedule_30s, _ = IntervalSchedule.objects.get_or_create(
            every=30, period=IntervalSchedule.SECONDS
        )
        schedule_1h, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.HOURS
        )

        PeriodicTask.objects.update_or_create(
            name="Retry stale payouts every 30s",
            defaults={
                "interval": schedule_30s,
                "task": "payouts.tasks.retry_stale_payouts_task",
                "args": json.dumps([]),
            },
        )
        PeriodicTask.objects.update_or_create(
            name="Cleanup expired idempotency keys",
            defaults={
                "interval": schedule_1h,
                "task": "payouts.tasks.cleanup_expired_idempotency_keys",
                "args": json.dumps([]),
            },
        )
