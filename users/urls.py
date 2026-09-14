from django.urls import path, re_path
from . import views

urlpatterns = [
    path('profile/', views.UserViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update'})),
    path('register/', views.UserRegisterView.as_view()),
    path('login/', views.UserLoginView.as_view()),
    path('change-password/', views.ChangePwdView.as_view()),
    path('admin/', views.UserAdminViewSet.as_view({'get': 'list'})),
    path('admin/<int:pk>/', views.UserAdminViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update'})),
    path('admin/<int:pk>/freeze/', views.UserAdminViewSet.as_view({'post': 'freeze'})),
    path('admin/<int:pk>/unfreeze/', views.UserAdminViewSet.as_view({'post': 'unfreeze'})),
    path('logout/', views.UserLogoutView.as_view()),
    path('captcha/', views.CaptchaView.as_view()),
]
