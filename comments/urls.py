from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.register(r'', views.CommentViewSet, basename='comment')

urlpatterns = router.urls   