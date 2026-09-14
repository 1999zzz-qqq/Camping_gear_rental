from rest_framework import serializers
from .models import Comment
from equipment.models import Equipment
from django.core.exceptions import ValidationError
from orders.models import OrderItem
class CommentService:
    @staticmethod
    def create_comment(user, validated_data):
        """
        创建评论
        """
        equipment = validated_data['equipment']
        has_rented = OrderItem.objects.filter(
            equipment=equipment,
            order__user=user,
            order__order_status=5
        ).exists()
        if not has_rented:
            raise ValueError("只有租赁并归还过该装备才能评价")

        # 业务校验2：一人一装备只能评一次
        if Comment.objects.filter(user=user, equipment=equipment).exists():
            raise ValueError("您已评价过该装备")

        # 创建（user由后端塞，rating别漏）
        comment = Comment.objects.create(
            user=user,
            equipment=equipment,
            content=validated_data['content'],
            rating=validated_data['rating']
        )
        return comment
        
