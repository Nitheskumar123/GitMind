import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('github_intelligence')

# Load config from Django settings with CELERY namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered apps
app.autodiscover_tasks()

# Celery Beat schedule for periodic tasks
app.conf.beat_schedule = {
    'sync-all-repositories-every-30-minutes': {
        'task': 'core.tasks.sync_all_repositories',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
# ... (keep existing celery configuration)

from celery.schedules import crontab

# Celery Beat Schedule
app.conf.beat_schedule = {
    # Daily insights at 8:00 AM
    'generate-daily-insights': {
        'task': 'core.tasks.generate_daily_insights',
        'schedule': crontab(hour=8, minute=0),
        'options': {'expires': 3600}
    },
    # Weekly insights every Monday at 8:00 AM UTC
'generate-weekly-insights': {
    'task': 'core.tasks.generate_weekly_insights',
    'schedule': crontab(day_of_week=1, hour=8, minute=0),
    'options': {'expires': 3600}
},
    'update-documentation-daily': {
        'task': 'core.tasks.update_documentation_daily',
        'schedule': crontab(hour=2, minute=0),       # Every day at 2:00 AM UTC
    },
    # Weekly documentation on Friday at 4:00 PM
    'update-documentation-weekly': {
        'task': 'core.tasks.update_documentation_weekly',
        'schedule': crontab(day_of_week=4, hour=16, minute=0),
        'options': {'expires': 3600}
    },
    'update-documentation-monthly': {
        'task': 'core.tasks.update_documentation_monthly',
        'schedule': crontab(day_of_month=1, hour=3, minute=0),  # 1st of month 3 AM UTC
    },
    
    
    # Hourly webhook health check
    'check-webhook-health': {
        'task': 'core.tasks.check_webhook_health',
        'schedule': crontab(minute=0),
        'options': {'expires': 300}
    },
    
    # Sync all repositories every 30 minutes (existing)
    'sync-all-repositories': {
        'task': 'core.tasks.sync_all_repositories',
        'schedule': crontab(minute='*/30'),
        'options': {'expires': 900}
    },
}

app.conf.timezone = 'UTC'