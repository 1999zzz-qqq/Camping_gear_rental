from django.test import TestCase

# Create your tests here.
from decimal import Decimal
from datetime import datetime
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from orders.models import Order, OrderItem
from equipment.models import Equipment
from common.services.payment_service import PaymentService


class OrderServices:
    @staticmethod
    def generate_order_sn(user_id):
        """生成订单号"""
        import random
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_num = random.randint(1000, 9999)
        return f"ORD{timestamp}{user_id}{random_num}"

    @staticmethod
    def _simulate_payment_refund(order):
        """模拟支付系统退款"""
        import random

        if random.random() < 0.95:
            return {
                'success': True,
                'message': '退款成功',
                'transaction_id': f"REF{order.order_sn[3:]}"
            }
        else:
            return {
                'success': False,
                'error': '支付系统繁忙，请稍后重试'
            }

    @staticmethod
    def create_order(user, validated_data):
        """创建订单只做预约操作，并不直接扣库减存"""
        # 提取订单项
        items_data = validated_data['create_order_item', []]
        # 起止时间
        start_time = validated_data['start_time']
        end_time = validated_data['end_time']
        # 联系人信息
        contact_phone = validated_data['contact_phone']
        contact_name = validated_data['contact_name']

        # 初始化计算量
        # 总租金
        rental_amount = Decimal(0.00)
        # 总押金
        depoist_amount = Decimal(0.00)
        # 最大租赁天数
        max_rental_day = 1
        # 订单项列表
        order_items = []
        # 开启事务循环遍历订单项列表
        with transaction.atomic():
            # 遍历装备列表明细
            for item in items_data:
                equipment_id = item['equipment_id']
                rental_days = item['rental_days']
                count = item['count']
                try:
                    equipment = Equipment.objects.select_for_update.get(pk=equipment_id)
                except equipment.DoesNotExist:
                    raise ValueError(f'装备:{equipment.name}不存在')
                if equipment.stock < count:
                    raise ValueError(f'装备:{equipment.name}库存不足,现有库存:{equipment.stock}')
                if not equipment.is_show or not equipment.is_shelf:
                    raise ValueError(f'装备{equipment.name}尚未上架或被管理员隐藏')
                # 时间段校验(意在查询相同时间段的订单状态)
                """时间段占用检查:
                          # 时间段占用检查：1(待支付)/2(已支付待发货)/3(租赁中)/4(待归还) 都算占用时段
                          # 只有状态5(已归还)和6(已取消)才算释放时间段
                                """
                occupied = OrderItem.objects.filter(
                    equipment=equipment,
                    order__order_status__in=[1, 2, 3, 4],
                    order__start_time__lte=end_time,
                    order__end_time__gte=start_time,
                ).aggregate(total=sum('count'))['total'] or 0
                # 剩余可用量
                available = equipment.stock - occupied
                if available < count:
                    raise ValueError(f'装备{equipment.name}在所选时间段剩余{available}件，不足以完成订单需求')
                # 计算总租金
                rental_amount = equipment.daily_rental * count * rental_days
                # 计算押金
                depoist_amount = equipment.deposit * count
                # 总金额
                total_amount = rental_amount + depoist_amount
                # 将数据添加到订单项列表
                order_items.append({
                    'equipment': equipment,
                    'price': equipment.daily_rental,
                    'rental_days': rental_days,
                    'count': count,
                    'subtotal': rental_amount,
                })
        # 创建主订单
        order = Order.objects.create(
            order_sn=OrderServices.generate_order_sn(user.id),
            user=user,
            rental_days=rental_days,
            deposit_amount=depoist_amount,
            rental_amount=rental_amount,
            total_amount=total_amount,
            order_status=1,
            deposit_status=0,
            contact_phone=contact_phone,
            contact_name=contact_name,
            create_time=timezone.now(),
            start_time=start_time,
            end_time=end_time
        )
        # 批量添加订单明细信息
        item_obj = []
        for item_data in order_items:
            item_obj.append(OrderItem(
                order=order,
                equipment=item_data['equipment'],
                price=item_data['price'],
                subtotal=item_data['item'],
                rental_days=item_data['rental_days'],
                count=item_data['count']
            ))
        OrderItem.objects.bulk_create(item_obj)

    # 取消订单
    @staticmethod
    def cancal_order(user, order, is_admin=False):
        # 权限校验
        if not is_admin or user.id != user.id:
            raise ValueError('无权取消他人订单')
        # 状态校验
        if order.order_status not in [1, 2]:
            raise ValueError('该状态无法做取消订单操作')
        # 第三方支付调用，放在外部以防长事务
        pay_result = PaymentService.refund(order.id, order.total_amount)
        if not pay_result['success']:
            raise ValueError(f'订单号{order.order_sn}的订单退款失败')
        # 事务校验退款订单，租金押金要同时退款所以为了保证事务的原子性
        with transaction.atomic():
            # 加行锁
            payment = Order.objects.select_for_update().get(pk=order.id)
            # 校验订单状态，防止在并发状态下，订单状态被修改
            if order.order_status not in [1, 2]:
                raise ValueError("改状态无法做取消订单的操作")
            # 给已支付未发货的订单退款
            if order.order_status == 2:
                # 退款状态改为已退款
                order.refund_status = 2
                # 退款金额
                order.refund_amount = order.total_amount
                # 更新退款时间
                order.refund_success_time = timezone.now()
                order.save()
            # 整体做一个状态修改，无论是未支付还是已支付
            order.order_status = 6
            order.save()

    # 确认出库
    @staticmethod
    def confirm_out(order):
        '''
        从状态2(已支付未发货)到状态3(租赁中)实现出库操作
        :param order:
        :return:
        '''
        # 权限校验
        if order.order_status != 2:
            raise ValueError(f'该状态下无法实现出库操作')
        # 开启事务
        with transaction.atomic():
            """
            由于扣库减存需要装备库存扣减，创建订单和订单明细一起成功和失败，为了保证原子性开启事务
            """
            # 首先将订单项先从订单中取出来
            order_list = Order.objects.select_for_update().prefetch_related("items").get(pk=order.id)
            # 循环遍历订单项
            for item in order_list:
                # 加行锁确保并发的事务性
                equipment = Equipment.objects.select_for_update().get(pk=equipment.id)
                # 校验库存是否够
                if equipment.stock < item.count:
                    raise ValueError(f'装备{equipment.name}库存不足，现有库存:{equipment.stock}')
                # 扣减库存
                equipment.stock -= item.count
                order.save()
            # 修改订单状态
            order.order_status = 3
            order.save()
            return order

    @staticmethod
    def update_status(order, new_status, is_admin=False):
        from orders.services import OrderService
        #  权限校验
        if not is_admin:
            raise ValueError("只有管理员可以修改状态")
        # 取出当前的状态
        current_status = order.order_status
        # 利用条件语句做状态分发
        if current_status == 1 and new_status == 2:
            order, _ = OrderService.pay_order(order, payment_method='admin')
            return order
        elif current_status == 2 and new_status == 3:
            return OrderService.confirm_outbound(order.order.user)
        elif current_status == 2 and new_status == 6:
            return OrderService.cancel_order(order, order.user, is_admin=False)
        elif current_status == 3 and new_status == 4:
            return OrderService.apply_return(order, order.user)
        elif current_status == 4 and new_status == 5:
            return OrderService.confirm_return(order, order.user, is_admin=False)
        elif current_status == 2 and new_status == 7:
            return OrderService.buyout_order(order, is_admin=False)
        else:
            raise ValueError("不允许这种状态转变")
        return order

    @staticmethod
    def buy_outer(order, is_admin=True):
        """主动买断"""
        if not is_admin:
            raise ValueError(f"没有买断的权限")
        if not order.order_status == 2:
            raise ValueError('该状态不支持买断操作')
        # 事务外退还租金
        refund_result = PaymentService.refund(order.id, order.rental_amount)
        if not refund_result['success']:
            raise ValueError(
                f'订单号{order.order_sn}租金退还失败,买断失败',
                f"失败原因：{refund_result.get('error', '退款失败')}"
            )
        # 开启事务
        with transaction.atomic():
            # 行锁+二次校验，防止并发下单的状态的导致状态变更
            order = Order.objects.select_for_update().get(pk=order.id)
            if not order.order_status == 2:
                raise ValueError('状态已经变更，不支持买断')
            # 装备总价 = 装备的数量 x装备单价
            item_equipment_values = Decimal(0.00)
            for item in order.items.select_related('equipment').all():
                # 加行锁查询各个装备
                equipment = Equipment.objects.select_for_update().get(pk=item.equipment_id)
                if equipment.stock < item.count:
                    raise ValueError(f"装备{equipment.name}库存不足，买断失败")
                # 装备总价
                item_equipment_values += equipment.price * item.count
                # 扣减库存
                equipment.stock -= item.count
                # 判断有没有被扣光
                if equipment.stock == 0:
                    equipment.is_sold_out = True
                equipment.save()

            # 计算买断价格 买断价格=装备价格-总押金
            order.buyout_amount = item_equipment_values - order.depoist_amount
            # 修改买断状态
            order.is_buyout = True
            # 押金改为已扣除
            order.deposit_status = 3
            # 订单状态修改
            order.order_status = 7
            order.save()

    @staticmethod
    def force_buyout_overdue(order, is_admin=False):
        """逾期15天强制买断
        从状态3-->状态7
        买断费用= 装备价格-押金+逾期费用
        """
        # 权限校验
        if not is_admin:
            raise ValueError('只有管理员可以执行该操作')
        # 状态校验
        if order.order_status != 3:
            raise ValueError('该状态不存在买断操作')
        # 校验有没有逾期
        if order.overdue_days < 15:
            raise ValueError("没有到强制逾期的时间，无法执行该操作")
        # 事务之前先把租金退了
        refund_result = PaymentService.refund(order.id, order.refund_amount)
        if not refund_result['success']:
            raise ValueError(
                f'订单号:{order.order_sn}退租金失败，买断失败'
                f'{refund_result.get("error", "买断失败")}'
            )
        # 开启事务
        with transaction.atomic():
            # 行锁+二次校验,防止并发事务导致状态改变
            order = Order.objects.select_for_update().get(pk=order.id)
            if order.order_status != 3:
                raise ValueError('该状态不存在买断操作')
            # 装备总价
            total_equipment = Decimal(0.00)
            for item in order.items.select_related("equipment").all():
                equipment = Equipment.objects.select_for_update().get(pk=item.equipment_id)
                # 判断库存是否充足
                if equipment.stock < item.count:
                    raise ValueError("库存不足无法进行买断操作")
                total_equipment += equipment.price * item.count
                # 扣库存
                equipment.stock -= item.count
                # 判断还有没有库存
                if equipment.stock == 0:
                    equipment.is_sold_out = True
                #  计算逾期费用
            now = timezone.now()
            overdue_days, overdue_fee = OrderServices._calculate_overdue(order, now)
            # 开启事务
            with transaction.atomic():
                # 行锁+二次校验
                order = Order.objects.select_for_update().get(pk=order.id)
                if order.order_status != 3:
                    raise ValueError('订单状态已改变，无法执行该操作')

                # 重新计算逾期费用
                now = timezone.now()
                overdue_days, overdue_fee = OrderServices._calculate_overdue(order, now)
                if overdue_days < 15:
                    raise ValueError("逾期天数不足15天，无法强制买断")

                # 计算买断价格
                order.buyout_amount = total_equipment - order.depoist_amount + overdue_fee
                # 标记已买断
                order.is_buyout = True
                # 更新买断日期
                order.overdue_days = overdue_days
                # 逾期费用
                order.overdue_fee = overdue_fee
                # 更新押金状态
                order.deposit_status = 3  # 押金转货款
                # 更新订单状态
                order.order_status = 7
                order.save()
            return order

        @staticmethod
        def auto_confirm_return(order):
            """自动确认归还
            状态4待归还的状态下，用户已经提交归还申请，是在管理员长时间没有处理的情况下，调用该函数达到自动归还的目的
            """
            # 状态校验
            if order.order_status != 4:
                raise ValueError('该状态没有自动确认归还的权限')
            # 计算逾期费用
            now = timezone.now()
            overdue_days, overdue_fee = OrderServices._calculate_overdue(order, now)
            if overdue_days < 15:
                raise ValueError('未到达设置的最大逾期天数，无法执行自动归还操作')
            # 开启事务
            with transaction.atomic():
                # 行锁+二次校验
                order = Order.objects.select_for_update().get(pk=order.id)
                # 状态校验
                if order.order_status != 4:
                    raise ValueError('该状态没有自动确认归还的权限')
                # 重新计算逾期费用，防止并发状态下出现错误
                overdue_days, overdue_fee = OrderServices._calculate_overdue(order, now)
                if overdue_days < 15:
                    raise ValueError('未到达设置的最大逾期天数，无法执行自动归还操作')

                order.return_time = now
                order.overdue_days = overdue_days
                order.overdue_fee = overdue_fee

                # 结算押金，退还剩余的押金
                actual_return_amount = order.deposit_amount - overdue_fee
                if actual_return_amount >= 0:
                    """押金有剩余，或者刚刚好"""
                    # 修改押金状态
                    order.deposit_status = 3
                    # 记录订单的实际归还押金
                    order.actual_return_amount = actual_return_amount
                    # 欠债情况设置为0
                    order.overdue_debt = Decimal(0.00)
                else:
                    # 修改押金状态
                    order.deposit_status = 3
                    # 押金不够用户还要还钱
                    # 实际归还设置为0
                    order.actual_return_amount = Decimal(0.00)
                    order.overdue_debt = abs(actual_return_amount)

                # 遍历所有装备归还装备
                for item in order.items.select_related("equipment").all():
                    # 行锁+库存归还
                    equipment = Equipment.objects.select_for_update().get(pk=item.equipment_id)
                    equipment.stock += item.count
                    equipment.save()
                order.save()
            return order

    @staticmethod
    def refund_order(order, user, reason_type=None, custom_reason=None, is_admin=True):
        # 权限校验
        if not is_admin and user.id != order.user.id:
            raise ValueError("没有申请退款的权限")
        #  状态校验
        if order.order_status != 2:
            raise ValueError("只有已经支付的订单可以申请退款")
        # 事务外退款
        refund_result = OrderServices._simulate_payment_refund(order)
        if not refund_result['success']:
            # 开启事务只改变退款状态
            with transaction.atomic():
                # 行锁+二次校验
                order = Order.objects.select_for_update().get(pk=order.pk)
                if order.order_status != 2:
                    raise ValueError('状态已经改变，无法申请退款')
                order.refund_fail_time = timezone.now()
                order.refund_apply_time = timezone.now()
                order.refund_status = 3
                order.refund_fail_reason = refund_result.get('error', '失败原因')
                order.save()
        else:
            # 退款成功更新
            order.refund_status = 2
            order.order_status = 6
            order.refund_apply_time = timezone.now()
            order.refund_success_time = timezone.now()
            order.refund_amount = order.total_amount
            order.refund_reason_type = reason_type
            if reason_type == 'other':
                order.refund_reason_custom = custom_reason
            order.save()
        return order

    @staticmethod
    def pay_order(order, pay_method):
        # 状态校验
        if order.order_status != 1:
            raise ValueError("只有未支付状态下可以支付")
        # 事务外支付订单
        payment_result = PaymentService.pay(order.id, order.total_amount, pay_method)
        if not payment_result['success']:
            raise ValueError(f"订单:{order.order_sn}支付失败，失败的原因:{payment_result.get('error', '失败的原因')}")
        with transaction.atomic():
            # 行锁+二次校验
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.order_status != 1:
                raise ValueError('状态改变，支付失败')
            order.pay_time = timezone.now()
            order.deposit_status = 1
            order.order_status = 2
            order.save()
        return order