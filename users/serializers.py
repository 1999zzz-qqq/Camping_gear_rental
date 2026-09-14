# @version  : 1.0
# @Author   :swj
# @File     :serializers.py.py

from rest_framework import serializers
from .models import UserInfo
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import check_password


# 管理员序列化器
class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInfo
        fields = ['id', 'username', 'phone', 'email', 'is_staff', 'is_frozen', 'frozen_reason', 'date_joined']
        read_only_fields = ('id', 'username', 'is_staff')
# 展示+修改资料
class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInfo
        fields = ('id', 'username', 'phone', 'email', 'is_staff')
        read_only_fields = ('id', 'username', 'is_staff')


# 用户注册序列化器
class UserRegisterSerializer(serializers.ModelSerializer):
    re_password = serializers.CharField(write_only=True)

    class Meta:
        model = UserInfo
        fields = ['username', 'password', 'phone', 'email', 're_password']
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 6},
            "phone":{"min_length":11,"max_length":11},
            "username":{"min_length":3,"max_length":12}
        }   

    def validate(self, attrs):
        if attrs['password'] != attrs['re_password']:
            raise serializers.ValidationError({'re_password': '两次密码不一致'})
        return attrs
    def validate_username(self, value):
        if not value.isalnum():
            raise serializers.ValidationError('用户名只能包含字母和数字')
        return value
    def validate_phone(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('手机号只能包含数字')
        return value
    def validate_email(self, value):
        try:
            validate_email(value)
        except ValidationError:
            raise serializers.ValidationError('邮箱格式错误,请输入正确的邮箱格式')
        return value
    
    def create(self, validated_data):
        # 删除非模型字段
        validated_data.pop('re_password')
        # 加密密码
        user = UserInfo.objects.create_user(**validated_data)
        return user


# 用户登陆序列化器
class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    # style={'input_type': 'password'} 会将密码输入框设置为密码输入框
    password = serializers.CharField(required=True, style={'input_type': 'password'})


# 修改密码序列化器
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        # label 会显示在前端,显示在输入框的外面
        label='原密码'
    )
    new_password = serializers.CharField(
        min_length=6,
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        label='新密码')
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        label="确认新密码"
    )

    # 校验原密码是否正确
    def validate_old_password(self, value):
        # value 就是前端传的 old_password
        # 拿到当前登陆用户
        user = self.context['request'].user
        # 校验密码是否一致
        if not check_password(value, user.password):
            raise serializers.ValidationError("原密码输入错误")
        return value

    # 校验新密码和确认密码
    # attrs是通过检验的字段
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "两次输入的新密码不一致"})
        return attrs
    # 保存新密码
    def save(self, **kwargs):
        # 拿到当前登陆的用户
        user = self.context['request'].user
        # set_password会将明文转为密文
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user