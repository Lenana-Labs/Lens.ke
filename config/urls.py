from django.contrib import admin
from django.urls import path

from lenskenya import views as lens_views

# Swagger / OpenAPI
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    # -------------------
    # Admin
    # -------------------
    path("admin/", admin.site.urls),

    # -------------------
    # OpenAPI / Swagger
    # -------------------
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),

    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),

    # -------------------
    # Photos
    # -------------------
    path("api/v1/photos", lens_views.photo_list_view, name="photo-list"),
    path("api/v1/photos/<uuid:photo_id>", lens_views.photo_detail_view, name="photo-detail"),

    path("api/v1/photos/upload-intent", lens_views.upload_intent_view, name="photo-upload-intent"),
    path("api/v1/photos/<uuid:photo_id>/finalize", lens_views.finalize_photo_view, name="photo-finalize"),

    # -------------------
    # Auth (cleaned: only one namespace)
    # -------------------
    path("api/v1/auth/register", lens_views.auth_register_view, name="auth-register"),
    path("api/v1/auth/login", lens_views.auth_login_view, name="auth-login"),

    path("api/v1/auth/login/custom", lens_views.login_view, name="auth-login-custom"),
    path("api/v1/auth/refresh", lens_views.refresh_view, name="auth-refresh"),
    path("api/v1/auth/logout", lens_views.logout_view, name="auth-logout"),
    path("api/v1/auth/me", lens_views.me_view, name="auth-me"),

    # -------------------
    # Users
    # -------------------
    path("api/v1/users/profile", lens_views.profile_view, name="user-profile"),

    # -------------------
    # Contributor
    # -------------------
    path("api/v1/contributor/dashboard", lens_views.contributor_dashboard_view, name="contributor-dashboard"),

    # -------------------
    # Licensing / Downloads
    # -------------------
    path(
        "api/v1/licenses/download-token/<uuid:photo_id>",
        lens_views.download_token_view,
        name="license-download-token",
    ),
]