from django.urls import path

from . import views

urlpatterns = [
    path("", views.PersonListView.as_view(), name="person-list"),
    path("personne/<int:pk>/", views.PersonDetailView.as_view(), name="person-detail"),
]
