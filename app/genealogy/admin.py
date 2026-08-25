from django.contrib import admin

from .models import Event, Parentage, Person, Union


class EventInline(admin.TabularInline):
    model = Event
    fk_name = "person"
    extra = 0
    fields = ("event_type", "label", "date", "date_text", "place", "related_person")
    autocomplete_fields = ("related_person",)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("full_name", "sex", "birth_date", "death_date")
    search_fields = ("first_name", "last_name", "notes")
    list_filter = ("sex",)
    inlines = [EventInline]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("person", "title", "date_text", "place")
    list_filter = ("event_type",)
    search_fields = ("person__first_name", "person__last_name", "label", "place")
    autocomplete_fields = ("person", "related_person")


@admin.register(Parentage)
class ParentageAdmin(admin.ModelAdmin):
    list_display = ("parent", "child", "relation_type")
    list_filter = ("relation_type",)
    autocomplete_fields = ("parent", "child")


@admin.register(Union)
class UnionAdmin(admin.ModelAdmin):
    list_display = ("person1", "person2", "union_type", "start_date", "end_date")
    list_filter = ("union_type",)
    autocomplete_fields = ("person1", "person2")
