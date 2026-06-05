from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers


AuthHeader = [
	OpenApiParameter(
		name='Authorization',
		type=OpenApiTypes.STR,
		location=OpenApiParameter.HEADER,
		description='Bearer access token.',
		required=True,
	)
]

PhotoListQuery = [
	OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY, description='Page number.'),
	OpenApiParameter('limit', OpenApiTypes.INT, OpenApiParameter.QUERY, description='Page size, max 50.'),
	OpenApiParameter('sort', OpenApiTypes.STR, OpenApiParameter.QUERY, enum=['newest', 'popular']),
	OpenApiParameter('search', OpenApiTypes.STR, OpenApiParameter.QUERY),
	OpenApiParameter('tag', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Comma-separated tags.'),
	OpenApiParameter('county', OpenApiTypes.STR, OpenApiParameter.QUERY),
	OpenApiParameter('county_code', OpenApiTypes.INT, OpenApiParameter.QUERY),
	OpenApiParameter('license_type', OpenApiTypes.STR, OpenApiParameter.QUERY, enum=['Free_Attribution', 'Commercial_Paid']),
]

StatusMessageSerializer = inline_serializer(
	name='StatusMessage',
	fields={
		'status': serializers.CharField(),
		'message': serializers.CharField(required=False),
	},
)

UserProfileSerializer = inline_serializer(
	name='UserProfile',
	fields={
		'user_id': serializers.UUIDField(),
		'name': serializers.CharField(),
		'email': serializers.EmailField(),
		'role': serializers.CharField(),
		'mpesa_phone': serializers.CharField(allow_null=True, required=False),
		'created_at': serializers.DateTimeField(),
	},
)

PhotoSummarySerializer = inline_serializer(
	name='PhotoSummary',
	fields={
		'photo_id': serializers.UUIDField(),
		'title': serializers.CharField(),
		'watermarked_preview_url': serializers.URLField(allow_null=True, required=False),
		'image_url': serializers.URLField(allow_null=True, required=False),
		'county': serializers.CharField(),
		'sheng_tags': serializers.ListField(child=serializers.CharField()),
		'formal_tags': serializers.ListField(child=serializers.CharField()),
		'tags': serializers.ListField(child=serializers.CharField()),
		'county_code': serializers.IntegerField(allow_null=True),
		'price_kes': serializers.FloatField(),
		'license_type': serializers.CharField(),
	},
)

PhotoDetailSerializer = inline_serializer(
	name='PhotoDetail',
	fields={
		'photo_id': serializers.UUIDField(),
		'contributor': inline_serializer(
			name='PhotoContributor',
			fields={
				'user_id': serializers.UUIDField(),
				'name': serializers.CharField(),
			},
		),
		'title': serializers.CharField(),
		'description': serializers.CharField(),
		'watermarked_preview_url': serializers.URLField(allow_null=True, required=False),
		'image_url': serializers.URLField(allow_null=True, required=False),
		'county': serializers.CharField(),
		'sheng_tags': serializers.ListField(child=serializers.CharField()),
		'formal_tags': serializers.ListField(child=serializers.CharField()),
		'tags': serializers.ListField(child=serializers.CharField()),
		'county_code': serializers.IntegerField(allow_null=True),
		'license_type': serializers.CharField(),
		'price_kes': serializers.FloatField(),
		'created_at': serializers.DateTimeField(),
	},
)

PhotoListResponseSerializer = inline_serializer(
	name='PhotoListResponse',
	fields={
		'status': serializers.CharField(),
		'pagination': inline_serializer(
			name='Pagination',
			fields={
				'current_page': serializers.IntegerField(),
				'total_pages': serializers.IntegerField(),
				'total_items': serializers.IntegerField(),
			},
		),
		'data': PhotoSummarySerializer,
	},
)

PhotoDetailResponseSerializer = inline_serializer(
	name='PhotoDetailResponse',
	fields={
		'status': serializers.CharField(),
		'data': PhotoDetailSerializer,
	},
)

RegisterRequestSerializer = inline_serializer(
	name='RegisterRequest',
	fields={
		'name': serializers.CharField(),
		'email': serializers.EmailField(),
		'password': serializers.CharField(write_only=True),
		'role': serializers.ChoiceField(choices=['buyer', 'contributor']),
	},
)

RegisterResponseSerializer = inline_serializer(
	name='RegisterResponse',
	fields={
		'status': serializers.CharField(),
		'message': serializers.CharField(),
		'data': inline_serializer(
			name='RegisteredUser',
			fields={
				'user_id': serializers.UUIDField(),
				'name': serializers.CharField(),
				'email': serializers.EmailField(),
				'role': serializers.CharField(),
			},
		),
	},
)

LoginRequestSerializer = inline_serializer(
	name='LoginRequest',
	fields={
		'email': serializers.EmailField(),
		'password': serializers.CharField(write_only=True),
	},
)

LoginResponseSerializer = inline_serializer(
	name='LoginResponse',
	fields={
		'status': serializers.CharField(),
		'token': serializers.CharField(),
		'expires_in': serializers.IntegerField(),
		'user': inline_serializer(
			name='AuthUser',
			fields={
				'user_id': serializers.UUIDField(),
				'name': serializers.CharField(),
				'role': serializers.CharField(),
			},
		),
	},
)

RefreshRequestSerializer = inline_serializer(
	name='RefreshRequest',
	fields={'refresh_token': serializers.CharField()},
)

RefreshResponseSerializer = inline_serializer(
	name='RefreshResponse',
	fields={
		'status': serializers.CharField(),
		'data': inline_serializer(
			name='RefreshTokenData',
			fields={
				'access_token': serializers.CharField(),
				'access_token_expires_in': serializers.IntegerField(),
				'refresh_token': serializers.CharField(),
				'refresh_token_expires_at': serializers.DateTimeField(),
			},
		),
	},
)

RefreshTokenRequestSerializer = inline_serializer(
	name='RefreshTokenRequest',
	fields={'refresh_token': serializers.CharField(required=False)},
)

ProfileResponseSerializer = inline_serializer(
	name='ProfileResponse',
	fields={
		'status': serializers.CharField(),
		'data': UserProfileSerializer,
	},
)

ContributorDashboardResponseSerializer = inline_serializer(
	name='ContributorDashboardResponse',
	fields={
		'status': serializers.CharField(),
		'data': inline_serializer(
			name='ContributorDashboard',
			fields={
				'wallet': inline_serializer(
					name='ContributorWallet',
					fields={
						'available_balance_kes': serializers.FloatField(),
						'total_earned_kes': serializers.FloatField(),
					},
				),
				'statistics': inline_serializer(
					name='ContributorStatistics',
					fields={
						'total_uploads': serializers.IntegerField(),
						'active_images': serializers.IntegerField(),
						'processing_images': serializers.IntegerField(),
						'total_downloads': serializers.IntegerField(),
					},
				),
			},
		),
	},
)

UploadIntentRequestSerializer = inline_serializer(
	name='UploadIntentRequest',
	fields={
		'title': serializers.CharField(),
		'filename': serializers.CharField(),
		'file_type': serializers.CharField(),
		'file_size': serializers.IntegerField(),
	},
)

UploadIntentResponseSerializer = inline_serializer(
	name='UploadIntentResponse',
	fields={
		'status': serializers.CharField(),
		'data': inline_serializer(
			name='UploadIntentData',
			fields={
				'photo_id': serializers.UUIDField(),
				'upload_url': serializers.URLField(),
				'fields': serializers.DictField(child=serializers.CharField()),
			},
		),
	},
)

FinalizePhotoRequestSerializer = inline_serializer(
	name='FinalizePhotoRequest',
	fields={
		'sheng_tags': serializers.ListField(child=serializers.CharField()),
		'formal_tags': serializers.ListField(child=serializers.CharField()),
		'county_code': serializers.IntegerField(),
		'license_type': serializers.ChoiceField(choices=['Free_Attribution', 'Commercial_Paid']),
		'price_kes': serializers.DecimalField(max_digits=12, decimal_places=2),
		'description': serializers.CharField(required=False, allow_blank=True),
	},
)

FinalizePhotoResponseSerializer = inline_serializer(
	name='FinalizePhotoResponse',
	fields={
		'status': serializers.CharField(),
		'message': serializers.CharField(),
		'photo_id': serializers.UUIDField(),
		'current_state': serializers.CharField(),
	},
)

DownloadTokenResponseSerializer = inline_serializer(
	name='DownloadTokenResponse',
	fields={
		'status': serializers.CharField(),
		'data': inline_serializer(
			name='DownloadTokenData',
			fields={
				'download_url': serializers.URLField(),
				'expires_in_seconds': serializers.IntegerField(),
				'license_pdf_url': serializers.URLField(allow_null=True, required=False),
			},
		),
	},
)
