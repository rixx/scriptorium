#!/bin/bash

# If run with '--client':
if [ "$1" = "--client" ]; then
    python manage.py calibre_export
    rsync -avz --info=progress2 -h calibre_books.json mycroft:/tmp
    rm calibre_books.json
    exit 0
fi

# If run with '--server':
if [ "$1" = "--server" ]; then
    runuser -u books -- python manage.py calibre_import /tmp/calibre_books.json
    exit 0
fi
