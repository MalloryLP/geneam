"""Import d'un arbre généalogique depuis un fichier GEDCOM (export Geneanet et autres).

Import en ajout pur : ne fusionne pas avec les personnes déjà en base, voir
`GedcomImportForm` pour l'avertissement affiché à l'utilisateur à ce sujet.
"""

import dataclasses
import datetime as dt

from django.db import transaction
from ged4py.parser import GedcomReader

from .models import Event, Parentage, Person, Union


@dataclasses.dataclass
class ImportSummary:
    persons: int = 0
    unions: int = 0
    parentages: int = 0
    events: int = 0


class GedcomImportError(Exception):
    """Le fichier n'a pas pu être parsé comme un GEDCOM valide."""


SEX_MAP = {"M": Person.Sex.MALE, "F": Person.Sex.FEMALE}

PEDI_MAP = {
    "adopted": Parentage.RelationType.ADOPTIVE,
    "foster": Parentage.RelationType.FOSTER,
}


def _relation_type(indi):
    """Type de filiation (biologique/adoptif/famille d'accueil) depuis `1 FAMC` / `2 PEDI`."""
    famc = indi.sub_tag("FAMC", follow=False)
    if famc is None:
        return Parentage.RelationType.BIOLOGICAL
    pedi = famc.sub_tag_value("PEDI")
    return PEDI_MAP.get((pedi or "").lower(), Parentage.RelationType.BIOLOGICAL)


def _gedcom_to_date(date_value):
    """Convertit une valeur de date GEDCOM (ged4py) en `datetime.date`, ou None.

    Les dates partielles (année seule, année+mois) sont approximées au 1er
    janvier / 1er du mois. Les dates non structurées (ex: `DateValuePhrase`)
    ou les plages (on prend alors la première borne) sont gérées au mieux.
    """
    if date_value is None:
        return None
    inner = getattr(date_value, "date", None) or getattr(date_value, "date1", None)
    if inner is None or inner.year is None:
        return None
    try:
        return dt.date(inner.year, inner.month_num or 1, inner.day or 1)
    except (ValueError, TypeError, OverflowError):
        return None


MONTHS_FR = {
    1: "janv.", 2: "févr.", 3: "mars", 4: "avr.", 5: "mai", 6: "juin",
    7: "juil.", 8: "août", 9: "sept.", 10: "oct.", 11: "nov.", 12: "déc.",
}


def _format_gedcom_day(gregorian):
    """'10 AUG 1872' -> '10 août 1872' ; année ou mois seuls gérés aussi."""
    if gregorian is None or gregorian.year is None:
        return ""
    month = MONTHS_FR.get(gregorian.month_num or 0)
    if gregorian.day and month:
        day = "1er" if gregorian.day == 1 else str(gregorian.day)
        return f"{day} {month} {gregorian.year}"
    if month:
        return f"{month} {gregorian.year}"
    return str(gregorian.year)


# Préfixes/gabarits français par nature de date GEDCOM, pour rester fidèle au flou
# de la source ("vers 1891") au lieu d'inventer une date exacte.
_DATE_KIND_TEMPLATES = {
    "ABOUT": "vers {d1}",
    "ESTIMATED": "estimé {d1}",
    "CALCULATED": "calculé {d1}",
    "INTERPRETED": "{d1}",
    "BEFORE": "avant {d1}",
    "AFTER": "après {d1}",
    "RANGE": "entre {d1} et {d2}",
    "PERIOD": "de {d1} à {d2}",
    "FROM": "à partir de {d1}",
    "TO": "jusqu'à {d1}",
}


def _format_gedcom_date(date_value):
    """Libellé français fidèle d'une date GEDCOM ('vers 1891', 'entre X et Y')."""
    if date_value is None:
        return ""
    kind = getattr(getattr(date_value, "kind", None), "name", "SIMPLE")
    if kind == "PHRASE":
        return str(getattr(date_value, "phrase", "") or "")

    d1 = _format_gedcom_day(getattr(date_value, "date", None) or getattr(date_value, "date1", None))
    d2 = _format_gedcom_day(getattr(date_value, "date2", None))
    if not d1:
        return ""
    template = _DATE_KIND_TEMPLATES.get(kind)
    if template is None:
        return d1
    if "{d2}" in template and not d2:
        # Intervalle amputé d'une borne : mieux vaut la borne connue que "entre X et ".
        return d1
    return template.format(d1=d1, d2=d2)


# Tags GEDCOM d'événements individuels -> type d'événement Geneam.
GEDCOM_TAG_TO_EVENT = {
    "BIRT": Event.EventType.BIRTH,
    "CHR": Event.EventType.BAPTISM,
    "BAPM": Event.EventType.BAPTISM,
    "DEAT": Event.EventType.DEATH,
    "BURI": Event.EventType.BURIAL,
    "CREM": Event.EventType.BURIAL,
    "RESI": Event.EventType.RESIDENCE,
    "CENS": Event.EventType.CENSUS,
    "OCCU": Event.EventType.OCCUPATION,
    "EDUC": Event.EventType.EDUCATION,
    "GRAD": Event.EventType.EDUCATION,
    "EVEN": Event.EventType.OTHER,
    "IMMI": Event.EventType.OTHER,
    "EMIG": Event.EventType.OTHER,
    "NATU": Event.EventType.OTHER,
    "RETI": Event.EventType.OTHER,
    "PROB": Event.EventType.OTHER,
    "WILL": Event.EventType.OTHER,
}

# Étiquettes lisibles pour les tags rangés en "Autre".
OTHER_TAG_LABELS = {
    "IMMI": "Immigration",
    "EMIG": "Émigration",
    "NATU": "Naturalisation",
    "RETI": "Retraite",
    "PROB": "Succession",
    "WILL": "Testament",
}


def _build_events(indi, person):
    """Un `Event` par tag d'événement porté par l'individu GEDCOM."""
    events = []
    for sub in indi.sub_records:
        event_type = GEDCOM_TAG_TO_EVENT.get(sub.tag)
        if event_type is None:
            continue

        date_value = sub.sub_tag_value("DATE")
        # Geneanet encode les événements sans tag dédié en `EVEN` + `TYPE`
        # (c'est ainsi qu'arrive "Service militaire").
        label = (sub.sub_tag_value("TYPE") or "").strip() or OTHER_TAG_LABELS.get(sub.tag, "")
        # OCCU/EVEN portent leur intitulé dans la valeur du tag lui-même.
        value = (sub.value or "").strip() if isinstance(sub.value, str) else ""
        if sub.tag == "EVEN" and not label:
            label = value

        events.append(
            Event(
                person=person,
                event_type=event_type,
                label=label,
                date=_gedcom_to_date(date_value),
                date_text=_format_gedcom_date(date_value),
                place=(sub.sub_tag_value("PLAC") or "").strip(),
                description=value if sub.tag == "OCCU" else (sub.sub_tag_value("NOTE") or ""),
            )
        )
    return events


def _create_person(indi):
    name = indi.name
    birt = indi.sub_tag("BIRT")
    deat = indi.sub_tag("DEAT")
    return Person.objects.create(
        # `name.given` et non `name.first` : ce dernier ne renvoie que le premier
        # prénom et perdrait les prénoms composés ("Auguste Louis" -> "Auguste").
        first_name=(name.given or "").strip() if name else "",
        last_name=(name.surname or "").strip() if name else "",
        sex=SEX_MAP.get(indi.sex, Person.Sex.OTHER),
        birth_date=_gedcom_to_date(birt.sub_tag_value("DATE")) if birt else None,
        birth_place=(birt.sub_tag_value("PLAC") or "") if birt else "",
        death_date=_gedcom_to_date(deat.sub_tag_value("DATE")) if deat else None,
        death_place=(deat.sub_tag_value("PLAC") or "") if deat else "",
    )


def import_gedcom(file_obj):
    """Importe un fichier GEDCOM (objet fichier ouvert en binaire) et renvoie un résumé.

    Toute l'opération est faite dans une transaction : si le fichier est mal
    formé en cours de route, rien n'est importé.

    ged4py résout les pointeurs (père/mère, HUSB/WIFE...) paresseusement en
    relisant le fichier à la demande : tout le traitement doit donc rester à
    l'intérieur du `with GedcomReader(...)`, avant que le fichier ne soit fermé.
    """
    summary = ImportSummary()

    try:
        with GedcomReader(file_obj) as parser:
            individuals = list(parser.records0("INDI"))
            families = list(parser.records0("FAM"))

            with transaction.atomic():
                persons_by_xref = {}
                for indi in individuals:
                    persons_by_xref[indi.xref_id] = _create_person(indi)
                summary.persons = len(persons_by_xref)

                # Événements individuels (naissance, résidence, recensement, profession...).
                individual_events = []
                for indi in individuals:
                    individual_events.extend(_build_events(indi, persons_by_xref[indi.xref_id]))
                Event.objects.bulk_create(individual_events)
                summary.events += len(individual_events)

                # Filiations : ged4py résout le père/la mère "primaires" de chaque individu.
                for indi in individuals:
                    child = persons_by_xref[indi.xref_id]
                    relation_type = _relation_type(indi)
                    for parent_indi in (indi.father, indi.mother):
                        if parent_indi is not None and parent_indi.xref_id in persons_by_xref:
                            Parentage.objects.get_or_create(
                                parent=persons_by_xref[parent_indi.xref_id],
                                child=child,
                                defaults={"relation_type": relation_type},
                            )
                            summary.parentages += 1

                # Unions : une par famille (FAM) ayant un époux et une épouse.
                couple_events = []
                for fam in families:
                    husb = fam.sub_tag("HUSB")
                    wife = fam.sub_tag("WIFE")
                    if husb is None or wife is None:
                        continue
                    if husb.xref_id not in persons_by_xref or wife.xref_id not in persons_by_xref:
                        continue
                    person1 = persons_by_xref[husb.xref_id]
                    person2 = persons_by_xref[wife.xref_id]
                    marr = fam.sub_tag("MARR")
                    Union.objects.create(
                        person1=person1,
                        person2=person2,
                        union_type=Union.UnionType.MARRIAGE if marr else Union.UnionType.OTHER,
                        start_date=_gedcom_to_date(marr.sub_tag_value("DATE")) if marr else None,
                    )
                    summary.unions += 1

                    # Mariage/divorce : un événement pour chacun des deux conjoints, afin
                    # qu'il apparaisse dans les deux chronologies avec "avec <l'autre>".
                    for tag, event_type in (("MARR", Event.EventType.MARRIAGE),
                                            ("DIV", Event.EventType.DIVORCE)):
                        record = fam.sub_tag(tag)
                        if record is None:
                            continue
                        date_value = record.sub_tag_value("DATE")
                        place = (record.sub_tag_value("PLAC") or "").strip()
                        for subject, spouse in ((person1, person2), (person2, person1)):
                            couple_events.append(
                                Event(
                                    person=subject,
                                    event_type=event_type,
                                    date=_gedcom_to_date(date_value),
                                    date_text=_format_gedcom_date(date_value),
                                    place=place,
                                    related_person=spouse,
                                )
                            )
                Event.objects.bulk_create(couple_events)
                summary.events += len(couple_events)
    except GedcomImportError:
        raise
    except Exception as exc:  # ged4py ne définit pas d'exception dédiée pour un fichier invalide
        raise GedcomImportError(str(exc)) from exc

    return summary
