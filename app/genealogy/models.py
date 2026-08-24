from django.db import models
from django.urls import reverse


class Person(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "F", "Féminin"
        MALE = "M", "Masculin"
        OTHER = "O", "Autre / inconnu"

    first_name = models.CharField("prénom", max_length=100)
    last_name = models.CharField("nom", max_length=100)
    sex = models.CharField("sexe", max_length=1, choices=Sex.choices, default=Sex.OTHER)

    birth_date = models.DateField("date de naissance", null=True, blank=True)
    birth_place = models.CharField("lieu de naissance", max_length=200, blank=True)
    death_date = models.DateField("date de décès", null=True, blank=True)
    death_place = models.CharField("lieu de décès", max_length=200, blank=True)

    notes = models.TextField("notes", blank=True)

    is_home_person = models.BooleanField(
        "personne de référence",
        default=False,
        help_text="Personne dont l'arbre s'affiche sur la page d'accueil (une seule à la fois).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "personne"
        verbose_name_plural = "personnes"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_home_person"],
                condition=models.Q(is_home_person=True),
                name="unique_home_person",
            )
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self):
        return reverse("person-detail", kwargs={"pk": self.pk})

    def parents(self):
        return Person.objects.filter(children_links__child=self)

    def children(self):
        return Person.objects.filter(parents_links__parent=self)

    def partners(self):
        as_p1 = Person.objects.filter(unions_as_person2__person1=self)
        as_p2 = Person.objects.filter(unions_as_person1__person2=self)
        return (as_p1 | as_p2).distinct()

    def unions(self):
        return Union.objects.filter(models.Q(person1=self) | models.Q(person2=self))


class Parentage(models.Model):
    class RelationType(models.TextChoices):
        BIOLOGICAL = "biological", "Biologique"
        ADOPTIVE = "adoptive", "Adoptif"
        FOSTER = "foster", "Famille d'accueil"

    parent = models.ForeignKey(
        Person, verbose_name="parent", related_name="children_links", on_delete=models.CASCADE
    )
    child = models.ForeignKey(
        Person, verbose_name="enfant", related_name="parents_links", on_delete=models.CASCADE
    )
    relation_type = models.CharField(
        "type de filiation", max_length=20, choices=RelationType.choices, default=RelationType.BIOLOGICAL
    )
    notes = models.TextField("notes", blank=True)

    class Meta:
        verbose_name = "filiation"
        verbose_name_plural = "filiations"
        constraints = [
            models.UniqueConstraint(fields=["parent", "child"], name="unique_parentage")
        ]

    def __str__(self):
        return f"{self.parent} → {self.child}"


class Union(models.Model):
    class UnionType(models.TextChoices):
        MARRIAGE = "marriage", "Mariage"
        CIVIL_UNION = "pacs", "PACS"
        COHABITATION = "cohabitation", "Union libre"
        OTHER = "other", "Autre"

    person1 = models.ForeignKey(
        Person, verbose_name="personne 1", related_name="unions_as_person1", on_delete=models.CASCADE
    )
    person2 = models.ForeignKey(
        Person, verbose_name="personne 2", related_name="unions_as_person2", on_delete=models.CASCADE
    )
    union_type = models.CharField(
        "type d'union", max_length=20, choices=UnionType.choices, default=UnionType.MARRIAGE
    )
    start_date = models.DateField("date de début", null=True, blank=True)
    end_date = models.DateField("date de fin", null=True, blank=True)
    notes = models.TextField("notes", blank=True)

    class Meta:
        verbose_name = "union"
        verbose_name_plural = "unions"

    def __str__(self):
        return f"{self.person1} & {self.person2} ({self.get_union_type_display()})"
