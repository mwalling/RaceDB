# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2017-03-28 14:11
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0056_auto_20170223_1910'),
    ]

    operations = [
        migrations.CreateModel(
            name='UpdateLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created')),
                ('update_type', models.PositiveSmallIntegerField(choices=[(0, 'MergeLicenseHolders'), (1, 'MergeTeams')], verbose_name='Update Type')),
                ('description', models.TextField(verbose_name='Description')),
            ],
            options={
                'ordering': ['-created'],
                'verbose_name': 'UpdateLog',
                'verbose_name_plural': 'UpdateLog',
            },
        ),
        migrations.AlterField(
            model_name='systeminfo',
            name='license_holder_unique_by_license_code',
            field=models.BooleanField(default=True, help_text='If True, License Holders will be Merged assuming that License Codes are permanent and unique.  Otherwise, ignore and attempt to match by Last, First, Gender and DOB', verbose_name='License Codes Permanent and Unique'),
        ),
    ]
