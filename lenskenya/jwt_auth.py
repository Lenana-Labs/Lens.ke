import datetime as dt
import hashlib
import secrets
import uuid

import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone

from .models import RefreshToken, User

ACCESS_TOKEN_TTL_SECONDS = 30 * 60
REFRESH_TOKEN_TTL_DAYS = 30
JWT_ISSUER = 'lens.ke'
JWT_AUDIENCE = 'lens.ke-web'


def access_token_ttl_seconds() -> int:
	return int(getattr(settings, 'JWT_ACCESS_TOKEN_MINUTES', 30)) * 60


def refresh_token_ttl_days() -> int:
	return int(getattr(settings, 'JWT_REFRESH_TOKEN_DAYS', 30))


def _jwt_secret() -> str:
	return getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY)


def _encode_token(payload: dict) -> str:
	return jwt.encode(payload, _jwt_secret(), algorithm='HS256')


def _now() -> dt.datetime:
	return timezone.now()


def issue_access_token(user: User) -> str:
	now = _now()
	exp = now + dt.timedelta(seconds=access_token_ttl_seconds())
	payload = {
		'type': 'access',
		'sub': str(user.pk),
		'email': user.email,
		'role': user.role,
		'iat': int(now.timestamp()),
		'exp': int(exp.timestamp()),
		'iss': JWT_ISSUER,
		'aud': JWT_AUDIENCE,
		'jti': uuid.uuid4().hex,
	}
	return _encode_token(payload)


def issue_refresh_token(user: User) -> tuple[str, RefreshToken]:
	now = _now()
	raw_token = secrets.token_urlsafe(48)
	refresh_record = RefreshToken.objects.create(
		user=user,
		token_hash=RefreshToken.hash_value(raw_token),
		jti=uuid.uuid4().hex,
		expires_at=now + dt.timedelta(days=refresh_token_ttl_days()),
	)
	return raw_token, refresh_record


def decode_access_token(token: str) -> dict:
	return jwt.decode(
		token,
		_jwt_secret(),
		algorithms=['HS256'],
		audience=JWT_AUDIENCE,
		issuer=JWT_ISSUER,
	)


def authenticate_user(email: str, password: str) -> User:
	user = authenticate(email=email, password=password)
	if not user:
		raise ValidationError('Invalid email or password.')
	return user


def login_response(user: User) -> JsonResponse:
	access_token = issue_access_token(user)
	refresh_token, refresh_record = issue_refresh_token(user)
	return JsonResponse({
		'access_token': access_token,
		'access_token_expires_in': ACCESS_TOKEN_TTL_SECONDS,
		'refresh_token': refresh_token,
		'refresh_token_expires_at': refresh_record.expires_at.isoformat(),
		'user': {
			'id': str(user.pk),
			'email': user.email,
			'role': user.role,
		},
	})


def rotate_refresh_token(raw_token: str) -> tuple[User, str, RefreshToken]:
	token_hash = RefreshToken.hash_value(raw_token)
	refresh_record = RefreshToken.objects.select_related('user').filter(token_hash=token_hash, revoked_at__isnull=True).first()
	if not refresh_record:
		raise ValidationError('Invalid refresh token.')
	if refresh_record.expires_at <= _now():
		refresh_record.revoke()
		raise ValidationError('Refresh token expired.')
	refresh_record.revoke()
	new_refresh_token, new_record = issue_refresh_token(refresh_record.user)
	new_record.last_used_at = _now()
	new_record.save(update_fields=['last_used_at', 'updated_at'])
	return refresh_record.user, new_refresh_token, new_record