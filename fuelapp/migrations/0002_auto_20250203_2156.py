# Generated by Django 3.2.23 on 2025-02-03 18:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fuelapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='fuelstation',
            name='latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fuelstation',
            name='longitude',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
