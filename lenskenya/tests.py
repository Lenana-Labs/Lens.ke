from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .jwt_auth import issue_access_token
from .models import License, Photo, Transaction


class ApiContractTests(TestCase):
	def setUp(self):
		self.user_model = get_user_model()
		self.buyer = self.user_model.objects.create_user(
			email='buyer@example.com',
			password='password123',
			name='Buyer One',
			role='buyer',
		)
		self.contributor = self.user_model.objects.create_user(
			email='photographer@example.com',
			password='password123',
			name='Photographer One',
			role='contributor',
		)

	def _auth_header(self, user):
		return {'HTTP_AUTHORIZATION': f'Bearer {issue_access_token(user)}'}

	def _create_photo(self, **kwargs):
		photo_id = kwargs.pop('photo_id', None)
		created_at = kwargs.pop('created_at', None)
		photo_kwargs = {
			'contributor': kwargs.pop('contributor', self.contributor),
			'title': kwargs.pop('title', 'Test photo'),
			'description': kwargs.pop('description', 'Test description'),
			'county': kwargs.pop('county', 'Nairobi'),
			'county_code': kwargs.pop('county_code', 47),
			'license_type': kwargs.pop('license_type', Photo.LicenseType.FREE_ATTRIBUTION),
			'price_kes': kwargs.pop('price_kes', Decimal('0.00')),
			'watermarked_preview_url': kwargs.pop('watermarked_preview_url', 'https://example.com/preview.jpg'),
			'secure_raw_s3_key': kwargs.pop('secure_raw_s3_key', 'private/raw/key.jpg'),
			'tags': kwargs.pop('tags', ['nature']),
			'sheng_tags': kwargs.pop('sheng_tags', []),
			'formal_tags': kwargs.pop('formal_tags', []),
			'views': kwargs.pop('views', 0),
			'downloads': kwargs.pop('downloads', 0),
			'likes': kwargs.pop('likes', 0),
			'status': kwargs.pop('status', Photo.Status.ACTIVE),
			'is_active': kwargs.pop('is_active', True),
		}
		if photo_id is not None:
			photo_kwargs['photo_id'] = photo_id
		photo = Photo.objects.create(**photo_kwargs)
		if created_at is not None:
			Photo.objects.filter(pk=photo.pk).update(created_at=created_at)
			photo.refresh_from_db()
		return photo

	def test_register_login_and_profile_contract(self):
		register_response = self.client.post('/api/v1/auth/register', data={
			'name': 'James Njange',
			'email': 'james@lens.ke',
			'password': 'SecurePassword123!',
			'role': 'contributor',
		}, content_type='application/json')

		self.assertEqual(register_response.status_code, 201)
		register_payload = register_response.json()
		self.assertEqual(register_payload['status'], 'success')
		self.assertEqual(register_payload['data']['email'], 'james@lens.ke')
		self.assertEqual(register_payload['data']['role'], 'contributor')

		login_response = self.client.post('/api/v1/auth/login', data={
			'email': 'james@lens.ke',
			'password': 'SecurePassword123!',
		}, content_type='application/json')

		self.assertEqual(login_response.status_code, 200)
		login_payload = login_response.json()
		self.assertEqual(login_payload['status'], 'success')
		self.assertIn('token', login_payload)
		self.assertEqual(login_payload['user']['name'], 'James Njange')

		profile_response = self.client.get('/api/v1/users/profile', **self._auth_header(self.user_model.objects.get(email='james@lens.ke')))
		self.assertEqual(profile_response.status_code, 200)
		profile_payload = profile_response.json()
		self.assertEqual(profile_payload['status'], 'success')
		self.assertEqual(profile_payload['data']['email'], 'james@lens.ke')
		self.assertEqual(profile_payload['data']['name'], 'James Njange')

	def test_photo_list_supports_pagination_sort_and_filters(self):
		now = timezone.now()
		older = self._create_photo(
			title='Older',
			tags=['matatu', 'urban'],
			sheng_tags=['matatu'],
			formal_tags=['transport'],
			county_code=47,
			license_type=Photo.LicenseType.COMMERCIAL_PAID,
			price_kes=Decimal('1500.00'),
			views=10,
			downloads=3,
			likes=2,
			created_at=now - timedelta(days=2),
		)
		newer = self._create_photo(
			title='Newer',
			tags=['matatu', 'city'],
			sheng_tags=['matatu'],
			formal_tags=['cityscape'],
			county_code=47,
			license_type=Photo.LicenseType.COMMERCIAL_PAID,
			price_kes=Decimal('1200.00'),
			views=20,
			downloads=10,
			likes=5,
			created_at=now,
		)
		self._create_photo(
			title='Other county',
			tags=['matatu'],
			sheng_tags=['matatu'],
			formal_tags=['cityscape'],
			county_code=24,
			license_type=Photo.LicenseType.FREE_ATTRIBUTION,
			price_kes=Decimal('0.00'),
			views=100,
			downloads=40,
			likes=12,
			created_at=now - timedelta(days=1),
		)

		response = self.client.get('/api/v1/photos', {
			'page': 0,
			'limit': 200,
			'sort': 'popular',
			'search': 'matatu',
			'county_code': '47',
			'license_type': 'Commercial_Paid',
		})

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload['status'], 'success')
		self.assertEqual(payload['pagination']['current_page'], 1)
		self.assertEqual(payload['pagination']['total_items'], 2)
		self.assertEqual(payload['data'][0]['photo_id'], str(newer.photo_id))
		self.assertEqual(payload['data'][1]['photo_id'], str(older.photo_id))
		self.assertEqual(payload['data'][0]['county_code'], 47)
		self.assertEqual(payload['data'][0]['license_type'], 'Commercial_Paid')

	def test_photo_detail_returns_public_metadata(self):
		photo = self._create_photo(
			title='Nairobi Expressway Dusk',
			description='Long exposure shot from the overpass near Westlands.',
			tags=['Kanairo', 'Chonjo'],
			sheng_tags=['Kanairo', 'Chonjo'],
			formal_tags=['Highway', 'Cityscape', 'Night'],
			county_code=47,
			license_type=Photo.LicenseType.COMMERCIAL_PAID,
			price_kes=Decimal('1500.00'),
		)

		response = self.client.get(f'/api/v1/photos/{photo.photo_id}')
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload['status'], 'success')
		self.assertEqual(payload['data']['photo_id'], str(photo.photo_id))
		self.assertEqual(payload['data']['contributor']['name'], 'Photographer One')
		self.assertEqual(payload['data']['price_kes'], 1500.0)
		self.assertEqual(payload['data']['county_code'], 47)

	def test_upload_intent_finalize_and_dashboard_contracts(self):
		upload_response = self.client.post('/api/v1/photos/upload-intent', data={
			'title': 'Smokie Pasua Vendor',
			'filename': 'smokie_vendor.raw',
			'file_type': 'image/x-adobe-dng',
			'file_size': 31457280,
		}, content_type='application/json', **self._auth_header(self.contributor))

		self.assertEqual(upload_response.status_code, 200)
		upload_payload = upload_response.json()
		photo_id = upload_payload['data']['photo_id']
		self.assertIn('upload_url', upload_payload['data'])
		self.assertIn('policy', upload_payload['data']['fields'])

		finalize_response = self.client.post(f'/api/v1/photos/{photo_id}/finalize', data={
			'description': 'Street food vendor cutting smokies in Nairobi CBD.',
			'sheng_tags': ['SmokiePasua', 'Kanairo'],
			'formal_tags': ['StreetFood', 'Nairobi', 'Hustle'],
			'county_code': 47,
			'license_type': 'Commercial_Paid',
			'price_kes': 1200.00,
		}, content_type='application/json', **self._auth_header(self.contributor))

		self.assertEqual(finalize_response.status_code, 202)
		self.assertEqual(finalize_response.json()['current_state'], 'processing')
		photo = Photo.objects.get(photo_id=photo_id)
		self.assertEqual(photo.status, Photo.Status.PROCESSING)
		self.assertEqual(photo.county_code, 47)
		self.assertEqual(photo.license_type, Photo.LicenseType.COMMERCIAL_PAID)

		completed_photo = self._create_photo(
			title='Active asset',
			status=Photo.Status.ACTIVE,
			is_active=True,
			views=10,
			downloads=4,
			likes=2,
		)
		self._create_photo(
			title='Processing asset',
			status=Photo.Status.PROCESSING,
			is_active=False,
		)
		Transaction.objects.create(
			buyer=self.buyer,
			photo=completed_photo,
			mpesa_receipt_no='MPESA-001',
			amount_paid=Decimal('1000.00'),
			contributor_cut=Decimal('700.00'),
			platform_cut=Decimal('300.00'),
			status=Transaction.Status.COMPLETED,
		)

		dashboard_response = self.client.get('/api/v1/contributor/dashboard', **self._auth_header(self.contributor))
		self.assertEqual(dashboard_response.status_code, 200)
		dashboard_payload = dashboard_response.json()
		self.assertEqual(dashboard_payload['status'], 'success')
		self.assertEqual(dashboard_payload['data']['statistics']['total_uploads'], 3)
		self.assertEqual(dashboard_payload['data']['statistics']['processing_images'], 2)
		self.assertEqual(dashboard_payload['data']['wallet']['available_balance_kes'], 700.0)

	def test_download_token_enforces_authorization(self):
		free_photo = self._create_photo(
			title='Free asset',
			license_type=Photo.LicenseType.FREE_ATTRIBUTION,
			price_kes=Decimal('0.00'),
			secure_raw_s3_key='raw/2026/06/free.raw',
		)
		paid_photo = self._create_photo(
			title='Paid asset',
			license_type=Photo.LicenseType.COMMERCIAL_PAID,
			price_kes=Decimal('1500.00'),
			secure_raw_s3_key='raw/2026/06/paid.raw',
		)
		License.objects.create(
			transaction=Transaction.objects.create(
				buyer=self.buyer,
				photo=paid_photo,
				mpesa_receipt_no='MPESA-002',
				amount_paid=Decimal('1500.00'),
				contributor_cut=Decimal('1000.00'),
				platform_cut=Decimal('500.00'),
				status=Transaction.Status.COMPLETED,
			),
			photo=paid_photo,
			buyer=self.buyer,
			license_pdf_url='https://cdn.lens.ke/licenses/pdf/LIC-TEST.pdf',
		)

		free_response = self.client.get(f'/api/v1/licenses/download-token/{free_photo.photo_id}', **self._auth_header(self.buyer))
		self.assertEqual(free_response.status_code, 200)
		self.assertEqual(free_response.json()['status'], 'success')
		self.assertIn('AWSAccessKeyId', free_response.json()['data']['download_url'])

		paid_response = self.client.get(f'/api/v1/licenses/download-token/{paid_photo.photo_id}', **self._auth_header(self.buyer))
		self.assertEqual(paid_response.status_code, 200)
		self.assertEqual(paid_response.json()['data']['license_pdf_url'], 'https://cdn.lens.ke/licenses/pdf/LIC-TEST.pdf')
