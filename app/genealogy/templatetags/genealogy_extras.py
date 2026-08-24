from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Petites icônes SVG faites main (24x24, trait uniforme) — pas de police/CDN externe pour
# rester utilisable sans accès internet.
_ICONS = {
    "menu": '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>'
    '<line x1="3" y1="18" x2="21" y2="18"/>',
    "close": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "home": '<path d="M3 11.5 12 4l9 7.5"/>'
    '<path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9"/>',
    "add": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "search": '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "person": '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>',
    "tree": '<circle cx="12" cy="4" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>'
    '<path d="M12 6v4M12 10 6 16M12 10l6 6"/>',
    "import": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 19h16"/>',
    "admin": '<line x1="4" y1="6" x2="20" y2="6"/><circle cx="9" cy="6" r="2"/>'
    '<line x1="4" y1="12" x2="20" y2="12"/><circle cx="15" cy="12" r="2"/>'
    '<line x1="4" y1="18" x2="20" y2="18"/><circle cx="9" cy="18" r="2"/>',
    "edit": '<path d="M4 20h4l10.5-10.5a1.5 1.5 0 0 0 0-2.1l-1.9-1.9a1.5 1.5 0 0 0-2.1 0L4 16z"/>'
    '<path d="M13.5 6.5l4 4"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "birth": '<line x1="12" y1="3" x2="12" y2="21"/><line x1="4" y1="7" x2="20" y2="17"/>'
    '<line x1="20" y1="7" x2="4" y2="17"/>',
    "death": '<line x1="12" y1="3" x2="12" y2="21"/><line x1="6" y1="9" x2="18" y2="9"/>',
    "union": '<path d="M8 12l-2 2a3 3 0 0 0 4 4l2-2"/><path d="M16 12l2-2a3 3 0 0 0-4-4l-2 2"/>'
    '<path d="M9 15l6-6"/>',
    "chevron": '<polyline points="9 6 15 12 9 18"/>',
}


@register.simple_tag
def icon(name, css_class=""):
    """Retourne une icône SVG inline. Usage : {% icon "home" %} ou {% icon "home" "big" %}."""
    inner = _ICONS.get(name, "")
    classes = f"icon icon-{name} {css_class}".strip()
    return mark_safe(
        f'<svg class="{classes}" viewBox="0 0 24 24" width="20" height="20" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{inner}</svg>'
    )


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
