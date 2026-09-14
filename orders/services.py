from decimal import Decimal
from datetime import datetime
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import Order, OrderItem
from equipment.models import Equipment
from common.services.payment_service import PaymentService
import logging
# 初始化日志记录器
logger = logging.getLogger(__name__)

class OrderService:
    @staticmethod
    def _calculate_overdue(order, now):
        """计算逾期天数和逾期费用（不保存数据库）
        返回 (overdue_days, overdue_fee)，未逾期返回 (0, Decimal('0'))
        逾期费封顶15天：超过15天会被强制买断，不再继续累加逾期费"""
        overdue_seconds = (now - order.end_time).total_seconds()
        if overdue_seconds <= 0:
            return 0, Decimal('0')
        overdue_days = int(overdue_seconds // 86400)
        if overdue_seconds % 86400 > 0:
            overdue_days += 1
        # 逾期费封顶15天，超过部分不再累加（超15天走强制买断）
        capped_days = min(overdue_days, 15)
        overdue_fee = order.rental_amount * (Decimal(str(order.overdue_rate)) / Decimal('100')) * capped_days
        return overdue_days, overdue_fee
    @staticmethod
    def generate_order_sn(user_id):
        """生成订单号"""
        import random
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_num = random.randint(1000, 9999)
        return f"ORD{timestamp}{user_id}{random_num}"

    @staticmethod
    def calculate_rental_days(start_time, end_time):
        """计算租赁天数"""
        delta = end_time - start_time
        days = delta.days
        if delta.seconds > 0:
            days += 1
        return max(days, 1)

    @staticmethod
    def create_order(user, validated_data):
        """创建订单"""
        items_data = validated_data.get('create_order_items', [])
        start_time = validated_data['start_time']
        end_time = validated_data['end_time']
        contact_name = validated_data['contact_name']
        contact_phone = validated_data['contact_phone']

        rental_amount = Decimal('0.00')
        deposit_amount = Decimal('0.00')
        #订单项列表
        order_items_data = []
        # 最大租赁天数
        max_rental_days = 1

        with transaction.atomic():
            # 遍历租赁装备明细列表
            for item in items_data:
                equipment_id = item['equipment_id']
                count = item['count']
                rental_days = item.get('rental_days', 1)

                try:
                    # 加行锁，防止并发更新库存时的冲突
                    equipment = Equipment.objects.select_for_update().get(id=equipment_id)
                except Equipment.DoesNotExist:
                    raise ValueError(f"装备ID {equipment_id} 不存在")

                if not equipment.is_shelf or not equipment.is_show:
                    raise ValueError(f"装备【{equipment.name}】已下架")

                if getattr(equipment, 'is_sold_out', False):
                    raise ValueError(f"装备【{equipment.name}】已被买断，无法租赁")

                if equipment.stock < count:
                    raise ValueError(f"装备【{equipment.name}】库存不足，当前库存：{equipment.stock}")

                # 时间段占用检查：1(待支付)/2(已支付待发货)/3(租赁中)/4(待归还) 都算占用时段
                # 只有状态5(已归还)和6(已取消)才算释放时间段
                occupied = OrderItem.objects.filter(
                    equipment=equipment,
                    order__order_status__in=[1, 2, 3, 4],
                    order__start_time__lte=end_time,
                    order__end_time__gte=start_time
                ).aggregate(total=Sum('count'))['total'] or 0

                available = equipment.stock - occupied
                if available < count:
                    raise ValueError(f"装备【{equipment.name}】在所选时间段仅余 {available} 件")
                
                item_rental = equipment.daily_rental * rental_days * count
                item_deposit = equipment.deposit * count

                rental_amount += item_rental
                deposit_amount += item_deposit
                ## 计算订单项金额
                order_items_data.append({
                    'equipment': equipment,
                    'price': equipment.daily_rental,
                    'rental_days': rental_days,
                    'count': count,
                    'subtotal': item_rental,
                })
                ## 更新最大租赁天数
                max_rental_days = max(max_rental_days, rental_days)
            rental_days = max_rental_days   
            # 计算订单总金额
            total_amount = rental_amount + deposit_amount
            # 创建订单
            order = Order.objects.create(
                order_sn=OrderService.generate_order_sn(user.id),
                user=user,
                rental_days=rental_days,
                rental_amount=rental_amount,
                deposit_amount=deposit_amount,
                total_amount=total_amount,
                start_time=start_time,
                end_time=end_time,
                contact_name=contact_name,
                contact_phone=contact_phone,
                order_status=1,
                deposit_status=0
            )
            # 批量插入订单项
            items_obj=[]
            for item_data in order_items_data:
                items_obj.append(OrderItem(
                    order=order,
                    equipment=item_data['equipment'],
                    price=item_data['price'],
                    rental_days=item_data['rental_days'],
                    count=item_data['count'],
                    subtotal=item_data['subtotal'],
                ))
                #批量插入订单项对象
            OrderItem.objects.bulk_create(items_obj)

        return order
    @staticmethod
    def confirm_outbound(order):
        """确认出库，扣减装备实物库存
        从状态2(已支付待发货) → 状态3(租赁中)时真正扣减库存"""
        if order.order_status != 2:
            raise ValueError("只有已支付待发货的订单才能确认出库")

        with transaction.atomic():
            # 遍历订单项，扣减装备实物库存
            # 查询订单时预先加载items,避免重复查询数据库(解决N+1查询问题)
            order = Order.objects.select_for_update().prefetch_related("items").get(pk=order.pk)
            if order.order_status != 2:
                raise ValueError("状态已改变，无法确认出库")

            for item in order.items.all():
                # 加行锁，防止并发更新库存时的冲突
                equipment = Equipment.objects.select_for_update().get(id=item.equipment_id)
                if equipment.stock < item.count:
                    raise ValueError(f"装备【{equipment.name}】库存不足，当前库存：{equipment.stock}")
                # 真正扣减实物库存
                equipment.stock -= item.count
                equipment.save()
            # 更新订单状态为租赁中
            order.order_status = 3
            order.save()

        return order

    @staticmethod
    def cancel_order(order, user, is_admin=False):
        """取消订单"""
        # 权限校验
        if not is_admin and order.user.id != user.id:
            raise ValueError("无权取消他人的订单")
        # 限制允许取消订单的状态
        if order.order_status not in [1, 2]:
            raise ValueError("当前状态不允许取消订单")
        refund_result = None
        # 第三方支付调用放到事务外部，避免长事务锁库
        if order.order_status == 2:
                # 待支付/已支付待发货状态下，退款订单金额
                refund_result = PaymentService.refund(order.id, order.total_amount)
                #  退款失败直接抛异常，不进入事务，不改动数据
                if not refund_result["success"]:
                    raise ValueError(
                        f"退款失败，订单号：{order.order_sn}取消失败，失败原因：{refund_result.get('error', '退款失败')}"
                    )

        with transaction.atomic():
        # 行锁 + 二次校验，防止并发下订单状态变更
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.order_status not in [1,2]:
                raise ValueError("订单状态已变更，无法取消")
            if order.order_status ==2:
                if refund_result['success']:
                    #退款成功，更新订单状态为已退款
                    order.refund_status = 2
                    order.refund_amount = order.total_amount
                    order.refund_success_time = timezone.now()
            # 更新订单状态为已取消
            order.order_status = 6
            order.save()

        return order

    @staticmethod
    def update_order_status(order, new_status, is_admin=False):
        """更新订单状态，状态分发处理"""
        if not is_admin:
            raise ValueError("只有管理员可以修改订单状态")

        current_status = order.order_status
        if current_status == 1 and new_status == 2:
            # 复用 pay_order，确保支付字段写入一致（trade_no、pay_time 等）
            order, _ = OrderService.pay_order(order, payment_method='admin')
            return order
                
        elif current_status == 2 and new_status == 3:
            return OrderService.deliver_order(order, is_admin=True)
        elif current_status == 2 and new_status == 6:
            return OrderService.cancel_order(order, order.user, is_admin=True)
        elif current_status == 3 and new_status == 4:
            return OrderService.apply_return(order, order.user)
        elif current_status == 4 and new_status == 5:
            return OrderService.confirm_return(order, order.user, is_admin=True)
        elif current_status == 2 and new_status == 7:
            return OrderService.buyout_order(order, order.user, is_admin=True)
        elif current_status == 3 and new_status == 7:
            return OrderService.force_buyout_overdue(order, is_admin=True)
        else:
            raise ValueError(f"不支持从状态 {current_status} 转为 {new_status}")

        return order

    @staticmethod
    def buyout_order(order, user, is_admin=False):
        """主动买断（状态2→7，已支付未发货）
        用户没租过，全额退租金，押金转货款，补装备差价"""
        if not is_admin and order.user.id != user.id:
            raise ValueError("无权买断他人的订单")

        if order.order_status != 2:
            raise ValueError("只有已支付订单可以买断")

        # 事务外：退还租金（没租过，全额退，避免长事务锁库）
        refund_result = PaymentService.refund(order.id, order.rental_amount)
        if not refund_result["success"]:
            raise ValueError(
                f"租金退还失败，订单号：{order.order_sn}买断失败，"
                f"失败原因：{refund_result.get('error', '退款失败')}"
            )

        with transaction.atomic():
            # 行锁 + 二次校验，防止并发下订单状态变更
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.order_status != 2:
                raise ValueError("订单状态已变更，无法买断")

            # 装备总价 = 数量 × 装备单价(equipment.price)
            total_equipment_value = Decimal('0')
            for item in order.items.select_related('equipment').all():
                equipment = Equipment.objects.select_for_update().get(id=item.equipment_id)
                # 待发货状态下买断：装备没出库但被买走，扣实物库存
                if equipment.stock < item.count:
                    raise ValueError(f"装备【{equipment.name}】库存不足，当前库存：{equipment.stock}")
                total_equipment_value += item.count * equipment.price
                equipment.stock -= item.count
                # 只有扣完库存后数量为0，才标记为已售出（清库）
                if equipment.stock == 0:
                    equipment.is_sold_out = True
                equipment.save()

            # 买断款 = 装备总价 - 押金（押金转货款，补差价）
            order.buyout_amount = total_equipment_value - order.deposit_amount
            order.is_buyout = True
            order.deposit_status = 3  # 押金转货款
            order.order_status = 7
            order.save()

        return order
        

    @staticmethod
    def refund_order(order, user, is_admin=False, reason_type=None, custom_reason=None):
        # 权限校验
        if not is_admin and order.user.id != user.id:
            raise ValueError("无权申请退款")
        if order.order_status != 2:
            raise ValueError("只有已支付订单可以申请退款")
        refund_result = OrderService._simulate_payment_refund(order)
        """退款失败"""
        if not refund_result['success']:
            with transaction.atomic():
                # 行锁 + 二次校验，防止并发下订单状态变更
                order = Order.objects.select_for_update().get(pk=order.pk)
                if order.order_status != 2:
                    raise ValueError("订单状态已变更，无法申请退款")
                # 退款失败，只记录失败状态，不改订单状态
                order.refund_status = 3
                order.refund_fail_reason = refund_result.get('error', '退款失败')
                order.refund_fail_time = timezone.now()
                order.save()

        """退款成功"""
        with transaction.atomic():
            # 行锁 + 二次校验，防止并发下订单状态变更
            order = Order.objects.select_for_update().get(pk=order.pk)
             #  二次校验（防并发下状态变化）
            if order.refund_status != 0:
                raise ValueError("订单已在退款流程中，请勿重复申请")
            if order.order_status != 2:
                raise ValueError("订单状态已变更，无法退款")
            
            order.refund_apply_time = timezone.now()
            order.refund_status = 2
            order.refund_amount = order.total_amount
            order.refund_success_time = timezone.now()
            order.refund_reason_type = reason_type
            if reason_type == 'other':
                order.refund_reason_custom = custom_reason
            
            # 退款成功，订单变已取消
            order.order_status = 6
            order.save()


        return order

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
    def pay_order(order, payment_method='alipay'):
        """支付订单"""
        if order.order_status != 1:
            raise ValueError("只有待支付订单可以支付")
        payment_result = PaymentService.pay(order.id, order.total_amount, payment_method)
        if not payment_result['success']:
            raise ValueError(payment_result.get('error', '支付失败'))
        with transaction.atomic():
            # 事务内更新订单状态，确保支付成功后订单状态为已支付
            order = Order.objects.select_for_update().get(id=order.id)
            if order.order_status != 1:
                raise ValueError("只有待支付订单可以支付")
            order.order_status = 2
            order.pay_time = timezone.now()
            order.deposit_status = 1
            order.save()

            return order, payment_result

    @staticmethod
    def deliver_order(order, is_admin=False):
        """发货（管理员操作）
        发货即确认出库，调用 confirm_outbound 真正扣减实物库存"""
        if not is_admin:
            raise ValueError("只有管理员可以执行发货操作")

        if order.order_status != 2:
            raise ValueError("只有已支付待发货订单可以发货")

        # 发货即确认出库，扣减实物库存并把状态改为租赁中(3)
        return OrderService.confirm_outbound(order)

    @staticmethod
    def apply_return(order, user):
        """用户申请归还"""
        if order.user.id != user.id:
            raise ValueError("无权申请归还他人订单")

        if order.order_status != 3:
            raise ValueError("只有租赁中的订单可以申请归还")

        with transaction.atomic():
            # 事务内更新订单状态，确保申请归还成功后订单状态为待归还(4)
            order = Order.objects.select_for_update().get(id=order.id)
            if order.order_status != 3:
                raise ValueError("只有租赁中的订单可以申请归还")
            order.order_status = 4
            order.save()

        return order

    @staticmethod
    def confirm_return(order, user, is_admin=False):
        """确认归还（管理员操作）"""
        if not is_admin:
            raise ValueError("只有管理员可以确认归还")

        if order.order_status != 4:
            raise ValueError("只有待归还订单可以确认归还")

        with transaction.atomic():
            # 事务内更新订单状态，确保归还成功后订单状态为已归还
            order = Order.objects.select_for_update().get(id=order.id)
            if order.order_status != 4:
                raise ValueError("只有待归还订单可以确认归还")
            now = timezone.now()
            order.return_time = now

            overdue_days, overdue_fee = OrderService._calculate_overdue(order, now)
            if overdue_days > 0:
                order.overdue_days = overdue_days
                order.overdue_fee = overdue_fee
                order.deposit_status = 3
                actual_return = order.deposit_amount - order.overdue_fee
                if actual_return >= 0:
                    order.actual_return_amount = actual_return
                    order.overdue_debt = Decimal('0')
                else:
                    order.actual_return_amount = Decimal('0')
                    order.overdue_debt = abs(actual_return)
            else:
                order.deposit_status = 2
                order.actual_return_amount = order.deposit_amount
                order.overdue_debt = Decimal('0')

            for item in order.items.all():
                equipment = Equipment.objects.select_for_update().get(id=item.equipment_id)
                equipment.stock += item.count
                equipment.save()

            order.order_status = 5
            order.save()

        return order

    @staticmethod
    def pay_overdue_debt(order, user):
        """支付逾期欠费"""
        if order.overdue_debt <= 0:
            raise ValueError("没有逾期欠费需要支付")
        payment_result = PaymentService.pay_overdue_debt(order.id, order.overdue_debt)
        if not payment_result['success']:
            raise ValueError(payment_result.get('error', '支付失败'))

        with transaction.atomic():
            # 事务内更新订单状态，确保支付成功后订单状态为已支付
            order = Order.objects.select_for_update().get(id=order.id)
            if order.overdue_debt <= 0:
                raise ValueError("没有逾期欠费需要支付")
            if payment_result['success']:
                order.overdue_debt = Decimal('0')
                order.save()

                return order

    @staticmethod
    def force_buyout_overdue(order, is_admin=False):
        """逾期强制买断（状态3→7，租赁中逾期≥15天）
        用户已租过，租金不退；买断款 = 装备总价 - 押金 + 逾期费
        逾期费封顶15天，超过部分不再累加"""
        if not is_admin:
            raise ValueError("只有管理员可以执行强制买断操作")

        if order.order_status != 3:
            raise ValueError("只有租赁中的订单可以强制买断")

        now = timezone.now()
        overdue_days, overdue_fee = OrderService._calculate_overdue(order, now)
        if overdue_days < 15:
            raise ValueError(f"逾期天数不足15天，当前逾期{overdue_days}天，无法强制买断")

        with transaction.atomic():
            # 行锁 + 二次校验
            order = Order.objects.select_for_update().get(id=order.id)
            if order.order_status != 3:
                raise ValueError("订单状态已变更，无法强制买断")

            # 重新计算（防并发下逾期天数变化）
            overdue_days, overdue_fee = OrderService._calculate_overdue(order, now)
            if overdue_days < 15:
                raise ValueError("逾期天数不足15天，无法强制买断")

            # 装备总价 = 数量 × 装备单价(equipment.price)
            total_equipment_value = Decimal('0')
            for item in order.items.select_related('equipment').all():
                equipment = Equipment.objects.select_for_update().get(id=item.equipment_id)
                # 强制买断：状态3已扣过库存，这里只标记售出，不重复扣
                # 但只有库存为0才标记已售出
                total_equipment_value += item.count * equipment.price
                if equipment.stock == 0:
                    equipment.is_sold_out = True
                equipment.save()

            # 买断款 = 装备总价 - 押金（补差价）+ 逾期费
            order.buyout_amount = total_equipment_value - order.deposit_amount + overdue_fee
            order.is_buyout = True
            order.overdue_days = overdue_days
            order.overdue_fee = overdue_fee
            order.deposit_status = 3  # 押金转货款
            order.order_status = 7
            order.save()

        return order

    @staticmethod
    def auto_confirm_return(order):
        """状态4（待归还）逾期≥15天自动确认归还（系统兜底）
        管理员拖着不确认归还时，系统自动确认，算逾期费，加库存，退押金
        和强制买断的区别：用户已申请归还（愿意还），不罚买断，只算逾期费"""
        if order.order_status != 4:
            raise ValueError("只有待归还的订单可以自动确认归还")

        now = timezone.now()
        overdue_days, overdue_fee = OrderService._calculate_overdue(order, now)
        if overdue_days < 15:
            raise ValueError(f"逾期天数不足15天，当前逾期{overdue_days}天，无法自动确认归还")

        with transaction.atomic():
            # 行锁 + 二次校验
            order = Order.objects.select_for_update().get(id=order.id)
            if order.order_status != 4:
                raise ValueError("订单状态已变更，无法自动确认归还")

            # 重新计算（防并发下逾期天数变化）
            overdue_days, overdue_fee = OrderService._calculate_overdue(order, now)
            if overdue_days < 15:
                raise ValueError("逾期天数不足15天，无法自动确认归还")

            order.return_time = now
            order.overdue_days = overdue_days
            order.overdue_fee = overdue_fee

            # 结算押金：扣除逾期费后退还
            actual_return = order.deposit_amount - order.overdue_fee
            if actual_return >= 0:
                order.deposit_status = 3  # 扣除逾期费
                order.actual_return_amount = actual_return
                order.overdue_debt = Decimal('0')
            else:
                # 逾期费超过押金，用户还欠钱
                order.deposit_status = 3
                order.actual_return_amount = Decimal('0')
                order.overdue_debt = abs(actual_return)

            # 加库存（装备归还入库）
            for item in order.items.select_related('equipment').all():
                equipment = Equipment.objects.select_for_update().get(id=item.equipment_id)
                equipment.stock += item.count
                equipment.save()

            order.order_status = 5
            order.save()

        return order

    @staticmethod
    def freeze_user(order, is_admin=False):
        """冻结用户账户（管理员操作）"""
        if not is_admin:
            raise ValueError("只有管理员可以冻结用户账户")

        user = order.user
        user.is_frozen = True
        user.frozen_reason = f"订单{order.order_sn}逾期未归还，强制买断后账户冻结"
        user.frozen_time = timezone.now()
        user.save()

        return user

    @staticmethod
    def auto_cancel_unpaid_orders(expire_hours=72):
        """自动取消超时未支付订单（默认3天=72小时）"""
        from datetime import timedelta
        expire_time = timezone.now() - timedelta(hours=expire_hours)
        """数据库直接过滤出超时待支付订单，加行锁跳过被其他任务正在处理的行"""
        qs = Order.objects.filter(
            order_status=1,
            create_time__lte=expire_time
        )
        for order in qs.iterator(chunk_size=20): # 迭代器分批拿，控制内存
            try:
                OrderService.cancel_order(order, order.user, is_admin=True)
            except Exception as e:
                logger.error(f"自动取消订单{order.order_sn}失败: {str(e)}")

    @staticmethod
    def check_overdue_orders():
        """检查逾期订单并自动处理
        状态3逾期≥15天 → 强制买断（用户不还）
        状态4逾期≥15天 → 自动确认归还（用户已申请归还，管理员不确认）"""
        now = timezone.now()
        # 状态3（租赁中）和状态4（待归还）都可能逾期
        rental_orders = Order.objects.filter(order_status__in=[3, 4])

        for order in rental_orders:
            overdue_days, overdue_fee = OrderService._calculate_overdue(order, now)
            if overdue_days <= 0:
                continue

            # 先更新逾期天数和逾期费
            order.overdue_days = overdue_days
            order.overdue_fee = overdue_fee
            order.save()

            if overdue_days >= 15:
                try:
                    if order.order_status == 3:
                        # 状态3逾期≥15天：用户不归还 → 强制买断 + 冻结账户
                        OrderService.force_buyout_overdue(order, is_admin=True)
                        OrderService.freeze_user(order, is_admin=True)
                    elif order.order_status == 4:
                        # 状态4逾期≥15天：用户已申请归还但管理员不确认 → 自动确认归还
                        OrderService.auto_confirm_return(order)
                except Exception as e:
                    logger.error(f"处理订单{order.order_sn}逾期自动处理失败: {str(e)}")
