from django.apps import AppConfig
from django.db.models.signals import post_migrate


class LogisticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'logistics'

    def ready(self):
        from .models import ensure_default_statuses

        def create_statuses(sender, **kwargs):
            ensure_default_statuses()

        post_migrate.connect(create_statuses, sender=self)
