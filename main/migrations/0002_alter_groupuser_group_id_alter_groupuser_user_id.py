# Generated by Django 4.2.13 on 2024-07-09 12:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='groupuser',
            name='group_id',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='groupuser',
            name='user_id',
            field=models.CharField(max_length=50),
        ),
    ]
