#!/bin/bash

runuser -u books -- git pull

runuser -u books -- python manage.py migrate
runuser -u books -- python manage.py collectstatic --no-input

systemctl restart books
