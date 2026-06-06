import uuid
from django.db import migrations, models

def split_names(apps, schema_editor):
    User = apps.get_model('lenskenya', 'User')
    for user in User.objects.all():
        if hasattr(user, 'name') and user.name:
            parts = user.name.strip().split(' ', 1)
            user.first_name = parts[0]
            if len(parts) > 1:
                user.last_name = parts[1]
            else:
                user.last_name = ''
            user.save(update_fields=['first_name', 'last_name'])

def reverse_split_names(apps, schema_editor):
    User = apps.get_model('lenskenya', 'User')
    for user in User.objects.all():
        user.name = f"{user.first_name} {user.last_name}".strip()
        user.save(update_fields=['name'])

class Migration(migrations.Migration):

    dependencies = [
        # Keep whatever previous migration number was automatically generated here
        ('lenskenya', '0005_merge_20260606_xxxx'), 
    ]

    operations = [
        # 1. First, create the new columns in the database so they exist
        migrations.AddField(
            model_name='user',
            name='first_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='user',
            name='last_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        
        # 2. Run the custom Python script to copy and split the name strings
        migrations.RunPython(split_names, reverse_split_names),
        
        # 3. Now that the data is safely copied, it is safe to drop the old column
        migrations.RemoveField(
            model_name='user',
            name='name',
        ),
    ]