from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import Order, OrderItem, Cart, CartItem
from equipment.models import Equipment
from .serializers import (
    OrderSerializer,
    CreateOrderSerializer,
    UpdateOrderStatusSerializer,
    CreateRefundSerializer,
    CartSerializer,
    CartItemSerializer,
    AddCartItemSerializer,
    UpdateCartItemSerializer
)
from .services import OrderService


class OrderPagination(PageNumberPagination):
    """订单分页：每页10条，支持 ?page=2&page_size=20 自定义"""
    page_size = 10
    # 自定义分页参数名
    page_size_query_param = 'page_size'
    # 最大每页数量
    max_page_size = 50


class OrderViewSet(viewsets.ModelViewSet):
    """用户订单视图"""
    permission_classes = [IsAuthenticated]
    pagination_class = OrderPagination
    # 查询订单集，自动取消未支付订单
    def get_queryset(self):
        OrderService.auto_cancel_unpaid_orders()
        queryset = Order.objects.prefetch_related('items').filter(user=self.request.user).order_by('-create_time')
        # 从查询参数中获取订单状态，根据状态过滤
        status = self.request.query_params.get('status')
        if status and status.isdigit():
            queryset = queryset.filter(order_status=int(status))
        return queryset
    # 序列化器
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateOrderSerializer
        return OrderSerializer
    def get_object(self):
        return get_object_or_404(Order, pk=self.kwargs['pk'], user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = OrderService.create_order(
                user=request.user,
                validated_data=serializer.validated_data
            )
            return Response(
                {'message': '订单创建成功', 'order_id': order.id, 'order_sn': order.order_sn},
                status=status.HTTP_201_CREATED
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def pay(self, request):
        """
        用户发起支付（一步完成）
        模拟支付平台：点击支付后立即确认支付成功
        """
        order = self.get_object()
        payment_method = request.data.get('payment_method', 'alipay')

        try:
            order, payment_result = OrderService.pay_order(order, payment_method)
            return Response({
                'message': '支付成功',
                'trade_no': payment_result['trade_no'],
                'pay_time': payment_result['pay_time'],
                'method': payment_result['method'],
                'amount': str(order.total_amount),
                'order_status': order.order_status,
                'order_status_display': order.get_order_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """取消订单"""
        order = self.get_object()

        try:
            OrderService.cancel_order(order, request.user)
            return Response({'message': '订单取消成功'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def refund(self, request):
        """提交退款申请"""
        order = self.get_object()
        serializer = CreateRefundSerializer(data=request.data, context={'order': order})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            order = OrderService.refund_order(
                order=order,
                user=request.user,
                reason_type=serializer.validated_data['refund_reason_type'],
                custom_reason=serializer.validated_data.get('refund_reason_custom', '')
            )
            return Response({
                'message': '退款申请已提交',
                'refund_status': order.get_refund_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def pay_overdue_debt(self, request, pk=None):
        """用户支付逾期欠费"""
        order = self.get_object()

        try:
            order = OrderService.pay_overdue_debt(order, request.user)
            return Response({
                'message': '欠费支付成功',
                'overdue_debt': str(order.overdue_debt),
                'order_status': order.order_status,
                'order_status_display': order.get_order_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def apply_return(self, request):
        """用户申请归还"""
        order = self.get_object()

        try:
            order = OrderService.apply_return(order, request.user)
            return Response({
                'message': '归还申请已提交，请等待管理员确认',
                'order_status': order.order_status,
                'order_status_display': order.get_order_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OrderAdminViewSet(viewsets.ModelViewSet):
    """管理员订单视图"""
    permission_classes = [IsAdminUser]
    pagination_class = OrderPagination

    def get_queryset(self):
        OrderService.auto_cancel_unpaid_orders()
        queryset = Order.objects.prefetch_related('items').all().order_by('-create_time')
        keyword = self.request.query_params.get('keyword')
        status = self.request.query_params.get('status')
        
        if keyword:
            queryset = queryset.filter(
                Q(order_sn__icontains=keyword) |
                Q(user__username__icontains=keyword)
            )
        if status :
            queryset = queryset.filter(order_status=int(status))
        
    
        
        return queryset

    def get_serializer_class(self):
        if self.action in ['update_status', 'partial_update_status']:
            return UpdateOrderStatusSerializer
        return OrderSerializer

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        """更新订单状态"""
        order = get_object_or_404(Order, pk=pk)
        new_status = request.data.get('order_status')

        if new_status is None:
            return Response({'error': '请提供 order_status'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_status = int(new_status)
        except (ValueError, TypeError):
            return Response({'error': 'order_status 必须是整数'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = UpdateOrderStatusSerializer(
            data={'order_status': new_status},
            instance=order
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            OrderService.update_order_status(order, new_status, is_admin=True)
            return Response({'message': '订单状态更新成功'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """管理员取消订单"""
        order = get_object_or_404(Order, pk=pk)

        try:
            OrderService.cancel_order(order, request.user, is_admin=True)
            return Response({'message': '订单取消成功'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """管理员处理退款"""
        order = get_object_or_404(Order, pk=pk)

        serializer = CreateRefundSerializer(data=request.data, context={'order': order})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reason_type = serializer.validated_data['refund_reason_type']
        custom_reason = serializer.validated_data.get('refund_reason_custom', '')

        try:
            order = OrderService.refund_order(
                order=order,
                user=request.user,
                is_admin=True,
                reason_type=reason_type,
                custom_reason=custom_reason
            )
            return Response({
                'message': '退款处理完成',
                'refund_status': order.get_refund_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def deliver(self, request, pk=None):
        """管理员发货"""
        order = get_object_or_404(Order, pk=pk)

        try:
            order = OrderService.deliver_order(order, is_admin=True)
            return Response({
                'message': '发货成功',
                'order_status': order.order_status,
                'order_status_display': order.get_order_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def confirm_return(self, request, pk=None):
        """管理员确认归还"""
        order = get_object_or_404(Order, pk=pk)

        try:
            order = OrderService.confirm_return(order, request.user, is_admin=True)
            return Response({
                'message': '归还确认成功，押金已退还',
                'overdue_days': order.overdue_days,
                'overdue_fee': str(order.overdue_fee),
                'overdue_debt': str(order.overdue_debt),
                'actual_return_amount': str(order.actual_return_amount),
                'deposit_status': order.get_deposit_status_display(),
                'order_status': order.order_status,
                'order_status_display': order.get_order_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def buyout(self, request, pk=None): 
        """用户执行装备买断"""
        order = get_object_or_404(Order, pk=pk)

        try:
            order = OrderService.buyout_order(order, is_admin=True)
            return Response({
                'message': '装备买断处理成功',
                'buyout_amount': str(order.buyout_amount),
                'deposit_status': order.get_deposit_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def force_buyout(self, request, pk=None):
        """管理员强制买断（逾期过长）"""
        order = get_object_or_404(Order, pk=pk)

        try:
            order = OrderService.force_buyout_overdue(order, is_admin=True)
            return Response({
                'message': '强制买断成功',
                'overdue_days': order.overdue_days,
                'overdue_fee': str(order.overdue_fee),
                'buyout_amount': str(order.buyout_amount),
                'order_status': order.order_status,
                'order_status_display': order.get_order_status_display()
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def freeze_user(self, request, pk=None):
        """管理员冻结用户账户"""
        order = get_object_or_404(Order, pk=pk)

        try:
            user = OrderService.freeze_user(order, is_admin=True)
            return Response({
                'message': '用户账户已冻结',
                'user_id': user.id,
                'username': user.username,
                'is_frozen': user.is_frozen,
                'frozen_reason': user.frozen_reason,
                'frozen_time': user.frozen_time.strftime('%Y-%m-%d %H:%M:%S') if user.frozen_time else None
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def check_overdue(self, request):
        """检查所有逾期订单并自动处理"""
        try:
            OrderService.check_overdue_orders()
            return Response({'message': '逾期订单检查完成'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CartViewSet(viewsets.GenericViewSet):
    """购物车视图集"""
    permission_classes = [IsAuthenticated]

    def _get_cart(self, user):
        """获取用户购物车"""
        cart, created = Cart.objects.get_or_create(user=user)
        return cart

    def _calculate_cart(self, cart):
        """计算购物车总金额"""
        items = cart.items.all().select_related('equipment')
        total_count = sum(item.count for item in items)
        total_rental = sum(item.equipment.daily_rental * item.count * item.rental_days for item in items)
        total_deposit = sum(item.equipment.deposit * item.count for item in items)
        return {
            'cart': cart,
            'items': items,
            'total_count': total_count,
            'total_rental': total_rental,
            'total_deposit': total_deposit
        }

    @action(detail=False, methods=['get'])
    def list(self, request):
        """获取购物车商品列表"""
        cart = self._get_cart(request.user)
        data = self._calculate_cart(cart)
        serializer = CartSerializer(data['cart'], context={'request': request})
        response_data = serializer.data
        response_data['total_count'] = data['total_count']
        response_data['total_rental'] = str(data['total_rental'])
        response_data['total_deposit'] = str(data['total_deposit'])
        return Response(response_data)

    @action(detail=False, methods=['post'])
    def add(self, request):
        """添加装备到购物车"""
        serializer = AddCartItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        equipment_id = serializer.validated_data['equipment_id']
        count = serializer.validated_data['count']
        rental_days = serializer.validated_data['rental_days']

        try:
            equipment = Equipment.objects.get(pk=equipment_id)
        except Equipment.DoesNotExist:
            return Response({'error': '装备不存在'}, status=status.HTTP_404_NOT_FOUND)

        if equipment.stock <= 0:
            return Response({'error': '该装备库存不足'}, status=status.HTTP_400_BAD_REQUEST)

        cart = self._get_cart(request.user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            equipment=equipment,
            defaults={'count': count, 'rental_days': rental_days}
        )

        if not created:
            new_count = cart_item.count + count
            if new_count > equipment.stock:
                return Response({'error': f'库存不足，最多可添加{equipment.stock}件'}, status=status.HTTP_400_BAD_REQUEST)
            cart_item.count = new_count
            cart_item.rental_days = rental_days
            cart_item.save()

        data = self._calculate_cart(cart)
        serializer = CartSerializer(data['cart'], context={'request': request})
        response_data = serializer.data
        response_data['total_count'] = data['total_count']
        response_data['total_rental'] = str(data['total_rental'])
        response_data['total_deposit'] = str(data['total_deposit'])
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['put'])
    def update_item(self, request):
        """更新购物车商品数量"""
        item_id = request.data.get('item_id')
        if not item_id:
            return Response({'error': '缺少item_id'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = CartItem.objects.get(pk=item_id)
        except CartItem.DoesNotExist:
            return Response({'error': '购物车商品不存在'}, status=status.HTTP_404_NOT_FOUND)

        if cart_item.cart.user != request.user:
            return Response({'error': '无权操作此购物车'}, status=status.HTTP_403_FORBIDDEN)

        serializer = UpdateCartItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        new_count = serializer.validated_data['count']
        new_rental_days = serializer.validated_data['rental_days']

        if new_count > cart_item.equipment.stock:
            return Response({'error': f'库存不足，最多{cart_item.equipment.stock}件'}, status=status.HTTP_400_BAD_REQUEST)

        cart_item.count = new_count
        cart_item.rental_days = new_rental_days
        cart_item.save()

        data = self._calculate_cart(cart_item.cart)
        serializer = CartSerializer(data['cart'], context={'request': request})
        response_data = serializer.data
        response_data['total_count'] = data['total_count']
        response_data['total_rental'] = str(data['total_rental'])
        response_data['total_deposit'] = str(data['total_deposit'])
        return Response(response_data)

    @action(detail=False, methods=['delete'], url_path=r'remove/(?P<item_id>\d+)')
    def remove_item(self, request, item_id=None):
        """删除购物车商品"""
        if not item_id:
            return Response({'error': '缺少item_id'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = CartItem.objects.get(pk=item_id)
        except CartItem.DoesNotExist:
            return Response({'error': '购物车商品不存在'}, status=status.HTTP_404_NOT_FOUND)

        if cart_item.cart.user != request.user:
            return Response({'error': '无权操作此购物车'}, status=status.HTTP_403_FORBIDDEN)

        cart = cart_item.cart
        cart_item.delete()

        data = self._calculate_cart(cart)
        serializer = CartSerializer(data['cart'], context={'request': request})
        response_data = serializer.data
        response_data['total_count'] = data['total_count']
        response_data['total_rental'] = str(data['total_rental'])
        response_data['total_deposit'] = str(data['total_deposit'])
        return Response(response_data)

    @action(detail=False, methods=['post'])
    def clear(self, request):
        """清空购物车"""
        cart = self._get_cart(request.user)
        cart.items.all().delete()

        data = self._calculate_cart(cart)
        serializer = CartSerializer(data['cart'], context={'request': request})
        response_data = serializer.data
        response_data['total_count'] = data['total_count']
        response_data['total_rental'] = str(data['total_rental'])
        response_data['total_deposit'] = str(data['total_deposit'])
        return Response(response_data)
