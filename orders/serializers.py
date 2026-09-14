from rest_framework import serializers
from .models import Order, OrderItem, Cart, CartItem


class OrderItemSerializer(serializers.ModelSerializer):
    equipment_id = serializers.IntegerField(source='equipment.id', read_only=True)
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'equipment_id', 'equipment_name', 'price', 'rental_days', 'count', 'subtotal']
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    order_status_display = serializers.CharField(
        source='get_order_status_display', read_only=True
    )
    refund_status_display = serializers.CharField(
        source='get_refund_status_display', read_only=True
    )
    deposit_status_display = serializers.CharField(
        source='get_deposit_status_display', read_only=True
    )
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_sn', 'user_name',
            'order_status', 'order_status_display',
            'rental_days', 'rental_amount', 'deposit_amount', 'total_amount',
            'deposit_status', 'deposit_status_display',
            'overdue_rate', 'return_time', 'overdue_days',
            'overdue_fee', 'overdue_debt', 'actual_return_amount',
            'is_buyout', 'buyout_amount',
            'start_time', 'end_time',
            'contact_name', 'contact_phone',
            'create_time', 'pay_time',
            'items',
            'refund_status', 'refund_status_display',
            'refund_amount', 'refund_reason_type', 'refund_reason_custom',
            'refund_apply_time', 'refund_success_time', 'refund_fail_time', 'refund_fail_reason'
        ]
        read_only_fields = fields


class CreateOrderItemSerializer(serializers.Serializer):
    equipment_id = serializers.IntegerField()
    count = serializers.IntegerField(min_value=1)
    rental_days = serializers.IntegerField(min_value=1, default=1)


class CreateOrderSerializer(serializers.Serializer):
    create_order_items = CreateOrderItemSerializer(many=True)
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    contact_name = serializers.CharField(max_length=20)
    contact_phone = serializers.CharField(max_length=11)

    def validate_create_order_items(self, value):
        if not value:
            raise serializers.ValidationError('请至少选择一件装备')
        ids = [i['equipment_id'] for i in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('同一装备请合并数量，请勿重复添加')
        return value

    def validate(self, attrs):
        if attrs['start_time'] >= attrs['end_time']:
            raise serializers.ValidationError('结束时间必须晚于开始时间')
        return attrs


class UpdateOrderStatusSerializer(serializers.Serializer):
    order_status = serializers.IntegerField()

    def validate_order_status(self, value):
        # 允许的目标状态：2(已支付) 3(租赁中) 4(待归还) 5(已归还) 6(已取消) 7(已买断)
        if value not in [2, 3, 4, 5, 6, 7]:
            raise serializers.ValidationError('状态值不合法')
        return value

    def validate(self, attrs):
        order = self.instance
        if order:
            # 状态流转规则（与 service.update_order_status 分发逻辑完全一致）
            # 1(待支付)   → 2(已支付) / 6(已取消)
            # 2(已支付)   → 3(租赁中) / 6(已取消) / 7(主动买断)
            # 3(租赁中)   → 4(待归还) / 7(强制买断)
            # 4(待归还)   → 5(已归还)
            allowed = {
                1: {2, 6},
                2: {3, 6, 7},
                3: {4, 7},
                4: {5},
            }.get(order.order_status, set())
            if attrs['order_status'] not in allowed:
                raise serializers.ValidationError('当前状态不允许该操作')
        return attrs


class CreateRefundSerializer(serializers.Serializer):
    refund_reason_type = serializers.ChoiceField(choices=Order.REFUND_REASON_CHOICES, label='退款原因')
    refund_reason_custom = serializers.CharField(
        required=False,
        max_length=255,
        allow_blank=True,
        label='自定义原因'
    )

    def validate(self, attrs):
        order = self.context.get('order')
        if not order:
            raise serializers.ValidationError('订单不存在')
        if order.refund_status != 0:
            raise serializers.ValidationError('订单已提交过退款，不能重复申请')
        if order.order_status != 2:
            raise serializers.ValidationError('订单状态不允许退款（仅已支付订单可退款）')
        if attrs.get('refund_reason_type') == 'other' and not attrs.get('refund_reason_custom'):
            raise serializers.ValidationError('请填写自定义退款原因')
        return attrs


class CartItemSerializer(serializers.ModelSerializer):
    equipment_id = serializers.IntegerField(source='equipment.id', read_only=True)
    equipment_name = serializers.CharField(source='equipment.name', read_only=True)
    equipment_price = serializers.DecimalField(source='equipment.price', max_digits=8, decimal_places=2, read_only=True)
    daily_rental = serializers.DecimalField(source='equipment.daily_rental', max_digits=8, decimal_places=2, read_only=True)
    deposit = serializers.DecimalField(source='equipment.deposit', max_digits=8, decimal_places=2, read_only=True)
    cover_img_url = serializers.SerializerMethodField(read_only=True)
    category_name = serializers.CharField(source='equipment.category.name', read_only=True)
    stock = serializers.IntegerField(source='equipment.stock', read_only=True)

    def get_cover_img_url(self, obj):
        if not obj.equipment.cover_img:
            return ''
        request = self.context.get('request')
        return request.build_absolute_uri(obj.equipment.cover_img.url) if request else obj.equipment.cover_img.url

    class Meta:
        model = CartItem
        fields = [
            'id', 'equipment_id', 'equipment_name', 'equipment_price',
            'daily_rental', 'deposit', 'count', 'rental_days',
            'cover_img_url', 'category_name', 'stock'
        ]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_count = serializers.IntegerField(read_only=True)
    total_rental = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_deposit = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_count', 'total_rental', 'total_deposit']


class AddCartItemSerializer(serializers.Serializer):
    equipment_id = serializers.IntegerField()
    count = serializers.IntegerField(min_value=1, default=1)
    rental_days = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=1)
    rental_days = serializers.IntegerField(min_value=1)