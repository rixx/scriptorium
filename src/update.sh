#!/bin/bash
# Update this web app

# Switch to proper user
su - books
cd /usr/share/webapps/books/scriptorium/src

# Update the code
git pull

# Update the database
python manage.py migrate
python manage.py collectstatic --noinput

# Restart the web server as root
exit
systemctl restart nginx
