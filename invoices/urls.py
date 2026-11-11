from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("documents/<uuid:pk>/", views.review, name="review"),
    path("documents/<uuid:pk>/file", views.document_file, name="document_file"),
    path("samples/<slug:key>.png", views.sample_image, name="sample_image"),
    path("api/documents", views.upload, name="upload"),
    path("api/samples/<slug:key>", views.use_sample, name="use_sample"),
    path("api/documents/<uuid:pk>/save", views.save, name="save"),
    path("api/documents/<uuid:pk>/approve", views.approve, name="approve"),
    path("api/documents/<uuid:pk>/reopen", views.reopen, name="reopen"),
    path("api/documents/<uuid:pk>/manual", views.manual, name="manual"),
    path("api/documents/<uuid:pk>/delete", views.remove, name="remove"),
    path("export.<str:fmt>", views.export, name="export"),
    path("healthz", views.healthz, name="healthz"),
]
