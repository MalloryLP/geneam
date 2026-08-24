from django import template

register = template.Library()


@register.simple_tag
def person_years(person):
    """Formatte '1950 – 2020', '1950 –', '? – 2020' ou '' selon les dates connues."""
    birth = person.birth_date.year if person.birth_date else None
    death = person.death_date.year if person.death_date else None
    if birth and death:
        return f"{birth} – {death}"
    if birth:
        return f"{birth} –"
    if death:
        return f"? – {death}"
    return ""
