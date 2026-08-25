import datetime

from django.db import models
from django.urls import reverse
from django.utils import formats


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

    def timeline(self):
        """Événements de la personne, triés, complétés par sa naissance/décès.

        Les personnes saisies à la main n'ont pas d'`Event` : on synthétise alors
        la naissance et le décès depuis les champs de `Person` pour qu'elles aient
        quand même une chronologie. Un vrai `Event` du même type a la priorité.
        """
        # Une profession sans date est déjà affichée sous le nom : l'inclure ici
        # produirait une ligne de chronologie vide.
        events = [
            e
            for e in self.events.select_related("related_person")
            if not (e.event_type == Event.EventType.OCCUPATION and e.date is None)
        ]
        present = {e.event_type for e in events}

        synthetic = []
        if Event.EventType.BIRTH not in present and (self.birth_date or self.birth_place):
            synthetic.append(
                Event(
                    person=self,
                    event_type=Event.EventType.BIRTH,
                    date=self.birth_date,
                    date_text=formats.date_format(self.birth_date, "DATE_FORMAT") if self.birth_date else "",
                    place=self.birth_place,
                )
            )
        if Event.EventType.DEATH not in present and (self.death_date or self.death_place):
            synthetic.append(
                Event(
                    person=self,
                    event_type=Event.EventType.DEATH,
                    date=self.death_date,
                    date_text=formats.date_format(self.death_date, "DATE_FORMAT") if self.death_date else "",
                    place=self.death_place,
                )
            )

        # Les dates inconnues partent en fin de chronologie plutôt qu'au début.
        return sorted(
            events + synthetic,
            key=lambda e: (e.date is None, e.date or datetime.date.min, e.pk or 0),
        )

    @property
    def occupation(self):
        """Profession affichée sous le nom, comme Geneanet."""
        job = next(
            (e for e in self.events.all() if e.event_type == Event.EventType.OCCUPATION),
            None,
        )
        return job.description if job else ""


class Event(models.Model):
    """Un événement de la vie d'une personne (naissance, résidence, mariage...).

    Deux champs de date volontairement : `date` sert uniquement au tri, `date_text`
    porte le libellé fidèle à la source ("vers 1891", "entre 1893 et 1894"). Écraser
    une date approximative en date exacte donnerait un affichage faux.
    """

    class EventType(models.TextChoices):
        BIRTH = "birth", "Naissance"
        BAPTISM = "baptism", "Baptême"
        DEATH = "death", "Décès"
        BURIAL = "burial", "Inhumation"
        MARRIAGE = "marriage", "Mariage"
        DIVORCE = "divorce", "Divorce"
        RESIDENCE = "residence", "Résidence"
        CENSUS = "census", "Recensement"
        OCCUPATION = "occupation", "Profession"
        EDUCATION = "education", "Éducation"
        OTHER = "other", "Autre"

    person = models.ForeignKey(
        Person, verbose_name="personne", related_name="events", on_delete=models.CASCADE
    )
    event_type = models.CharField(
        "type d'événement", max_length=20, choices=EventType.choices, default=EventType.OTHER
    )
    # Étiquette libre pour les événements sans type dédié (ex: "Service militaire").
    label = models.CharField("intitulé", max_length=120, blank=True)

    date = models.DateField("date (pour le tri)", null=True, blank=True)
    date_text = models.CharField("date affichée", max_length=120, blank=True)
    place = models.CharField("lieu", max_length=300, blank=True)
    description = models.TextField("détail", blank=True)

    related_person = models.ForeignKey(
        Person,
        verbose_name="personne associée",
        related_name="events_as_related",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Le conjoint pour un mariage, par exemple.",
    )

    class Meta:
        verbose_name = "événement"
        verbose_name_plural = "événements"
        ordering = ["date", "id"]
        indexes = [models.Index(fields=["person", "date"])]

    def __str__(self):
        return f"{self.title} — {self.person}"

    @property
    def title(self):
        return self.label or self.get_event_type_display()


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
