from django.test import TestCase

# Create your tests here.
import os
import sys
def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_djangoproject.settings")
    import django
    django.setup()
# 测试用户
# models
from users.models import UserInfo
from django.contrib.auth.models import AbstractUser
from django.db import models
from rest_framework import serializers
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import check_password



class UserInfo(AbstractUser):
    phone = models.CharField(max_length = 11,unique=True)
    # 是否冻结
    is_frozen = models.BooleanField(default=False)
    # 冻结原因
    frozen_reason = models.CharField(max_length = 200,blank=True,null=True)
    # 注册时间
    date_joined = models.DateTimeField(auto_now_add=True)

 # 序列化器
 # 管理员序列化器
class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInfo
        fields = ['id', 'username', 'phone', 'email', 'is_staff', 'is_frozen', 'frozen_reason', 'date_joined']
        read_only_fields = ('id', 'username', 'is_staff')
class UserPublicSerializer(serializers.ModelSerializer):
    # 公共序列化器
    class Meta:
        model = UserInfo
        fields = ('id', 'username', 'phone', 'email', 'is_staff')
        read_only_fields = ('id', 'username', 'is_staff')
# 用户注册序列化器
class UserRegisterSerializer(serializers.ModelSerializer):
    re_password = serializers.CharField(write_only=True)
    class Meta:
        model = UserInfo
        fields = ('username', 'password', 'phone', 'email', 're_password')
        read_only_fields = ('id', 'username', 'is_staff')
        extra_kwargs = {
            'password': {'write_only': True},
            'username': {'min_length': 6, 'max_length': 20},
            'phone': {'min_length': 11, 'max_length': 11},
            'email': {'min_length': 6, 'max_length': 50},

        }
        def validate_password(self, value):
            if len(value) < 6:
                raise serializers.ValidationError("密码长度不能小于6位")
            return value
        def validate_phone(self,value):
           if not value.isdigit():
               raise serializers.ValidationError("手机号只能包含数字")
           return value
        def validate_email(self,value):
            try:
                validate_email(value)
            except ValidationError:
                raise serializers.ValidationError('邮箱格式错误,请输入正确的邮箱格式')
            return value
        def validate(self, attrs):
            if attrs['password'] != attrs['re_password']:
                raise serializers.ValidationError({'re_password': '两次密码不一致'})
            return attrs
        def create(self,validated_data):
            # 删除非模型字段
            validated_data.pop('re_password')
            # 加密密码
            user = UserInfo.objects.create_user(**validated_data)
            return user
# 用户登录序列化器
class UserLoginSerializer(serializers.Serializer):
    # 用户登录序列化器
    username = serializers.CharField(min_length=6,max_length=20,required=True)
    password = serializers.CharField(min_length=6,max_length=20,required=True)
    def validate(self, attrs):
        user = UserInfo.objects.filter(username=attrs['username']).first()
        if not user:
            raise serializers.ValidationError({'username': '用户名不存在'})
        if not check_password(attrs['password'], user.password):
            raise serializers.ValidationError({'password': '密码错误'})
        return attrs
# 用户修改密码序列化器
class UserChangePasswordSerializer(serializers.Serializer):
    # 用户修改密码序列化器
    old_password = serializers.CharField(min_length=6,max_length=20,required=True)
    new_password = serializers.CharField(min_length=6,max_length=20,required=True)
    re_password = serializers.CharField(write_only=True,required=True)
    def validate(self, attrs):
        if attrs['new_password'] != attrs['re_password']:
            raise serializers.ValidationError({'re_password': '两次密码不一致'})
        return attrs
    def validate(self, attrs):
        if attrs['new_password'] != attrs['re_password']:
            raise serializers.ValidationError({'re_password': '两次密码不一致'})
        return attrs
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not check_password(value, user.password):
            raise serializers.ValidationError("旧密码错误")
        return value
    def update(self, instance, validated_data):
        instance.set_password(validated_data['new_password'])
        instance.save()
        return instance
        
        
        

