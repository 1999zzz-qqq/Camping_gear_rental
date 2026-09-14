from django.urls import path
from . import views

urlpatterns = [
    path('upload/image/', views.ImageUploadView.as_view(), name='image-upload'),
]
