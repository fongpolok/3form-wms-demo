from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'
    verbose_name = 'Inventory ledger, products, recipes, alerts'

    def ready(self):
        from core import config

        from . import site
        config.set_industry_resolver(site.industry_code)
