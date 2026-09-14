
from rest_framework import serializers
from .models import Comment
# 评论序列化器
class CommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)  # 只给用户名
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'content', 'rating', 'username', 'equipment_name', 'create_time']
        read_only_fields = ['id', 'create_time']

# 评论创建序列化器
class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['content', 'rating', 'equipment']
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
    def validate_rating(self, value):
        if value not in [1,2,3,4,5]:
            raise serializers.ValidationError('评分必须在1-5之间')
        return value
    def validate_content(self, value):
        # 过滤HTML标签,防止XSS攻击
        import bleach
        value = bleach.clean(value, tags=[], attributes={})
        if len(value) < 10:
            raise serializers.ValidationError('评论内容不能少于10个字符')
        if len(value) > 200:
            raise serializers.ValidationError('评论内容不能超过200个字符')
        return value
# 修改评论序列化器
class CommentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['content', 'rating', ]
    def validate_rating(self, value):
        if value not in [1,2,3,4,5]:
            raise serializers.ValidationError('评分必须在1-5之间')
        return value
    def validate_content(self, value):
        if len(value) < 10:
            raise serializers.ValidationError('评论内容不能少于10个字符')
        if len(value) > 200:
            raise serializers.ValidationError('评论内容不能超过200个字符')
        return value
