# Generated by Django 3.2.16 on 2023-06-15 10:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('location', '0015_set_managed_to_true'),
        ('claim', '0018_alter_jsonext_column'),
    ]

    operations = []
    try:
        Claim.objects.filter(pk<10).aggregate(sum=models.Count('refer_from'))
    except:
        operations.append(migrations.AddField(
            model_name='claim',
            name='refer_from',
            field=models.ForeignKey(blank=True, db_column='ReferFrom', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='referFromHF', to='location.healthfacility'),
        ))
    try:
        Claim.objects.filter(pk<10).aggregate(sum=models.Count('refer_to'))
    except:    
        operations.append(migrations.AddField(
            model_name='claim',
            name='refer_to',
            field=models.ForeignKey(blank=True, db_column='ReferTo', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='referToHF', to='location.healthfacility'),
        ))
    
