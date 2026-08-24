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

ANCESTOR_TREE_DEPTH = 4


def build_ancestors(person, depth=ANCESTOR_TREE_DEPTH):
    """Structure binaire récursive {person, father, mother} pour le pedigree chart."""
    if person is None or depth <= 0:
        return None

    parents = list(person.parents())
    father = next((p for p in parents if p.sex == Person.Sex.MALE), None)
    mother = next((p for p in parents if p.sex == Person.Sex.FEMALE), None)
    remaining = [p for p in parents if p not in (father, mother)]
    if father is None and remaining:
        father = remaining.pop(0)
    if mother is None and remaining:
        mother = remaining.pop(0)

    return {
        "person": person,
        "father": build_ancestors(father, depth - 1) if father else None,
        "mother": build_ancestors(mother, depth - 1) if mother else None,
    }


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
        context["partners"] = self.object.partners()
        context["children"] = self.object.children()
        return context


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
