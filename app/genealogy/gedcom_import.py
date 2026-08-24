"""Import d'un arbre généalogique depuis un fichier GEDCOM (export Geneanet et autres).

Import en ajout pur : ne fusionne pas avec les personnes déjà en base, voir
`GedcomImportForm` pour l'avertissement affiché à l'utilisateur à ce sujet.
"""

import dataclasses
import datetime as dt

from django.db import transaction
from ged4py.parser import GedcomReader

from .models import Parentage, Person, Union


@dataclasses.dataclass
class ImportSummary:
    persons: int = 0
    unions: int = 0
    parentages: int = 0


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


def _create_person(indi):
    name = indi.name
    birt = indi.sub_tag("BIRT")
    deat = indi.sub_tag("DEAT")
    return Person.objects.create(
        first_name=(name.first or "").strip() if name else "",
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
                for fam in families:
                    husb = fam.sub_tag("HUSB")
                    wife = fam.sub_tag("WIFE")
                    if husb is None or wife is None:
                        continue
                    if husb.xref_id not in persons_by_xref or wife.xref_id not in persons_by_xref:
                        continue
                    marr = fam.sub_tag("MARR")
                    Union.objects.create(
                        person1=persons_by_xref[husb.xref_id],
                        person2=persons_by_xref[wife.xref_id],
                        union_type=Union.UnionType.MARRIAGE if marr else Union.UnionType.OTHER,
                        start_date=_gedcom_to_date(marr.sub_tag_value("DATE")) if marr else None,
                    )
                    summary.unions += 1
    except GedcomImportError:
        raise
    except Exception as exc:  # ged4py ne définit pas d'exception dédiée pour un fichier invalide
        raise GedcomImportError(str(exc)) from exc

    return summary
