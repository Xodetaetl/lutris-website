from accounts import models
from django.contrib import admin


class UserAdmin(admin.ModelAdmin):
    list_display = ('__unicode__', 'email')
    search_fields = ('username', 'email')

admin.site.register(models.User, UserAdmin)
