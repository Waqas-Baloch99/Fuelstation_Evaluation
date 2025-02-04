#!/bin/bash
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn fuel_supply.wsgi:application -c gunicorn.conf.py 