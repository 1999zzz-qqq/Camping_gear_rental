from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# 分类接口
router.register(r'category', views.CategoryViewSet)
# 装备接口
router.register(r'equipment', views.EquipmentViewSet)
router.register(r'equipment-detail', views.EquipmentDetailViewSet, basename='equipment-detail')


# 管理员接口
router.register(r'category-admin', views.CategoryAdminViewSet, basename='category-admin')
router.register(r'equipment-admin', views.EquipmentAdminViewSet, basename='equipment-admin')

urlpatterns = [
    path('', include(router.urls)),
]
