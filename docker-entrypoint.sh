#!/bin/sh
set -e

python manage.py migrate --noinput

# Runs once per volume, so later edits to the seeded data survive a restart.
if [ ! -f /app/data/.initialized ]; then
    python manage.py loaddata seed_catalog
    if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
        python manage.py createsuperuser --noinput
    fi
    touch /app/data/.initialized
fi

# Ends together with the container.
python manage.py backup_scheduler &

exec "$@"
