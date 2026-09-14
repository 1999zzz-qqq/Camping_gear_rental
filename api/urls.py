import users.urls
import equipment.urls
import orders.urls
import common.urls
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
# 路由分发
# 路由分发到不同的应用
# 每个应用都有自己的路由配置
import comments.urls
urlpatterns = [
    # JWT Token 接口
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # 业务接口
    path('users/', include(users.urls)),
    path('equipment/', include(equipment.urls)),
    path('orders/', include(orders.urls)),
    path('common/', include(common.urls)),  
    path('comments/',  include(comments.urls)),

]