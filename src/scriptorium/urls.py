from django.urls import path

from scriptorium.main import views

urlpatterns = [
    # editor part, can be blocked off
    path("bibliothecarius/", views.Bibliothecarius.as_view()),
    path("bibliothecarius/login/", views.LoginView.as_view()),
    path("bibliothecarius/logout", views.logout_view),
    path("bibliothecarius/tohuwabohu/", views.TohuwabohuView.as_view()),
    path("bibliothecarius/<slug:author>/", views.AuthorEdit.as_view()),
    path("bibliothecarius/<slug:author>/<slug:book>/", views.ReviewEdit.as_view()),
    path("", views.IndexView.as_view()),
    path("feed.atom", views.feed_view),
    path("reviews.atom", views.feed_view),
    path("reviews/", views.YearView.as_view()),
    path("reviews/<int:year>/", views.YearView.as_view()),
    path("reviews/<int:year>/stats/", views.YearInBooksView.as_view()),
    path("reviews/by-author/", views.ReviewByAuthor.as_view()),
    path("reviews/by-title/", views.ReviewByTitle.as_view()),
    path("reviews/by-series/", views.ReviewBySeries.as_view()),
    path("stats/", views.StatsView.as_view()),
    path("graph/", views.GraphView.as_view()),
    path("graph.json", views.graph_data),
    path("search.json", views.search_data),
    path("queue/", views.QueueView.as_view()),
    path("lists/", views.ListView.as_view()),
    path("lists/<slug:tag>/", views.ListDetail.as_view()),
    path("<slug:author>/", views.AuthorView.as_view()),
    path("<slug:author>/<slug:book>/", views.ReviewView.as_view()),
    path("<slug:author>/<slug:book>/cover.jpg", views.ReviewCoverView.as_view()),
    path("<slug:author>/<slug:book>/edit", views.ReviewEdit.as_view()),
]
