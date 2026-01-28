from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('student', 'Student'),
                    ('proctor', 'Proctor'),
                    ('staff', 'Staff'),
                    ('hod', 'HOD'),
                    ('dean', 'Dean'),
                    ('principal', 'Principal'),
                ],
            ),
        ),
    ]
