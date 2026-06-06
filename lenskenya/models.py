import hashlib
import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The email field must be set.')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_superuser', True)

        # Adjusted to check against the refactored class definition
        if extra_fields.get('role') != User.Role.ADMIN:
            raise ValueError('Superuser must have role=admin.')

        # Ensure required fields are handled if passed down
        extra_fields.setdefault('first_name', 'Admin')
        extra_fields.setdefault('last_name', 'System')

        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    class Role(models.TextChoices):
        BUYER = 'buyer', 'Buyer'
        CONTRIBUTOR = 'contributor', 'Contributor'
        ADMIN = 'admin', 'Admin'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
	# Keep this temporarily so Django can read the old data
    name = models.CharField(max_length=255, blank=True, default='')
	
    # ─── REFRACTORED NAME FIELDS ──────────────────────────────────────
    first_name = models.CharField(max_length=150, blank=True, default='')
    last_name = models.CharField(max_length=150, blank=True, default='')
    
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128, db_column='password')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.BUYER)
    
    # Kept your exact db_column mapping and Safaricom / Airtel / Telkom validator
    mpesa_phone = models.CharField(
        max_length=13,
        blank=True,
        null=True,
        db_column='phone_number',
        validators=[RegexValidator(regex=r'^(\+254|0)[17][0-9]{8}$')],
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    # Adding these here ensures tools like standard django createsuperuser CLI prompt for them
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email'], name='users_email_idx'),
            models.Index(fields=['role'], name='users_role_idx'),
        ]

    @property
    def user_id(self):
        return self.id

    # Dynamic property to maintain backward compatibility if any service checks .name
    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_staff(self):
        return self.role == self.Role.ADMIN

    @property
    def is_active(self):
        return True

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if self.pk is not None:
            original_role = type(self).objects.filter(pk=self.pk).values_list('role', flat=True).first()
            if original_role is not None and self.role != original_role:
                from django.core.exceptions import ValidationError
                raise ValidationError({'role': 'Role is immutable after account creation.'})
        super().save(*args, **kwargs)


class Photo(TimestampedModel):
	class LicenseType(models.TextChoices):
		FREE_ATTRIBUTION = 'Free_Attribution', 'Free Attribution'
		COMMERCIAL_PAID = 'Commercial_Paid', 'Commercial Paid'

	photo_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	contributor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='photos', db_column='user_id')
	title = models.CharField(max_length=255)
	description = models.TextField(blank=True)
	county = models.CharField(max_length=100, blank=True, default='')
	county_code = models.PositiveSmallIntegerField(blank=True, null=True)
	license_type = models.CharField(max_length=30, choices=LicenseType.choices, default=LicenseType.FREE_ATTRIBUTION)
	price_kes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	watermarked_preview_url = models.URLField(max_length=1000, blank=True, null=True, db_column='watermarked_preview')
	secure_raw_s3_key = models.CharField(max_length=1024, db_column='raw_secure_file')
	tags = ArrayField(models.CharField(max_length=100), default=list, blank=True)
	sheng_tags = ArrayField(models.CharField(max_length=100), default=list, blank=True)
	formal_tags = ArrayField(models.CharField(max_length=100), default=list, blank=True)
	views = models.PositiveIntegerField(default=0)
	downloads = models.PositiveIntegerField(default=0, db_column='clicks')
	likes = models.PositiveIntegerField(default=0)
	class Status(models.TextChoices):
		ACTIVE = 'active', 'Active'
		PENDING = 'pending', 'Pending'
		PROCESSING = 'processing', 'Processing'

	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	is_active = models.BooleanField(default=True)

	class Meta:
		db_table = 'photos'
		indexes = [
			models.Index(fields=['contributor'], name='photos_contributor_idx'),
			models.Index(fields=['county'], name='photos_county_idx'),
			models.Index(fields=['county_code'], name='photos_county_code_idx'),
			models.Index(fields=['license_type'], name='photos_license_type_idx'),
			models.Index(fields=['created_at'], name='photos_created_at_idx'),
			models.Index(fields=['status', 'created_at'], name='photos_status_created_idx'),
			models.Index(fields=['status', 'county'], name='photos_status_county_idx'),
			models.Index(models.F('views') + models.F('downloads') + models.F('likes'), name='photos_popularity_idx'),
			GinIndex(fields=['tags'], name='photos_tags_gin'),
			GinIndex(fields=['sheng_tags'], name='photos_sheng_tags_gin'),
			GinIndex(fields=['formal_tags'], name='photos_formal_tags_gin'),
		]

	def __str__(self):
		return self.title

	@property
	def id(self):
		return self.photo_id

	@property
	def image_url(self):
		return self.watermarked_preview_url

	def save(self, *args, **kwargs):
		if not self.tags:
			merged_tags = list(dict.fromkeys((self.sheng_tags or []) + (self.formal_tags or [])))
			self.tags = merged_tags
		super().save(*args, **kwargs)


class Transaction(TimestampedModel):
	class Status(models.TextChoices):
		PENDING = 'pending', 'Pending'
		COMPLETED = 'completed', 'Completed'
		FAILED = 'failed', 'Failed'

	transaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='transactions', db_column='buyer_id')
	photo = models.ForeignKey(Photo, on_delete=models.PROTECT, related_name='transactions', db_column='photo_id')
	mpesa_receipt_no = models.CharField(max_length=100, unique=True)
	amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
	contributor_cut = models.DecimalField(max_digits=12, decimal_places=2)
	platform_cut = models.DecimalField(max_digits=12, decimal_places=2)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

	class Meta:
		db_table = 'transactions'
		constraints = [
			models.CheckConstraint(condition=Q(amount_paid__gt=0), name='transactions_amount_paid_gt_0'),
			models.CheckConstraint(condition=Q(contributor_cut__gte=0), name='transactions_contributor_cut_gte_0'),
			models.CheckConstraint(condition=Q(platform_cut__gte=0), name='transactions_platform_cut_gte_0'),
			models.CheckConstraint(
				condition=Q(amount_paid=F('contributor_cut') + F('platform_cut')),
				name='transactions_split_equals_amount_paid',
			),
		]
		indexes = [
			models.Index(fields=['buyer'], name='transactions_buyer_idx'),
			models.Index(fields=['photo'], name='transactions_photo_idx'),
			models.Index(fields=['status'], name='transactions_status_idx'),
			models.Index(fields=['created_at'], name='transactions_created_at_idx'),
		]

	def clean(self):
		super().clean()
		if self.contributor_cut is not None and self.platform_cut is not None and self.amount_paid is not None:
			if self.contributor_cut + self.platform_cut != self.amount_paid:
				from django.core.exceptions import ValidationError

				raise ValidationError({'platform_cut': 'Revenue split must equal amount_paid.'})

	def __str__(self):
		return f'{self.mpesa_receipt_no} ({self.status})'


class License(TimestampedModel):
	license_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	transaction = models.OneToOneField(Transaction, on_delete=models.PROTECT, related_name='license', db_column='transaction_id')
	photo = models.ForeignKey(Photo, on_delete=models.PROTECT, related_name='licenses', db_column='photo_id')
	buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='licenses', db_column='buyer_id')
	license_pdf_url = models.URLField(max_length=1000)
	issued_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = 'licenses'
		indexes = [
			models.Index(fields=['photo'], name='licenses_photo_idx'),
			models.Index(fields=['buyer'], name='licenses_buyer_idx'),
			models.Index(fields=['issued_at'], name='licenses_issued_at_idx'),
		]

	def save(self, *args, **kwargs):
		if self.transaction_id and not self.photo_id:
			self.photo = self.transaction.photo
		if self.transaction_id and not self.buyer_id:
			self.buyer = self.transaction.buyer
		super().save(*args, **kwargs)

	def __str__(self):
		return str(self.license_id)


class RefreshToken(TimestampedModel):
	refresh_token_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='instance_id')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='refresh_tokens', db_column='user_id')
	token_hash = models.CharField(max_length=64, unique=True)
	jti = models.CharField(max_length=64, unique=True)
	expires_at = models.DateTimeField()
	revoked_at = models.DateTimeField(blank=True, null=True)
	last_used_at = models.DateTimeField(blank=True, null=True)

	class Meta:
		db_table = 'refresh_tokens'
		indexes = [
			models.Index(fields=['user'], name='refresh_tokens_user_idx'),
			models.Index(fields=['expires_at'], name='refresh_tokens_expires_at_idx'),
			models.Index(fields=['revoked_at'], name='refresh_tokens_revoked_at_idx'),
		]

	@staticmethod
	def hash_value(raw_token: str) -> str:
		return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

	def revoke(self):
		from django.utils import timezone

		self.revoked_at = timezone.now()
		self.save(update_fields=['revoked_at', 'updated_at'])

	def __str__(self):
		return str(self.refresh_token_id)
