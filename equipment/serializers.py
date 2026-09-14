from rest_framework import serializers
from .models import Equipment, Category


class CategoryListSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'sort', 'children']
        read_only_fields = ['id', 'name', 'sort', 'children']

    def get_children(self, obj):
        children = obj.children.filter(is_show=True).order_by('sort')
        return CategoryListSerializer(children, many=True, context=self.context).data


class CategoryAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ['id', 'created_time']


class EquipmentListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    # 装备图片URL
    cover_img_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Equipment
        fields = [
            'id', 'name', 'price', 'daily_rental', 'deposit',
            'stock', 'is_sold_out', 'category', 'category_name',
            'cover_img_url', 'desc'
        ]
        read_only_fields = fields

    def get_cover_img_url(self, obj):
        # 装备图片URL
        # 如果没有图片，返回空字符串
        if not obj.cover_img:
            return ''
        request = self.context.get('request')
        # 构建绝对URL
        return request.build_absolute_uri(obj.cover_img.url) if request else obj.cover_img.url


class EquipmentDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    cover_img_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Equipment
        fields = [
            'id', 'name', 'price', 'daily_rental', 'deposit',
            'stock', 'is_sold_out', 'is_shelf', 'is_show',
            'category', 'category_name', 'cover_img_url', 'desc',
            'created_time'
        ]
        read_only_fields = ['id', 'created_time']

    def get_cover_img_url(self, obj):
        if not obj.cover_img:
            return ''
        request = self.context.get('request')
        return request.build_absolute_uri(obj.cover_img.url) if request else obj.cover_img.url


import requests
from decimal import Decimal
from django.core.files.base import ContentFile


class EquipmentAdminSerializer(serializers.ModelSerializer):
    cover_img_url = serializers.SerializerMethodField(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default='')
    cover_img_url_input = serializers.URLField(write_only=True, required=False)

    class Meta:
        model = Equipment
        fields = [
            'id', 'name', 'price', 'daily_rental', 'deposit',
            'stock', 'category', 'category_name',
            'cover_img', 'cover_img_url', 'cover_img_url_input', 'desc',
            'is_shelf', 'is_show', 'is_sold_out',
            'created_time'
        ]
        read_only_fields = ['id', 'created_time', 'cover_img_url', 'category_name','daily_rental','deposit']

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("单价必须大于0！")
        if value > Decimal('99999.99'):
            raise serializers.ValidationError("单价过大，请检查输入")
        return value



    def validate(self, attrs):
        instance = self.instance
        stock = attrs.get('stock', instance.stock if instance else 0)
        is_shelf = attrs.get('is_shelf', instance.is_shelf if instance else True)
        
        if is_shelf and stock <= 0:
            raise serializers.ValidationError("库存不足，无法上架！请先添加库存。")
        
        return attrs

    def _download_image_from_url(self, url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise serializers.ValidationError("URL不是有效的图片链接")
            filename = url.split('/')[-1]
            return ContentFile(response.content, name=filename)
        except Exception as e:
            raise serializers.ValidationError(f"下载图片失败: {str(e)}")

    def create(self, validated_data):
        cover_img_url_input = validated_data.pop('cover_img_url_input', None)
        if cover_img_url_input:
            validated_data['cover_img'] = self._download_image_from_url(cover_img_url_input)
        
        instance = super().create(validated_data)
        if instance.stock <= 0:
            instance.is_shelf = False
            instance.save()
        return instance

    def update(self, instance, validated_data):
        cover_img_url_input = validated_data.pop('cover_img_url_input', None)
        if cover_img_url_input:
            validated_data['cover_img'] = self._download_image_from_url(cover_img_url_input)
        
        stock = validated_data.get('stock', instance.stock)
        is_shelf = validated_data.get('is_shelf', instance.is_shelf)
        
        if is_shelf and stock <= 0:
            validated_data['is_shelf'] = False
        
        instance = super().update(instance, validated_data)
        
        if stock <= 0 and instance.is_shelf:
            instance.is_shelf = False
            instance.save()
        
        return instance

    def get_cover_img_url(self, obj):

        if not obj.cover_img:
            return ''
        
        request = self.context.get('request')
        return request.build_absolute_uri(obj.cover_img.url) if request else obj.cover_img.url
