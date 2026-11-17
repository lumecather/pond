from django.db import migrations

from guides.starter import GUIDES


def seed(apps, schema_editor):
    Guide = apps.get_model("guides", "Guide")
    for g in GUIDES:
        Guide.objects.create(**{**g, "body": g["body"].strip()})


class Migration(migrations.Migration):
    dependencies = [("guides", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
