# Generated by Django 3.2.23 on 2025-02-03 22:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fuelapp', '0002_auto_20250203_2156'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='fuelstation',
            index=models.Index(fields=['latitude', 'longitude'], name='fuelapp_fue_latitud_107792_idx'),
        ),
        migrations.AddIndex(
            model_name='fuelstation',
            index=models.Index(fields=['retail_price'], name='fuelapp_fue_retail__039f72_idx'),
        ),
        migrations.AddIndex(
            model_name='fuelstation',
            index=models.Index(fields=['state'], name='fuelapp_fue_state_48fd52_idx'),
        ),
    ]
