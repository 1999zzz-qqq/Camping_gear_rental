from django.shortcuts import render, get_object_or_404
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets
from rest_framework.decorators import action
from django.utils import timezone
from .models import UserInfo
from .serializers import UserPublicSerializer, UserRegisterSerializer, UserLoginSerializer, ChangePasswordSerializer, \
    AdminUserSerializer
from rest_framework.response import Response
import random
import string
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import base64
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin, CreateModelMixin, \
    DestroyModelMixin


# 管理员查看所有用户
class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = UserInfo.objects.all()
    serializer_class = AdminUserSerializer
    # 只有管理员+已登录才能查看所有用户
    permission_classes = [IsAdminUser, IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def freeze(self, request, pk=None):
        """冻结用户账户"""
        user = get_object_or_404(UserInfo, pk=pk)
        reason = request.data.get('reason', '账户异常')

        user.is_frozen = True
        user.frozen_reason = reason
        user.frozen_time = timezone.now()
        user.save()

        return Response({
            'message': '用户账户已冻结',
            'user_id': user.id,
            'username': user.username,
            'is_frozen': user.is_frozen,
            'frozen_reason': user.frozen_reason,
            'frozen_time': user.frozen_time.strftime('%Y-%m-%d %H:%M:%S') if user.frozen_time else None
        })

    @action(detail=True, methods=['post'])
    def unfreeze(self, request, pk=None):
        """解冻用户账户"""
        user = get_object_or_404(UserInfo, pk=pk)

        user.is_frozen = False
        user.frozen_reason = ''
        user.frozen_time = None
        user.save()

        return Response({
            'message': '用户账户已解冻',
            'user_id': user.id,
            'username': user.username,
            'is_frozen': user.is_frozen
        })


# 用户个人展示视图
class UserViewSet(viewsets.GenericViewSet, RetrieveModelMixin, UpdateModelMixin):
    queryset = UserInfo.objects.all()
    serializer_class = UserPublicSerializer
    # 只能查看自己的信息
    permission_classes = [IsAuthenticated]

    # 重写get_object方法，返回当前登录用户,省去接收pk
    def get_object(self):
        return self.request.user


# 用户注册视图
# 豁免CSRF验证装饰器，用在dispatch方法上，dispatch方法是分发器，用在它身上就可以豁免所有请求的CSRF验证
@method_decorator(csrf_exempt, name='dispatch')
class UserRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # 将数据交给序列化器进行验证
        serializer = UserRegisterSerializer(data=request.data)
        # 验证数据是否有效
        if serializer.is_valid():
            # 保存用户
            serializer.save()
            # 返回成功响应
            return Response({'message': '注册成功'})
        # 返回错误响应
        return Response(serializer.errors, status=400)


from django.contrib.auth import login, logout
from rest_framework_simplejwt.tokens import RefreshToken


@method_decorator(csrf_exempt, name='dispatch')
class UserLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        captcha_key = request.data.get('captcha_key')
        captcha_code = request.data.get('captcha_code')
        # 有没有验证码
        if not captcha_key or not captcha_code:
            return Response({'message': '请输入验证码'}, status=400)
        # 验证码校验
        if not CaptchaView().verify_captcha(captcha_key, captcha_code):
            return Response({'message': '验证码错误'}, status=400)

        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            # 验证密码
            user = authenticate(username=serializer.validated_data['username'],
                                password=serializer.validated_data['password'])
            if user:
                # 判断是否冻结
                if user.is_frozen:
                    return Response({'message': '您的账户已被冻结，请联系管理员'}, status=403)
                # 生成双token
                """
                access_token 短：被盗了很快就失效，安全性高
                refresh_token 长：用户不用频繁重新登录
                """
                refresh = RefreshToken.for_user(user)
                return Response({
                    'message': '登录成功',
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                })
            else:
                return Response({'message': '用户名或密码错误，请重新输入'}, status=400)
        return Response(serializer.errors, status=400)


# 用户修改密码视图
class ChangePwdView(APIView):
    permission_classes = [IsAuthenticated]  # 只有已登录用户才能修改密码

    def post(self, request):
        # 将数据交给序列化器验证
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        # 验证数据是否有效
        if serializer.is_valid():
            # 验证用户
            user = authenticate(username=request.user.username, password=serializer.validated_data['old_password'])
            if user:
                # 更新用户密码
                user.set_password(serializer.validated_data['new_password'])
                user.save()
                # 返回成功响应
                return Response({'message': '密码修改成功'})
            else:
                # 返回错误响应
                return Response({'message': '旧密码错误'}, status=400)
        # 返回错误响应
        return Response(serializer.errors, status=400)


# 用户退出登录视图
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class UserLogoutView(APIView):
    # 只有已登录用户才能退出登录
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 从请求数据中获取refresh_token
            refresh_token = request.data.get("refresh")
            if refresh_token:
                # 从前端发送的 POST 请求体中获取 refresh_token(刷新令牌)
                token = RefreshToken(refresh_token)
                # 刷新令牌加入黑名单
                token.blacklist()
            return Response({'message': '退出登录成功'})
        except (InvalidToken,TypeError):
            # token无效或过期也算退出成功
            return Response({'message': '退出登录成功'})




captcha_storage = {}


@method_decorator(csrf_exempt, name='dispatch')
class CaptchaView(APIView):
    permission_classes = [AllowAny]

    def generate_captcha(self):
        characters = string.ascii_letters + string.digits
        captcha_text = ''.join(random.choices(characters, k=4))

        width, height = 120, 40
        image = Image.new('RGB', (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype('arial.ttf', 28)
        except:
            font = ImageFont.load_default()

        for i, char in enumerate(captcha_text):
            x = 10 + i * 25
            y = random.randint(5, 10)
            draw.text((x, y), char, fill=(random.randint(0, 150), random.randint(0, 150), random.randint(0, 150)),
                      font=font)

        for _ in range(10):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = random.randint(0, width)
            y2 = random.randint(0, height)
            draw.line((x1, y1, x2, y2),
                      fill=(random.randint(150, 200), random.randint(150, 200), random.randint(150, 200)), width=1)

        for _ in range(50):
            x = random.randint(0, width)
            y = random.randint(0, height)
            draw.point((x, y), fill=(random.randint(150, 200), random.randint(150, 200), random.randint(150, 200)))

        buffer = BytesIO()
        image.save(buffer, format='PNG')
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return captcha_text, image_base64

    def get(self, request):
        captcha_text, image_base64 = self.generate_captcha()
        captcha_key = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        captcha_storage[captcha_key] = captcha_text
        return Response({
            'key': captcha_key,
            'image': f'data:image/png;base64,{image_base64}'
        })

    def verify_captcha(self, key, code):
        stored_code = captcha_storage.get(key)
        if stored_code and stored_code.lower() == code.lower():
            del captcha_storage[key]
            return True
        return False
