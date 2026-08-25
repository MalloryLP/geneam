from django.urls import path

from . import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("personnes/", views.PersonListView.as_view(), name="person-list"),
    path("personne/ajouter/", views.PersonCreateView.as_view(), name="person-add"),
    path("personne/importer-gedcom/", views.gedcom_import_view, name="gedcom-import"),
    path("personne/<int:pk>/", views.PersonDetailView.as_view(), name="person-detail"),
    path("personne/<int:pk>/modifier/", views.PersonUpdateView.as_view(), name="person-edit"),
    path("personne/<int:pk>/supprimer/", views.PersonDeleteView.as_view(), name="person-delete"),
    path("personne/<int:pk>/arbre/", views.PersonTreeView.as_view(), name="person-tree"),
    path("personne/<int:pk>/panneau/", views.person_panel, name="person-panel"),
    path("personne/<int:pk>/definir-reference/", views.set_home_person, name="set-home-person"),
    path("personne/<int:pk>/ajouter-parent/", views.add_parent, name="add-parent"),
    path("personne/<int:pk>/ajouter-enfant/", views.add_child, name="add-child"),
    path("personne/<int:pk>/ajouter-conjoint/", views.add_partner, name="add-partner"),
    path("filiation/<int:pk>/supprimer/", views.remove_parentage, name="remove-parentage"),
    path("union/<int:pk>/supprimer/", views.remove_union, name="remove-union"),
]
