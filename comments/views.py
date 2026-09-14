from django.shortcuts import render
from rest_framework.response import Response

# Create your views here.
# 评论视图
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from .models import Comment
from .serializers import CommentCreateSerializer, CommentSerializer, CommentUpdateSerializer
from .services import CommentService
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import AllowAny
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
class CommentPagination(PageNumberPagination):
    page_size = 10
    max_page_size = 50
    page_size_query_param = 'page_size'
    page_query_param = 'page'
# 自定义权限类
class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.user == request.user
class CommentViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'post','delete','put','patch',]
    pagination_class = CommentPagination
    # 动态查询集判断
    def get_queryset(self):
        queryset = Comment.objects.select_related('user', 'equipment').order_by('-create_time')
        equipment_id = self.request.query_params.get('equipment_id')
        if equipment_id:
            queryset = queryset.filter(equipment_id=equipment_id)
        return queryset
    # 动态序列化器判断
    def get_serializer_class(self):
        if self.action == 'create':
            return CommentCreateSerializer
        if self.action in ['update','partial_update']:
            return CommentUpdateSerializer
        return CommentSerializer
        
        
    # 动态权限判断
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        if self.action == 'create':
            return [IsAuthenticated()]
        return (IsOwnerOrAdmin(),IsAuthenticated())
    def perform_create(self, serializer):
        try:
            comment = CommentService.create_comment(
                user=self.request.user,
                validated_data=serializer.validated_data
            )
            serializer.instance = comment  
        except ValueError as e:
            raise ValidationError(str(e))
            

