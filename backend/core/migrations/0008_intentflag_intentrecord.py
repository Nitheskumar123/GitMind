from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_add_filecomprehensionscore'),
    ]

    operations = [
        migrations.CreateModel(
            name='IntentFlag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file_path', models.CharField(max_length=500)),
                ('line_number', models.IntegerField(default=0)),
                ('flag_type', models.CharField(choices=[
                    ('magic_number', 'Magic Number'),
                    ('timeout', 'Timeout / Limit'),
                    ('threshold', 'Conditional Threshold'),
                    ('algorithm_choice', 'Algorithm Choice'),
                    ('string_assumption', 'String Assumption'),
                ], max_length=30)),
                ('detected_value', models.CharField(max_length=255)),
                ('question', models.TextField(help_text='Auto-generated question for the developer')),
                ('code_snippet', models.TextField(blank=True, help_text='The line of code containing the flagged value')),
                ('ai_confidence', models.FloatField(default=0.0, help_text='Confidence that this code was AI-generated (0-1)', validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending'),
                    ('captured', 'Captured'),
                    ('dismissed', 'Dismissed'),
                ], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('pull_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='intent_flags', to='core.pullrequest')),
                ('repository', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='intent_flags', to='core.repository')),
            ],
            options={
                'db_table': 'intent_flags',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='IntentRecord',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('author', models.CharField(help_text='Developer who answered', max_length=200)),
                ('intent_text', models.TextField(help_text="Developer's explanation in plain English")),
                ('constraint_type', models.CharField(choices=[
                    ('legal', 'Legal Requirement'),
                    ('business_rule', 'Business Rule'),
                    ('performance', 'Performance Decision'),
                    ('security', 'Security Policy'),
                    ('ux', 'UX / Design Decision'),
                    ('other', 'Other'),
                ], default='other', max_length=20)),
                ('review_required', models.BooleanField(default=False, help_text='Should this be reviewed before changing?')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('flag', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='intent_record', to='core.intentflag')),
            ],
            options={
                'db_table': 'intent_records',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='intentflag',
            index=models.Index(fields=['repository', 'status'], name='intent_flag_repo_status_idx'),
        ),
        migrations.AddIndex(
            model_name='intentflag',
            index=models.Index(fields=['pull_request', 'status'], name='intent_flag_pr_status_idx'),
        ),
        migrations.AddIndex(
            model_name='intentflag',
            index=models.Index(fields=['-created_at'], name='intent_flag_created_idx'),
        ),
    ]
