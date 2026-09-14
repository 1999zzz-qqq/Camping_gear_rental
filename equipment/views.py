from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated, AllowAny
from .models import Equipment, Category
from .serializers import CategoryListSerializer, CategoryAdminSerializer, EquipmentListSerializer, EquipmentDetailSerializer, EquipmentAdminSerializer

# Create your views here.
# 分类展示视图
from decimal import Decimal
DEILY_RENTAL_RATE = Decimal('0.10') # 日租金比例:10%
DEPOSIT_RATE = Decimal('0.10') # 押金比例:10%
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(is_show=True, parent__isnull=True).order_by('sort')
    serializer_class = CategoryListSerializer
    pagination_class = None 

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAdminUser()]
# 管理员修改分类
class CategoryAdminViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategoryAdminSerializer
    permission_classes = [IsAdminUser] # 只有管理员才能修改分类·
# 装备展示视图
class EquipmentViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.filter(is_shelf=True, is_show=True).order_by('-created_time')
    serializer_class = EquipmentListSerializer
    pagination_class = None 

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAdminUser()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        category_id = request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        keyword = request.query_params.get('keyword')
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

# 装备详情视图
class EquipmentDetailViewSet(viewsets.ModelViewSet):
    queryset = Equipment.objects.filter(is_shelf=True, is_show=True).order_by('-created_time')
    serializer_class = EquipmentDetailSerializer
    pagination_class = None 

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAdminUser()]
 
# 管理员修改装备
class EquipmentAdminViewSet(viewsets.ModelViewSet):
    serializer_class = EquipmentAdminSerializer
    permission_classes = [IsAdminUser]
    def get_queryset(self):
        queryset = Equipment.objects.all()
        keyword = self.request.query_params.get('keyword')
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)
        return queryset.order_by('-created_time')
    def perform_create(self, serializer):
        '''创建时，自动计算日租金和押金'''
        price = serializer.validated_data['price']
        daily_rental = price * DEILY_RENTAL_RATE.quantize(Decimal('0.01'))
        deposit = price * DEPOSIT_RATE.quantize(Decimal('0.01'))
        serializer.save(daily_rental=daily_rental, deposit=deposit)
    def perform_update(self, serializer):
        '''更新时，自动计算日租金和押金'''
        price = serializer.validated_data['price'] or serializer.instance.price
        daily_rental = price * DEILY_RENTAL_RATE.quantize(Decimal('0.01'))
        deposit = price * DEPOSIT_RATE.quantize(Decimal('0.01'))
        serializer.save(daily_rental=daily_rental, deposit=deposit)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)