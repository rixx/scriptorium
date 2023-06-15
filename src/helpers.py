
def new_tag(tag, queryset=None):
    queryset = queryset or Book.objects.all().exclude(tags__id__in=[tag.pk])
    for book in queryset:
        print(f"Tag {book.title} by {book.author} with {tag.name} tag? (y/n)")
        if input().lower() == "y":
            book.tags.add(tag)
            print(f"Added tag {tag.name} to {book.title} by {book.author}")

def new_author_tag(tag):
    queryset = Author.objects.all()
    for author in queryset:
        print(f"Tag {author.name} with {tag.name} tag? (y/n)")
        if input().lower() == "y":
            author.tag_author(tag)
