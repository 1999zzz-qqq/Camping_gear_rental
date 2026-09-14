
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'admin', views.OrderAdminViewSet, basename='order-admin')
router.register(r'', views.OrderViewSet, basename='order')

urlpatterns = [
    path('cart/', views.CartViewSet.as_view({
        'get': 'list',
        'post': 'add',
        'put': 'update_item',
    })),
    path('cart/remove/<int:item_id>/', views.CartViewSet.as_view({
        'delete': 'remove_item',
    })),
    path('cart/clear/', views.CartViewSet.as_view({'post': 'clear'})),
    path('', include(router.urls)),
]
