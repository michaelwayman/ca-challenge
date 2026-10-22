from django.db import migrations, models
from django.db.models import F


def mark_descriptions_as_imported(apps, schema_editor):
    # Every existing description counts as unedited, so the next import may refresh it.
    apps.get_model("catalog", "Brand").objects.update(wp_description=F("description"))


class Migration(migrations.Migration):
    """A brand has one description (sanitized HTML); the separate short description is gone.

    A short description written through the API or the admin is dropped: the cards now show
    an excerpt of the description, and the short text cannot be merged into it automatically.
    """

    dependencies = [
        ("catalog", "0002_page"),
    ]

    operations = [
        migrations.AddField(
            model_name="brand",
            name="wp_description",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.RunPython(mark_descriptions_as_imported, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="brand",
            name="short_description",
        ),
    ]
