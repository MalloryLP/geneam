from django import forms

from .models import Parentage, Person, Union

DATE_WIDGET = forms.DateInput(attrs={"type": "date"})


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "sex",
            "birth_date",
            "birth_place",
            "death_date",
            "death_place",
            "notes",
        ]
        widgets = {
            "birth_date": DATE_WIDGET,
            "death_date": DATE_WIDGET,
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


def _existing_person_field(exclude_pk):
    return forms.ModelChoiceField(
        label="Personne",
        queryset=Person.objects.exclude(pk=exclude_pk),
        required=True,
    )


class ExistingParentForm(forms.Form):
    """Lie une personne déjà enregistrée comme parent."""

    def __init__(self, *args, child, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"] = _existing_person_field(child.pk)

    relation_type = forms.ChoiceField(
        label="Type de filiation", choices=Parentage.RelationType.choices
    )


class NewParentForm(PersonForm):
    """Crée une nouvelle personne et la lie comme parent."""

    relation_type = forms.ChoiceField(
        label="Type de filiation", choices=Parentage.RelationType.choices
    )


class ExistingChildForm(forms.Form):
    """Lie une personne déjà enregistrée comme enfant."""

    def __init__(self, *args, parent, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"] = _existing_person_field(parent.pk)

    relation_type = forms.ChoiceField(
        label="Type de filiation", choices=Parentage.RelationType.choices
    )


class NewChildForm(PersonForm):
    """Crée une nouvelle personne et la lie comme enfant."""

    relation_type = forms.ChoiceField(
        label="Type de filiation", choices=Parentage.RelationType.choices
    )


class ExistingPartnerForm(forms.Form):
    """Lie une personne déjà enregistrée comme conjoint·e."""

    def __init__(self, *args, person, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"] = _existing_person_field(person.pk)

    union_type = forms.ChoiceField(label="Type d'union", choices=Union.UnionType.choices)
    start_date = forms.DateField(label="Date de début", required=False, widget=DATE_WIDGET)
    end_date = forms.DateField(label="Date de fin", required=False, widget=DATE_WIDGET)


class NewPartnerForm(PersonForm):
    """Crée une nouvelle personne et la lie comme conjoint·e."""

    union_type = forms.ChoiceField(label="Type d'union", choices=Union.UnionType.choices)
    start_date = forms.DateField(label="Date de début", required=False, widget=DATE_WIDGET)
    end_date = forms.DateField(label="Date de fin", required=False, widget=DATE_WIDGET)
