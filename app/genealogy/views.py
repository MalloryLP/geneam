from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import (
    ExistingChildForm,
    ExistingParentForm,
    ExistingPartnerForm,
    GedcomImportForm,
    NewChildForm,
    NewParentForm,
    NewPartnerForm,
    PersonForm,
)
from .gedcom_import import GedcomImportError, import_gedcom
from .models import Parentage, Person, Union

# Nombre de générations affichées dans le pedigree, personne d'ancrage comprise.
ANCESTOR_TREE_DEPTH = 5


def build_ancestors(person, depth=ANCESTOR_TREE_DEPTH):
    """Pedigree ascendant récursif {person, father, mother} sur `depth` générations.

    Toutes les filiations et unions sont chargées en une seule requête chacune
    puis l'arbre est construit en mémoire : sur 5 générations le pedigree
    compte jusqu'à 31 nœuds, ce qui ferait autant de requêtes en interrogeant
    la base nœud à nœud.
    """
    if person is None or depth <= 0:
        return None

    parents_of = defaultdict(list)
    children_of = defaultdict(list)
    for link in Parentage.objects.select_related("parent", "child"):
        parents_of[link.child_id].append(link.parent)
        children_of[link.parent_id].append(link.child)

    # Tous les conjoint(e)s de chaque personne, pour repérer les remariages :
    # quand un ancêtre a eu plusieurs unions, celle qui n'a pas produit l'enfant
    # de la lignée directe est quand même affichée à côté de lui.
    partners_of = defaultdict(list)
    for union in Union.objects.select_related("person1", "person2"):
        partners_of[union.person1_id].append(union.person2)
        partners_of[union.person2_id].append(union.person1)

    def node(current, remaining, co_parent=None):
        parents = parents_of.get(current.pk, [])
        father = next((p for p in parents if p.sex == Person.Sex.MALE), None)
        mother = next((p for p in parents if p.sex == Person.Sex.FEMALE), None)
        unsexed = [p for p in parents if p is not father and p is not mother]
        if father is None and unsexed:
            father = unsexed.pop(0)
        if mother is None and unsexed:
            mother = unsexed.pop(0)

        last_generation = remaining <= 1
        co_parent_pk = co_parent.pk if co_parent else None
        other_spouses = [p for p in partners_of.get(current.pk, []) if p.pk != co_parent_pk]
        return {
            "person": current,
            "father": None if last_generation or father is None
            else node(father, remaining - 1, mother),
            "mother": None if last_generation or mother is None
            else node(mother, remaining - 1, father),
            # Emplacements "+" pour compléter l'arbre là où il s'arrête, comme sur Geneanet.
            "father_slot": not last_generation and father is None,
            "mother_slot": not last_generation and mother is None,
            # L'arbre continue au-delà de ce qui est affiché : cliquer la carte recentre dessus.
            "has_hidden_ancestors": last_generation and bool(parents),
            "has_descendants": current.pk in children_of,
            # Badge "+" façon Geneanet : cette personne a au moins une union connue
            # (même celle déjà affichée comme père/mère juste à côté), invitant à
            # explorer son couple/sa descendance.
            "has_union": bool(partners_of.get(current.pk)),
            # Remariage : les autres conjoint(e)s de cette personne, hors celui/celle
            # qui a donné l'enfant par lequel on est remonté jusqu'ici. Pas de branche
            # d'ancêtres au-delà : on ne connaît pas leur propre lignée dans ce
            # pedigree centré sur la personne d'ancrage. Même traitement visuel que
            # la carte principale (façon Geneanet : aucune distinction de style entre
            # les conjoint(e)s d'une personne).
            "other_spouses": [
                {
                    "person": p,
                    "has_descendants": p.pk in children_of,
                    "has_union": True,  # elle est justement affichée ici pour son union avec current
                }
                for p in other_spouses
            ],
        }

    return node(person, depth)


class PersonListView(ListView):
    model = Person
    template_name = "genealogy/person_list.html"
    context_object_name = "persons"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query) | Q(last_name__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        return context


class PersonDetailView(DetailView):
    model = Person
    template_name = "genealogy/person_detail.html"
    context_object_name = "person"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        context["parentages_as_child"] = Parentage.objects.filter(child=person).select_related("parent")
        context["parentages_as_parent"] = Parentage.objects.filter(parent=person).select_related("child")
        context["unions"] = person.unions().select_related("person1", "person2")
        context["timeline"] = person.timeline()
        return context


class PersonCreateView(CreateView):
    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Ajouter une personne"
        return context


class PersonUpdateView(UpdateView):
    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Modifier {self.object.full_name}"
        return context


class PersonDeleteView(DeleteView):
    model = Person
    template_name = "genealogy/person_confirm_delete.html"
    success_url = reverse_lazy("person-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        context["parentage_count"] = Parentage.objects.filter(
            Q(parent=person) | Q(child=person)
        ).count()
        context["union_count"] = person.unions().count()
        return context


class PersonTreeView(DetailView):
    model = Person
    template_name = "genealogy/person_tree.html"
    context_object_name = "person"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ancestors"] = build_ancestors(self.object)
        context["generations"] = ANCESTOR_TREE_DEPTH
        # Les conjoint(e)s de la personne d'ancrage sont déjà affiché(e)s à côté
        # d'elle dans le pedigree (`other_spouses` du nœud racine, cf.
        # build_ancestors — sans co_parent à exclure, il·elle·s y figurent
        # toutes/tous) : pas besoin d'une section "Conjoint(e)s" séparée.

        # Enfants groupés par union (par l'autre parent) dès qu'il y en a plus
        # d'une, comme sur Geneanet — sinon liste simple, pas de sous-titre inutile.
        children = list(self.object.children())
        other_parent_links = (
            Parentage.objects.filter(child__in=children)
            .exclude(parent=self.object)
            .select_related("parent")
        )
        other_parent_by_child = {link.child_id: link.parent for link in other_parent_links}
        groups = defaultdict(list)
        for child in children:
            groups[other_parent_by_child.get(child.pk)].append(child)

        children_by_union = []
        for co_parent, kids in groups.items():
            cards = []
            for child in kids:
                cards.append({
                    "person": child,
                    "has_descendants": bool(child.children_links.exists()),
                    "has_union": child.unions().exists(),
                })
            children_by_union.append({"co_parent": co_parent, "children": cards})
        context["children_by_union"] = children_by_union
        context["children_grouped"] = len(children_by_union) > 1
        return context


class HomeView(PersonTreeView):
    """Page d'accueil : l'arbre de la personne de référence, ou la liste si aucune n'est définie."""

    def get(self, request, *args, **kwargs):
        home_person = Person.objects.filter(is_home_person=True).first()
        if home_person is None:
            return PersonListView.as_view()(request)
        self.object = home_person
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


def person_panel(request, pk):
    """Fragment HTML de la fiche latérale, chargé en fetch() depuis l'arbre."""
    person = get_object_or_404(Person, pk=pk)
    return render(
        request,
        "genealogy/_person_panel.html",
        {"person": person, "timeline": person.timeline()},
    )


@require_POST
def set_home_person(request, pk):
    person = get_object_or_404(Person, pk=pk)
    with transaction.atomic():
        Person.objects.filter(is_home_person=True).update(is_home_person=False)
        person.is_home_person = True
        person.save(update_fields=["is_home_person"])
    messages.success(request, f"{person.full_name} est maintenant la personne de référence de l'accueil.")
    return redirect("person-detail", pk=person.pk)


def add_parent(request, pk):
    child = get_object_or_404(Person, pk=pk)
    existing_form = ExistingParentForm(child=child, prefix="existing")
    new_form = NewParentForm(prefix="new")

    if request.method == "POST":
        mode = request.POST.get("mode")
        if mode == "existing":
            existing_form = ExistingParentForm(request.POST, child=child, prefix="existing")
            if existing_form.is_valid():
                parent = existing_form.cleaned_data["person"]
                Parentage.objects.get_or_create(
                    parent=parent,
                    child=child,
                    defaults={"relation_type": existing_form.cleaned_data["relation_type"]},
                )
                messages.success(request, f"{parent.full_name} ajouté·e comme parent de {child.full_name}.")
                return redirect("person-detail", pk=child.pk)
        elif mode == "new":
            new_form = NewParentForm(request.POST, prefix="new")
            if new_form.is_valid():
                with transaction.atomic():
                    parent = new_form.save()
                    Parentage.objects.create(
                        parent=parent,
                        child=child,
                        relation_type=new_form.cleaned_data["relation_type"],
                    )
                messages.success(
                    request, f"{parent.full_name} créé·e et ajouté·e comme parent de {child.full_name}."
                )
                return redirect("person-detail", pk=child.pk)

    return render(
        request,
        "genealogy/add_relative.html",
        {
            "title": f"Ajouter un parent à {child.full_name}",
            "target": child,
            "existing_form": existing_form,
            "new_form": new_form,
            "existing_label": "Lier une personne existante comme parent",
            "new_label": "Créer une nouvelle personne comme parent",
        },
    )


def add_child(request, pk):
    parent = get_object_or_404(Person, pk=pk)
    existing_form = ExistingChildForm(parent=parent, prefix="existing")
    new_form = NewChildForm(prefix="new")

    if request.method == "POST":
        mode = request.POST.get("mode")
        if mode == "existing":
            existing_form = ExistingChildForm(request.POST, parent=parent, prefix="existing")
            if existing_form.is_valid():
                child = existing_form.cleaned_data["person"]
                Parentage.objects.get_or_create(
                    parent=parent,
                    child=child,
                    defaults={"relation_type": existing_form.cleaned_data["relation_type"]},
                )
                messages.success(request, f"{child.full_name} ajouté·e comme enfant de {parent.full_name}.")
                return redirect("person-detail", pk=parent.pk)
        elif mode == "new":
            new_form = NewChildForm(request.POST, prefix="new")
            if new_form.is_valid():
                with transaction.atomic():
                    child = new_form.save()
                    Parentage.objects.create(
                        parent=parent,
                        child=child,
                        relation_type=new_form.cleaned_data["relation_type"],
                    )
                messages.success(
                    request, f"{child.full_name} créé·e et ajouté·e comme enfant de {parent.full_name}."
                )
                return redirect("person-detail", pk=parent.pk)

    return render(
        request,
        "genealogy/add_relative.html",
        {
            "title": f"Ajouter un enfant à {parent.full_name}",
            "target": parent,
            "existing_form": existing_form,
            "new_form": new_form,
            "existing_label": "Lier une personne existante comme enfant",
            "new_label": "Créer une nouvelle personne comme enfant",
        },
    )


def add_partner(request, pk):
    person = get_object_or_404(Person, pk=pk)
    existing_form = ExistingPartnerForm(person=person, prefix="existing")
    new_form = NewPartnerForm(prefix="new")

    if request.method == "POST":
        mode = request.POST.get("mode")
        if mode == "existing":
            existing_form = ExistingPartnerForm(request.POST, person=person, prefix="existing")
            if existing_form.is_valid():
                partner = existing_form.cleaned_data["person"]
                Union.objects.create(
                    person1=person,
                    person2=partner,
                    union_type=existing_form.cleaned_data["union_type"],
                    start_date=existing_form.cleaned_data["start_date"],
                    end_date=existing_form.cleaned_data["end_date"],
                )
                messages.success(request, f"Union avec {partner.full_name} ajoutée.")
                return redirect("person-detail", pk=person.pk)
        elif mode == "new":
            new_form = NewPartnerForm(request.POST, prefix="new")
            if new_form.is_valid():
                with transaction.atomic():
                    partner = new_form.save()
                    Union.objects.create(
                        person1=person,
                        person2=partner,
                        union_type=new_form.cleaned_data["union_type"],
                        start_date=new_form.cleaned_data["start_date"],
                        end_date=new_form.cleaned_data["end_date"],
                    )
                messages.success(request, f"{partner.full_name} créé·e et lié·e comme conjoint·e.")
                return redirect("person-detail", pk=person.pk)

    return render(
        request,
        "genealogy/add_relative.html",
        {
            "title": f"Ajouter un·e conjoint·e à {person.full_name}",
            "target": person,
            "existing_form": existing_form,
            "new_form": new_form,
            "existing_label": "Lier une personne existante comme conjoint·e",
            "new_label": "Créer une nouvelle personne comme conjoint·e",
        },
    )


@require_POST
def remove_parentage(request, pk):
    link = get_object_or_404(Parentage, pk=pk)
    redirect_pk = request.POST.get("redirect_to") or link.child.pk
    link.delete()
    messages.success(request, "Lien de filiation retiré.")
    return redirect("person-detail", pk=redirect_pk)


@require_POST
def remove_union(request, pk):
    link = get_object_or_404(Union, pk=pk)
    redirect_pk = request.POST.get("redirect_to") or link.person1.pk
    link.delete()
    messages.success(request, "Union retirée.")
    return redirect("person-detail", pk=redirect_pk)


def gedcom_import_view(request):
    existing_person_count = Person.objects.count()

    if request.method == "POST":
        form = GedcomImportForm(request.POST, request.FILES, existing_person_count=existing_person_count)
        if form.is_valid():
            try:
                summary = import_gedcom(form.cleaned_data["gedcom_file"])
            except GedcomImportError as exc:
                messages.error(request, f"Le fichier n'a pas pu être importé : {exc}")
            else:
                messages.success(
                    request,
                    f"Import terminé : {summary.persons} personne(s), "
                    f"{summary.parentages} filiation(s), {summary.unions} union(s) créée(s).",
                )
                return redirect("person-list")
    else:
        form = GedcomImportForm(existing_person_count=existing_person_count)

    return render(
        request,
        "genealogy/gedcom_import.html",
        {"form": form, "existing_person_count": existing_person_count},
    )
