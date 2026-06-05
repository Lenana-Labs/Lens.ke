import os
from celery import Celery

app = Celery('lenskenya')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# DigitalOcean Redis TLS enforcement configuration
if os.environ.get('REDIS_URL', '').startswith('rediss://'):
    app.conf.update(
        broker_use_ssl={
            'ssl_cert_reqs': None # Disables strict certificate verification for managed cloud clusters
        },
        redis_backend_use_ssl={
            'ssl_cert_reqs': None
        }
    )

app.autodiscover_tasks()