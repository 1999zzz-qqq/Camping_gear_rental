import os
import uuid
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser


class ImageUploadView(APIView):
    """通用图片上传接口"""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAdminUser]

    def post(self, request):
        file = request.FILES.get("image")
        if not file:
            return Response(
                {"error": "请上传图片文件"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 限制文件大小 5MB
        if file.size > 5 * 1024 * 1024:
            return Response(
                {"error": "图片大小不能超过 5MB"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 限制格式
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            return Response(
                {"error": "仅支持 JPG、PNG、GIF、WebP 格式"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 生成唯一文件名
        ext = os.path.splitext(file.name)[1]
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(settings.MEDIA_ROOT, filename)

        # 保存文件
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        with open(filepath, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        # 返回访问 URL
        image_url = request.build_absolute_uri(
            f"{settings.MEDIA_URL}{filename}"
        )

        return Response({
            "message": "上传成功",
            "url": image_url,
            "filename": filename
        })
