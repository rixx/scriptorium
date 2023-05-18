from django.urls import path, include

from scriptorium.main import views

urlpatterns = [
    path("", views.IndexView.as_view()),
    path("b/", views.Bibliothecarius.as_view()),
    path("b/login/", views.LoginView.as_view()),
    path("b/logout", views.logout_view),
    path("b/tohuwabohu/", views.TohuwabohuView.as_view()),
    path("b/new", views.ReviewCreate.as_view()),
    path("b/page/new", views.PageCreate.as_view()),
    path("b/page/", views.PageList.as_view()),
    path("b/page/<slug:slug>/", views.PageEdit.as_view()),
    path("b/<slug:author>/", views.AuthorEdit.as_view()),
    path("b/<slug:author>/<slug:book>/", views.ReviewEdit.as_view()),
    path("p/<slug:slug>/", views.PageView.as_view()),
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
    path("<slug:author>/<slug:book>/thumbnail.jpg", views.ReviewCoverThumbnailView.as_view()),
    path("<slug:author>/<slug:book>/square.png", views.ReviewCoverSquareView.as_view()),
    path("<slug:author>/<slug:book>/edit", views.ReviewEdit.as_view()),
]

try:
    import debug_toolbar
    # insert url for debug toolbar at the top of the list
    urlpatterns.insert(0, path("__debug__/", include(debug_toolbar.urls)))
except ImportError:
    pass
