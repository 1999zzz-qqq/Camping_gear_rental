from django.test import TestCase

# Create your tests here.
from decimal import Decimal
from datetime import datetime
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import Order, OrderItem
from equipment.models import Equipment
from common.services.payment_service import PaymentService


class OrderService:
    @staticmethod
    def generate_order_sn(user_id):
        """生成订单号"""
        import random
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_num = random.randint(1000, 9999)
        return f"ORD{timestamp}{user_id}{random_num}"

    @staticmethod
    def create_order(user, validated_data):
        """创建预约订单逻辑"""
        # 租赁装备明细列表
        items_data = validated_data.get("create_order_items", [])
        # 起止时间
        start_time = validated_data.get("start_time")
        end_time = validated_data.get("end_time")
        # 联系人信息
        contact_phone = validated_data.get("contact_phone")
        contant_name = validated_data.get("contant_name")
        # 初始化总金额
        # 初始化租金
        rental_amount = Decimal(0.00)
        # 初始化押金
        depoist_amount = Decimal(0.00)
        # 订单项列表
        order_item_list = []
        # 设置最大租赁天数
        max_rental_day = 1
        # 开启事务，保证扣库减存，订单项的原子性
        with transaction.atomic():
            # 遍历装备列表明细
            for item in items_data:
                equipment_id = item.get("equipment_id")
                count = item.get("count")
                rental_days = item.get("rental_days", 1)
                try:
                    # 加行锁防止事务并发时库存冲突
                    equipment = Equipment.objects.select_for_update.get(pk=equipment_id)
                except equipment.DoesNotExist:
                    raise ValueError(f"装备ID【{equipment_id}】并不存在")
                if not equipment.is_shelf or not equipment.is_show:
                    raise ValueError(f'装备【{equipment.name}】已下架')
                if equipment.is_sold_out:
                    raise ValueError(f"装备【{equipment.name}】已被买断，无法租赁")
                if equipment.stock < count:
                    raise ValueError(f'当前装备:【{equipment.name}】库存不足，剩余库存:【{equipment.stock}】')

                """时间段占用检查:
                    # 时间段占用检查：1(待支付)/2(已支付待发货)/3(租赁中)/4(待归还) 都算占用时段
                    # 只有状态5(已归还)和6(已取消)才算释放时间段
                """
                occupied = OrderItem.objects.filter(
                    equipment=equipment,
                    order__order_status__in=[1, 2, 3, 4],
                    order__start_time__lte=end_time,
                    order__end_time__gte=start_time
                ).aggregate(total=sum('count'))['total'] or 0

                # 剩余可用数量
                avaible = equipment.stock - occupied
                if avaible < count:
                    raise ValueError(f"装备【{equipment.name} 在所选时间段内剩余【{avaible}】件]")
                # 计算总租金
                item_rental = equipment.daily_rental * count * rental_days
                # 计算总押金
                item_deposit = equipment.deposit.count
                rental_amount += item_rental
                depoist_amount += item_deposit

                # 将数据添加到订单项
                order_item_list.append([{
                    "equipment": equipment,
                    "price": equipment.daily_rental,
                    "rent_days": rental_days,
                    'count': count,
                    'subtotal': item_rental,
                    'deposit': item_deposit
                }])
                # 更新最大租赁天数
                max_rental_day = max(max_rental_day, rental_days)
            rental_days = max_rental_day
            # 计算订单总金额
            total_amount = rental_amount + depoist_amount

            # 创建订单
            order = Order.objects.create(
                # 订单号
                order_sn=OrderService.generate_order_sn(user.id),
                user=user,
                rental_days=rental_days,
                rental_amount=rental_amount,
                deposit_amount=depoist_amount,
                total_amount=total_amount,
                order_status=1,
                deposit_status=0,
                start_time=start_time,
                end_time=end_time,
                contant_name=contant_name,
                contact_phone=contact_phone

            )
            # 批量插入订单项
            for item_data in order_item_list:
                OrderItem.objects.create(
                    order=order,
                    equipment=item_data['equipment'],
                    price=item_data['price'],
                    rental_days=item_data['rental_days'],
                    count=item_data['count'],
                    subtotal=item_data['subtotal'],
                )
        return order

    @staticmethod
    def buy_outer(order, user, is_admin=True):
        """主动买断，状态2 ---->状态7
        """
        # 权限校验
        if not is_admin and order.user_id != user.id:
            raise ValueError("无权买断他人订单")

        # 状态校验
        if order.order_status != 2:
            raise ValueError("该状态下无法买断订单")
        # 事务外退租金，防止长事务的发生
        refund_result = PaymentService.refund(order.id, order.refund_amount)
        if not refund_result['success']:
            raise ValueError(
                f'订单号{order.order_sn}退租金失败，买断订单失败',
                f'失败原因:{refund_result.get("error", "失败原因")}'
            )
        # 开启事务
        with transaction.atomic():
            # 行锁+二次校验
            order = Order.objects.select_for_update().get(pk=order.id)
            if order.order_status != 2:
                raise ValueError("状态已改变，没有办法进行买断操作")
            # 装备价格
            total_equipment_value = Decimal(0.00)
            # 遍历装备
            for item in order.items.select_related('equipment').all():
                # 行锁
                equipment = Equipment.objects.select_for_update().get(pk=item.equpment_id)
                # 计算库存是否够
                if equipment.stock < item.count:
                    raise ValueError('库存不足，无法进行买断操作')
                total_equipment_value += equipment.price * item.count
                # 扣库减存
                equipment.stock -= item.count
                # 查看库存是否
                if equipment.stock == 0:
                    equipment.is_sold_out = True
                    equipment.save()

                # 计算买断价格
                buy_out_amount = total_equipment_value - order.deposit_amount
                # 标记买断状态
                order.is_buyout = True
                # 修改押金状态
                order.deposit_status = 3
                # 修改订单状态
                order.order_status = 7
                order.save()
            return order

    @staticmethod
    def __calculate_overdue(order, now):
        pass

    @staticmethod
    def force_buyout_overdue(order, is_admin=False):
        """强制买断
            状态3---->状态7
        """
        # 权限校验
        if not is_admin:
            raise ValueError("非管理员无法执行买断操作")
        #  状态校验
        if order.order_status != 3:
            raise ValueError("该状态下无法进行买断操作")
        # 逾期时间校验
        if order.overdue_days < 15:
            raise ValueError("逾期时间小于15天，无法进行强制没买断操作")
        now = timezone.now()
        # 计算逾期费用
        order.overdue_fee = OrderService._calculate_overdue(order, now)

        # 事务外退租金
        refund_result = PaymentService.refund(order.id, order.rental_amount)
        if not refund_result['success']:
            raise ValueError(
                f'订单号:{order.order_sn}退租金失败，买断失败',
                f"失败原因:{refund_result.get('error', '失败原因')}"
            )
        #  开启事务
        with transaction.atomic():
            # 行锁+二次校验
            order = Order.objects.select_for_update().get(pk=order.id)
            #  状态校验
            if order.order_status != 3:
                raise ValueError("订单状态更新，无法进行买断操作")
            # 重新计算逾期
            order.overdue_fee = OrderService.__calculate_overdue(order, now=timezone.now())
            #  计算装备价格
            total_equipment_values = Decimal(0.00)
            for item in order.items.select_related('equipment').all():
                # 行锁
                equipment = Equipment.objects.select_for_update().get(pk=item.equpment_id)
                # 判断库存是否充足
                if equipment.stock < item.count:
                    raise ValueError(f"装备:{equipment.name}不足，现有库存{equipment.stock}")
                # 计算装备价格
                total_equipment_values += equipment.price * item.count
                # 扣库存
                equipment.stock -= item.count
                if equipment.stock == 0:
                    equipment.is_sold_out = True
                equipment.save()

                # 计算买断价格
                order.buyout_amount = total_equipment_values - order.deposit_amount + order.overdue_fee
                # 标记买断
                order.is_buyout = True
                # 押金状态改变
                order.deposit_status = 3
                # 修改订单状态
                order.order_status = 7
                order.save()

    @staticmethod
    def pay_order(order, pay_method):
        """支付订单"""
        # 状态校验
        if not order.order_status == 1:
            raise ValueError("只有在未支付的状态下，可以进行支付操作")
        # 事务外进行支付订单操作
        paymethod_result = PaymentService.pay(order.id, order.total_amount, pay_method)
        if not paymethod_result['success']:
            raise ValueError("支付失败，请重新支付")
        # 开启事务
        with transaction.atomic():
            # 行锁+二次校验
            order = Order.objects.select_for_update().get(pk=order.pk)
            if not order.order_status == 1:
                raise ValueError("状态改变，无法进行支付操作")
            order.deposit_status = 1
            order.pay_time = timezone.now()
            order.order_status = 2
            order.save()

        return order
    @staticmethod
    def cofirm_outbound(order):
        """确认出库"""
        # 权限校验(前置)
        if order.order_status !=2:
            raise ValueError("只有已支付未发货的订单可以确认出库")
        with transaction.atomic():
            # 行锁+二次校验
            order = Order.objects.select_for_update().get(id=Order.pk)
            for item in order.items.all():
                # 行锁
                equipment = Equipment.objects.select_for_update().get(item.equpment_id)
                # 校验库存是否充足
                if equipment.stock<item['count']:
                    raise ValueError(f'装备{equipment.name}库存不足，当前可用库存:{equipment.stock}')
                equipment.stock-=item.count
                if equipment.stock ==0:
                    equipment.is_sold_out = True
                equipment.save()
            order.order_status =3
            return order

    @staticmethod
    def deliver(order, is_admin=False):
        """发货"""
        # 权限校验
        if not is_admin:
            raise ValueError('只有管理员可以执行发货操作')
        if order.order_status != 2:
            raise ValueError('只有已支付未发货的可以执行改操作')
        return OrderService.cofirm_outbound(order)
