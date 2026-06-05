import io
import uuid

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from .models import Photo
from .storage import private_raw_bucket_name, public_preview_bucket_name, public_preview_url, s3_client


TARGET_WEBP_BYTES = 150 * 1024
MAX_PREVIEW_WIDTH = 1800
MAX_PREVIEW_HEIGHT = 1800


def _fit_preview(image):
	image = image.convert('RGB')
	image.thumbnail((MAX_PREVIEW_WIDTH, MAX_PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
	return image


def _stamp_watermark(image):
	overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
	draw = ImageDraw.Draw(overlay)
	font_size = max(26, min(image.size) // 12)
	try:
		font = ImageFont.truetype('arial.ttf', font_size)
	except OSError:
		font = ImageFont.load_default()

	mark = getattr(settings, 'LENSKE_WATERMARK_TEXT', 'LENS.KE')
	text_box = draw.textbbox((0, 0), mark, font=font)
	text_width = text_box[2] - text_box[0]
	text_height = text_box[3] - text_box[1]
	step_x = max(text_width + 140, image.width // 3)
	step_y = max(text_height + 100, image.height // 4)

	for y in range(-step_y, image.height + step_y, step_y):
		for x in range(-step_x, image.width + step_x, step_x):
			draw.line((x - 24, y + text_height + 24, x + text_width + 24, y - 24), fill=(255, 255, 255, 44), width=3)
			draw.text((x, y), mark, fill=(255, 255, 255, 72), font=font)

	return Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')


def _encode_webp_under_target(image):
	working = image
	for scale in (1.0, 0.85, 0.7, 0.55):
		if scale != 1.0:
			size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
			working = image.resize(size, Image.Resampling.LANCZOS)
		for quality in range(82, 34, -8):
			buffer = io.BytesIO()
			working.save(buffer, format='WEBP', quality=quality, method=6, optimize=True)
			if buffer.tell() <= TARGET_WEBP_BYTES or quality <= 42:
				buffer.seek(0)
				return buffer
	buffer.seek(0)
	return buffer


@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def process_photo_asset(self, photo_id):
	photo = Photo.objects.get(photo_id=photo_id)
	raw_object = io.BytesIO()
	client = s3_client()
	client.download_fileobj(private_raw_bucket_name(), photo.secure_raw_s3_key, raw_object)
	raw_object.seek(0)

	try:
		with Image.open(raw_object) as image:
			preview = _stamp_watermark(_fit_preview(image))
			webp_object = _encode_webp_under_target(preview)
	except UnidentifiedImageError as exc:
		raise ValueError(f'Unsupported image format for photo {photo_id}.') from exc

	now = timezone.now()
	preview_key = f"previews/{now.year:04d}/{now.month:02d}/{photo.photo_id}-{uuid.uuid4().hex[:8]}.webp"
	client.upload_fileobj(
		webp_object,
		public_preview_bucket_name(),
		preview_key,
		ExtraArgs={'ContentType': 'image/webp', 'ACL': 'public-read'},
	)

	photo.watermarked_preview_url = public_preview_url(preview_key)
	photo.status = Photo.Status.ACTIVE
	photo.is_active = True
	photo.save(update_fields=['watermarked_preview_url', 'status', 'is_active', 'updated_at'])
	return {'photo_id': str(photo.photo_id), 'preview_key': preview_key}
