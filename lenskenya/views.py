import datetime as dt
import json
import math
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view

from .api_schema import (
	AuthHeader,
	ContributorDashboardResponseSerializer,
	DownloadTokenResponseSerializer,
	FinalizePhotoRequestSerializer,
	FinalizePhotoResponseSerializer,
	LoginRequestSerializer,
	LoginResponseSerializer,
	PhotoDetailResponseSerializer,
	PhotoListQuery,
	PhotoListResponseSerializer,
	ProfileResponseSerializer,
	RefreshRequestSerializer,
	RefreshResponseSerializer,
	RefreshTokenRequestSerializer,
	RegisterRequestSerializer,
	RegisterResponseSerializer,
	StatusMessageSerializer,
	UploadIntentRequestSerializer,
	UploadIntentResponseSerializer,
)
from .jwt_auth import access_token_ttl_seconds, authenticate_user, decode_access_token, issue_access_token, login_response, rotate_refresh_token
from .models import License, Photo, RefreshToken, Transaction, User
from .storage import MAX_RAW_UPLOAD_BYTES, create_raw_download_url, create_raw_upload_post


def _json_body(request):
	if not request.body:
		return {}
	return json.loads(request.body.decode('utf-8'))


def _validation_error_response(exc: ValidationError) -> JsonResponse:
	message = exc.messages[0] if exc.messages else 'Invalid request.'
	return JsonResponse({'detail': message}, status=400)


def _parse_int(value, default, minimum, maximum):
	try:
		parsed = int(value)
	except (TypeError, ValueError):
		return default
	return max(minimum, min(parsed, maximum))


def _parse_tags(value):
	if not value:
		return []
	return list(dict.fromkeys(tag.strip() for tag in str(value).split(',') if tag.strip()))


def _parse_optional_int(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def _parse_decimal(value):
	if value is None or value == '':
		return None
	try:
		return Decimal(str(value))
	except (TypeError, ValueError, ArithmeticError):
		return None


def _parse_list_field(value):
	if value is None:
		return None
	if isinstance(value, list):
		return [str(item).strip() for item in value if str(item).strip()]
	return None


def _parse_iso_z(value):
	if value is None:
		return None
	if timezone.is_naive(value):
		value = timezone.make_aware(value, dt.timezone.utc)
	return value.isoformat().replace('+00:00', 'Z')


def _decimal_to_number(value):
	if value is None:
		return None
	return float(value)


def _success_response(data=None, message=None, status=200):
	payload = {'status': 'success'}
	if message is not None:
		payload['message'] = message
	if data is not None:
		payload['data'] = data
	return JsonResponse(payload, status=status)


def _error_response(message, status=400):
	return JsonResponse({'status': 'error', 'message': message}, status=status)


def _normalized_license_type(value):
	if not value:
		return None
	value = str(value).strip()
	for choice_value, _ in Photo.LicenseType.choices:
		if choice_value.lower() == value.lower():
			return choice_value
	return None


def _normalized_role(value):
	if not value:
		return User.Role.BUYER
	value = str(value).strip().lower()
	if value in {User.Role.BUYER, User.Role.CONTRIBUTOR}:
		return value
	return None


def _auth_user_payload(user: User):
	return {
		'user_id': str(user.pk),
		'first_name': user.first_name,
		'last_name': user.last_name,
		'role': user.role,
	}


def _profile_payload(user: User):
	return {
		'user_id': str(user.pk),
		'first_name': user.first_name,
		'last_name': user.last_name,
		'email': user.email,
		'role': user.role,
		'mpesa_phone': user.mpesa_phone,
		'created_at': _parse_iso_z(user.created_at),
	}


def _photo_list_item(photo: Photo):
	return {
		'photo_id': str(photo.photo_id),
		'title': photo.title,
		'watermarked_preview_url': photo.watermarked_preview_url,
		'image_url': photo.watermarked_preview_url,
		'county': photo.county,
		'sheng_tags': photo.sheng_tags,
		'formal_tags': photo.formal_tags,
		'tags': photo.tags,
		'county_code': photo.county_code,
		'price_kes': _decimal_to_number(photo.price_kes),
		'license_type': photo.license_type,
	}


def _photo_detail_item(photo: Photo):
	return {
		'photo_id': str(photo.photo_id),
		'contributor': {
			'user_id': str(photo.contributor_id),
			'first_name': photo.contributor.first_name,
			'last_name': photo.contributor.last_name,
		},
		'title': photo.title,
		'description': photo.description,
		'watermarked_preview_url': photo.watermarked_preview_url,
		'image_url': photo.watermarked_preview_url,
		'county': photo.county,
		'sheng_tags': photo.sheng_tags,
		'formal_tags': photo.formal_tags,
		'tags': photo.tags,
		'county_code': photo.county_code,
		'license_type': photo.license_type,
		'price_kes': _decimal_to_number(photo.price_kes),
		'created_at': _parse_iso_z(photo.created_at),
	}


def _extract_bearer_user(request):
	authorization = request.headers.get('Authorization', '')
	if not authorization.startswith('Bearer '):
		return None, _error_response('Unauthorized.', status=401)

	token = authorization.removeprefix('Bearer ').strip()
	try:
		payload = decode_access_token(token)
		user = User.objects.get(pk=payload['sub'])
		return user, None
	except Exception:
		return None, _error_response('Unauthorized.', status=401)


def _require_contributor(request):
	user, error = _extract_bearer_user(request)
	if error:
		return None, error
	if user.role != User.Role.CONTRIBUTOR:
		return None, _error_response('Forbidden.', status=403)
	return user, None


def _build_raw_key(photo_id: uuid.UUID, filename: str):
	clean_name = filename.replace('\\', '_').replace('/', '_').strip() or 'upload.raw'
	stamp = timezone.now()
	return f'raw/{stamp.year:04d}/{stamp.month:02d}/{photo_id}_{clean_name}'


def _queue_photo_processing(photo_id):
	try:
		from .tasks import process_photo_asset

		transaction.on_commit(lambda: process_photo_asset.delay(str(photo_id)))
	except Exception:
		pass


def _normalize_sort(value):
	value = (value or 'newest').strip().lower()
	if value not in {'newest', 'popular'}:
		return 'newest'
	return value


def _serialize_photo_summary(photo: Photo) -> dict:
	return {
		'id': str(photo.id),
		'title': photo.title,
		'image_url': photo.image_url,
		'county': photo.county,
		'tags': photo.tags,
		'views': photo.views,
		'likes': photo.likes,
		'created_at': photo.created_at.isoformat(),
	}


def _serialize_photo_detail(photo: Photo) -> dict:
	return {
		'id': str(photo.id),
		'title': photo.title,
		'description': photo.description,
		'image_url': photo.image_url,
		'county': photo.county,
		'tags': photo.tags,
		'views': photo.views,
		'likes': photo.likes,
		'downloads': photo.downloads,
		'created_at': photo.created_at.isoformat(),
		'uploader': {
			'id': str(photo.contributor_id),
			'first_name': getattr(photo.contributor, 'first_name', ''),
			'last_name': getattr(photo.contributor, 'last_name', ''),
		},
	}


@csrf_exempt
@extend_schema(
	tags=['Auth'],
	request=LoginRequestSerializer,
	responses={200: LoginResponseSerializer},
	summary='Login with email and password',
)
@api_view(['POST'])
def login_view(request):
	return auth_login_view(request)


@csrf_exempt
@extend_schema(
	tags=['Auth'],
	request=RefreshRequestSerializer,
	responses={200: RefreshResponseSerializer},
	summary='Refresh an access token',
)
@api_view(['POST'])
def refresh_view(request):
	try:
		payload = _json_body(request)
		refresh_token = payload.get('refresh_token')
		if not refresh_token:
			raise ValidationError('refresh_token is required.')
		user, new_refresh_token, new_record = rotate_refresh_token(refresh_token)
		access_token = issue_access_token(user)
		return _success_response(data={
			'access_token': access_token,
			'access_token_expires_in': access_token_ttl_seconds(),
			'refresh_token': new_refresh_token,
			'refresh_token_expires_at': new_record.expires_at.isoformat(),
		}, status=200)
	except ValidationError as exc:
		return _validation_error_response(exc)
	except (json.JSONDecodeError, TypeError, ValueError):
		return JsonResponse({'detail': 'Invalid JSON body.'}, status=400)


@csrf_exempt
@extend_schema(
	tags=['Auth'],
	request=RefreshTokenRequestSerializer,
	responses={200: StatusMessageSerializer},
	summary='Logout and revoke a refresh token',
)
@api_view(['POST'])
def logout_view(request):
	try:
		payload = _json_body(request)
		refresh_token = payload.get('refresh_token')
		if refresh_token:
			token_hash = RefreshToken.hash_value(refresh_token)
			record = RefreshToken.objects.filter(token_hash=token_hash, revoked_at__isnull=True).first()
			if record:
				record.revoke()
		return _success_response(message='Logged out.', status=200)
	except (json.JSONDecodeError, TypeError, ValueError):
		return JsonResponse({'detail': 'Invalid JSON body.'}, status=400)


@extend_schema(
	tags=['Photos'],
	parameters=PhotoListQuery,
	responses={200: PhotoListResponseSerializer},
	summary='List active photos',
)
@api_view(['GET'])
def photo_list_view(request):
	page = _parse_int(request.GET.get('page', 1), default=1, minimum=1, maximum=10**9)
	limit = _parse_int(request.GET.get('limit', 20), default=20, minimum=1, maximum=50)
	sort = _normalize_sort(request.GET.get('sort', 'newest'))
	search = (request.GET.get('search') or '').strip()
	tag_filter = _parse_tags(request.GET.get('tag'))
	county = (request.GET.get('county') or '').strip()
	county_code = _parse_optional_int(request.GET.get('county_code'))
	license_type = _normalized_license_type(request.GET.get('license_type'))

	queryset = Photo.objects.select_related('contributor').filter(status=Photo.Status.ACTIVE, is_active=True)

	if tag_filter:
		queryset = queryset.filter(tags__contains=tag_filter)

	if search:
		queryset = queryset.filter(
			Q(tags__contains=[search]) |
			Q(sheng_tags__contains=[search]) |
			Q(formal_tags__contains=[search])
		)

	if county:
		queryset = queryset.filter(county=county)

	if county_code is not None:
		queryset = queryset.filter(county_code=county_code)

	if license_type:
		queryset = queryset.filter(license_type=license_type)

	if sort == 'popular':
		queryset = queryset.annotate(popularity_score=F('views') + F('downloads') + F('likes')).order_by('-popularity_score')
	else:
		queryset = queryset.order_by('-created_at')

	total = queryset.count()
	offset = (page - 1) * limit
	results = [_photo_list_item(photo) for photo in queryset[offset:offset + limit]]
	total_pages = math.ceil(total / limit) if total else 0

	return JsonResponse({
		'status': 'success',
		'pagination': {
			'current_page': page,
			'total_pages': total_pages,
			'total_items': total,
		},
		'data': results,
	}, status=200)


@extend_schema(
	tags=['Photos'],
	responses={200: PhotoDetailResponseSerializer},
	summary='Get photo details',
)
@api_view(['GET'])
def photo_detail_view(request, photo_id):
	photo = get_object_or_404(Photo.objects.select_related('contributor'), photo_id=photo_id, status=Photo.Status.ACTIVE, is_active=True)
	return JsonResponse({'status': 'success', 'data': _photo_detail_item(photo)}, status=200)


@extend_schema(
	tags=['Auth'],
	parameters=AuthHeader,
	responses={200: ProfileResponseSerializer},
	summary='Get the current user',
)
@api_view(['GET'])
def me_view(request):
	user, error = _extract_bearer_user(request)
	if error:
		return error
	return _success_response(data=_profile_payload(user), status=200)


@csrf_exempt
@extend_schema(
	tags=['Auth'],
	request=RegisterRequestSerializer,
	responses={201: RegisterResponseSerializer},
	summary='Register a user',
)
@api_view(['POST'])
def auth_register_view(request):
    try:
        payload = _json_body(request)
        # 1. Extract the new split name fields from the payload
        first_name = (payload.get('first_name') or '').strip()
        last_name = (payload.get('last_name') or '').strip()
        email = (payload.get('email') or '').strip().lower()
        password = payload.get('password') or ''
        role = _normalized_role(payload.get('role'))

        # 2. Update validation assertions to require both values
        if not first_name:
            raise ValidationError('first_name is required.')
        if not last_name:
            raise ValidationError('last_name is required.')
        if not email:
            raise ValidationError('email is required.')
        if not password:
            raise ValidationError('password is required.')
        if role is None:
            raise ValidationError('role must be buyer or contributor.')
        if User.objects.filter(email=email).exists():
            raise ValidationError('A user with this email already exists.')

        # 3. Create the user using the split schema values
        user = User.objects.create_user(
            email=email, 
            password=password, 
            first_name=first_name, 
            last_name=last_name, 
            role=role
        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'User registered successfully',
            'data': {
                'user_id': str(user.pk),
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'role': user.role,
            },
        }, status=201)
    except ValidationError as exc:
        return _validation_error_response(exc)
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'detail': 'Invalid JSON body.'}, status=400)


@csrf_exempt
@extend_schema(
	tags=['Auth'],
	request=LoginRequestSerializer,
	responses={200: LoginResponseSerializer},
	summary='Login with email and password',
)
@api_view(['POST'])
def auth_login_view(request):
	try:
		payload = _json_body(request)
		user = authenticate_user(payload.get('email', ''), payload.get('password', ''))
		access_token = issue_access_token(user)
		return JsonResponse({
			'status': 'success',
			'token': access_token,
			'expires_in': access_token_ttl_seconds(),
			'user': _auth_user_payload(user),
		}, status=200)
	except ValidationError as exc:
		return _validation_error_response(exc)
	except (json.JSONDecodeError, TypeError, ValueError):
		return JsonResponse({'detail': 'Invalid JSON body.'}, status=400)


@extend_schema(
	tags=['Users'],
	parameters=AuthHeader,
	responses={200: ProfileResponseSerializer},
	summary='Get user profile',
)
@api_view(['GET'])
def profile_view(request):
	user, error = _extract_bearer_user(request)
	if error:
		return error
	return _success_response(data=_profile_payload(user), status=200)


@extend_schema(
	tags=['Contributor'],
	parameters=AuthHeader,
	responses={200: ContributorDashboardResponseSerializer},
	summary='Get contributor dashboard',
)
@api_view(['GET'])
def contributor_dashboard_view(request):
	user, error = _require_contributor(request)
	if error:
		return error

	photo_qs = Photo.objects.filter(contributor=user)
	total_uploads = photo_qs.count()
	active_images = photo_qs.filter(status=Photo.Status.ACTIVE, is_active=True).count()
	processing_images = photo_qs.filter(status=Photo.Status.PROCESSING).count()
	total_downloads = photo_qs.aggregate(total=Coalesce(Sum('downloads'), Value(0)))['total']
	total_earned = Transaction.objects.filter(photo__contributor=user, status=Transaction.Status.COMPLETED).aggregate(
		total=Coalesce(Sum('contributor_cut'), Value(Decimal('0.00')))
	)['total']

	return _success_response(data={
		'wallet': {
			'available_balance_kes': _decimal_to_number(total_earned),
			'total_earned_kes': _decimal_to_number(total_earned),
		},
		'statistics': {
			'total_uploads': total_uploads,
			'active_images': active_images,
			'processing_images': processing_images,
			'total_downloads': total_downloads,
		},
	}, status=200)


@csrf_exempt
@extend_schema(
	tags=['Photos'],
	parameters=AuthHeader,
	request=UploadIntentRequestSerializer,
	responses={200: UploadIntentResponseSerializer},
	summary='Create an upload intent',
)
@api_view(['POST'])
def upload_intent_view(request):
	user, error = _require_contributor(request)
	if error:
		return error

	try:
		payload = _json_body(request)
		title = (payload.get('title') or '').strip()
		filename = (payload.get('filename') or '').strip()
		file_type = (payload.get('file_type') or '').strip()
		file_size = _parse_optional_int(payload.get('file_size'))
		if not title:
			raise ValidationError('title is required.')
		if not filename:
			raise ValidationError('filename is required.')
		if not file_type:
			raise ValidationError('file_type is required.')
		if file_size is None or file_size <= 0:
			raise ValidationError('file_size is required.')
		if file_size > MAX_RAW_UPLOAD_BYTES:
			raise ValidationError('file_size must be 30MB or smaller.')

		photo_id = uuid.uuid4()
		raw_key = _build_raw_key(photo_id, filename)
		with transaction.atomic():
			Photo.objects.create(
				photo_id=photo_id,
				contributor=user,
				title=title,
				description='',
				county='',
				county_code=None,
				license_type=Photo.LicenseType.FREE_ATTRIBUTION,
				price_kes=Decimal('0.00'),
				watermarked_preview_url=None,
				secure_raw_s3_key=raw_key,
				tags=[],
				sheng_tags=[],
				formal_tags=[],
				status=Photo.Status.PENDING,
				is_active=False,
			)

		presigned = create_raw_upload_post(raw_key, file_type)
		return _success_response(data={
			'photo_id': str(photo_id),
			'upload_url': presigned['url'],
			'fields': presigned['fields'],
		}, status=200)
	except ValidationError as exc:
		return _validation_error_response(exc)
	except (json.JSONDecodeError, TypeError, ValueError):
		return JsonResponse({'detail': 'Invalid JSON body.'}, status=400)


@csrf_exempt
@extend_schema(
	tags=['Photos'],
	parameters=AuthHeader,
	request=FinalizePhotoRequestSerializer,
	responses={202: FinalizePhotoResponseSerializer},
	summary='Finalize a photo upload',
)
@api_view(['POST'])
def finalize_photo_view(request, photo_id):
	user, error = _require_contributor(request)
	if error:
		return error

	photo = get_object_or_404(Photo, photo_id=photo_id, contributor=user)
	try:
		payload = _json_body(request)
		sheng_tags = _parse_list_field(payload.get('sheng_tags'))
		formal_tags = _parse_list_field(payload.get('formal_tags'))
		county_code = _parse_optional_int(payload.get('county_code'))
		license_type = _normalized_license_type(payload.get('license_type'))
		price_kes = _parse_decimal(payload.get('price_kes'))
		description = (payload.get('description') or '').strip()

		if sheng_tags is None:
			raise ValidationError('sheng_tags must be an array.')
		if formal_tags is None:
			raise ValidationError('formal_tags must be an array.')
		if county_code is None:
			raise ValidationError('county_code is required.')
		if license_type is None:
			raise ValidationError('license_type must be Free_Attribution or Commercial_Paid.')
		if price_kes is None:
			raise ValidationError('price_kes is required.')

		photo.description = description
		photo.sheng_tags = sheng_tags
		photo.formal_tags = formal_tags
		photo.county_code = county_code
		photo.license_type = license_type
		photo.price_kes = price_kes
		photo.tags = list(dict.fromkeys(sheng_tags + formal_tags))
		photo.status = Photo.Status.PROCESSING
		photo.is_active = False
		photo.save()
		_queue_photo_processing(photo.photo_id)

		return JsonResponse({
			'status': 'success',
			'message': 'Image queued for watermarking and processing optimization.',
			'photo_id': str(photo.photo_id),
			'current_state': 'processing',
		}, status=202)
	except ValidationError as exc:
		return _validation_error_response(exc)
	except (json.JSONDecodeError, TypeError, ValueError):
		return JsonResponse({'detail': 'Invalid JSON body.'}, status=400)


@extend_schema(
	tags=['Licensing'],
	parameters=AuthHeader,
	responses={200: DownloadTokenResponseSerializer},
	summary='Create a secure download token',
)
@api_view(['GET'])
def download_token_view(request, photo_id):
	user, error = _extract_bearer_user(request)
	if error:
		return error

	photo = get_object_or_404(Photo.objects.select_related('contributor'), photo_id=photo_id, status=Photo.Status.ACTIVE, is_active=True)
	license_record = License.objects.filter(photo=photo, buyer=user).first()
	if photo.license_type == Photo.LicenseType.COMMERCIAL_PAID and not license_record and photo.contributor_id != user.id:
		return _error_response('Forbidden.', status=403)

	return _success_response(data={
		'download_url': create_raw_download_url(photo.secure_raw_s3_key),
		'expires_in_seconds': 600,
		'license_pdf_url': license_record.license_pdf_url if license_record else None,
	}, status=200)

