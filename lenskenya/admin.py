from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import License, Photo, Transaction, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	model = User
	list_display = ('email', 'role', 'mpesa_phone', 'is_staff')
	list_filter = ('role',)
	ordering = ('email',)
	search_fields = ('email', 'mpesa_phone')
	fieldsets = (
		(None, {'fields': ('email', 'password')}),
		('Permissions', {'fields': ('role', 'is_superuser')}),
		('Payouts', {'fields': ('mpesa_phone',)}),
		('Dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
	)
	readonly_fields = ('role', 'last_login', 'created_at', 'updated_at')
	add_fieldsets = (
		(None, {
			'classes': ('wide',),
			'fields': ('email', 'password1', 'password2', 'role', 'mpesa_phone'),
		}),
	)


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
	list_display = ('title', 'contributor', 'county', 'is_active', 'created_at')
	list_filter = ('county', 'is_active')
	search_fields = ('title', 'description', 'county', 'sheng_tags', 'formal_tags')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
	list_display = ('mpesa_receipt_no', 'buyer', 'photo', 'amount_paid', 'status', 'created_at')
	list_filter = ('status', 'created_at')
	search_fields = ('mpesa_receipt_no',)


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
	list_display = ('license_id', 'transaction', 'buyer', 'photo', 'issued_at')
	search_fields = ('license_id', 'transaction__mpesa_receipt_no')
