# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2017-07-18 13:18
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0069_teamalias'),
    ]

    operations = [
        migrations.AddField(
            model_name='licenseholder',
            name='emergency_medical',
            field=models.CharField(blank=True, default=b'', help_text='eg. diabetic, drug alergy, etc.', max_length=64, verbose_name='Emergency Medical Condition'),
        ),
    ]
