from django.contrib import admin

from .models import Parentage, Person, Union


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("full_name", "sex", "birth_date", "death_date")
    search_fields = ("first_name", "last_name", "notes")
    list_filter = ("sex",)


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
