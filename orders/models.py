from django.db import models
from users.models import UserInfo
from equipment.models import Equipment


class Order(models.Model):
    STATUS_CHOICES = (
        (1, "待支付"),
        (2, "已支付待发货"),
        (3, "租赁中"),
        (4, "待归还"),
        (5, "已归还"),
        (6, "已取消"),
        (7, "已买断"),
    )
    REFUND_STATUS_CHOICES = (
        (0, "未退款"),
        (1, "退款中"),
        (2, "退款成功"),
        (3, "退款失败"),
    )
    REFUND_REASON_CHOICES = (
        ('change_mind', '不想租了'),
        ('schedule_conflict', '时间冲突'),
        ('equipment_issue', '装备问题'),
        ('price_concern', '价格问题'),
        ('other', '其他'),
    )
    order_sn = models.CharField(max_length=64, verbose_name="订单编号")
    order_status = models.IntegerField(choices=STATUS_CHOICES, default=1, verbose_name='订单状态')
    user = models.ForeignKey(to='users.UserInfo', on_delete=models.CASCADE, related_name='orders_user', verbose_name='用户')
    rental_days = models.IntegerField(default=0, verbose_name="租赁天数")
    rental_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='租金')
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='押金')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="订单总价")

    deposit_status = models.IntegerField(
        choices=[(0,'未支付'),(1,'已冻结'),(2,'已退还'),(3,'扣除')],
        default=0,
        verbose_name='押金状态'
    )
    overdue_rate = models.DecimalField(max_digits=5, decimal_places=2, default=150.0, verbose_name='逾期费比例(%)')
    return_time = models.DateTimeField(null=True, blank=True, verbose_name='实际归还时间')
    overdue_days = models.IntegerField(default=0, verbose_name='逾期天数')
    overdue_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='逾期费')
    overdue_debt = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='逾期欠费')
    actual_return_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='实际退还金额')
    is_buyout = models.BooleanField(default=False, verbose_name='是否买断')
    buyout_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='买断金额')
    
    start_time = models.DateTimeField(verbose_name="租赁开始时间")
    end_time = models.DateTimeField(verbose_name="租赁结束时间")
    contact_name = models.CharField(max_length=20, verbose_name="联系人")
    contact_phone = models.CharField(max_length=11, verbose_name="联系电话")
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="订单创建时间")
    pay_time = models.DateTimeField(null=True, blank=True, verbose_name='支付时间')
    refund_status = models.IntegerField(choices=REFUND_STATUS_CHOICES, default=0, verbose_name='退款状态')
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='退款金额')
    refund_reason_type = models.CharField(
        max_length=50, 
        choices=REFUND_REASON_CHOICES, 
        null=True, 
        blank=True,
        verbose_name='退款原因类型'
    )
    refund_reason_custom = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        verbose_name='自定义退款原因'
    )
    refund_apply_time = models.DateTimeField(null=True, blank=True, verbose_name='退款申请时间')
    refund_success_time = models.DateTimeField(null=True, blank=True, verbose_name='退款成功时间')
    refund_fail_time = models.DateTimeField(null=True, blank=True, verbose_name='退款失败时间')
    refund_fail_reason = models.TextField(null=True, blank=True, verbose_name='退款失败原因')


class OrderItem(models.Model):
    order = models.ForeignKey(to='Order', on_delete=models.CASCADE, related_name="items", verbose_name="所属订单")
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="租赁单价")
    rental_days = models.IntegerField(verbose_name="租赁天数")
    count = models.PositiveIntegerField(default=1, verbose_name="租赁数量")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="单品小计")
    equipment = models.ForeignKey(to='equipment.Equipment', on_delete=models.CASCADE, verbose_name='租赁装备',
                                  related_name='orderItem_equipment')


class Cart(models.Model):
    user = models.OneToOneField(to='users.UserInfo', on_delete=models.CASCADE, verbose_name='用户')
    create_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    update_time = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '购物车'
        verbose_name_plural = '购物车'


class CartItem(models.Model):
    cart = models.ForeignKey(to='Cart', on_delete=models.CASCADE, related_name='items', verbose_name='所属购物车')
    equipment = models.ForeignKey(to='equipment.Equipment', on_delete=models.CASCADE, verbose_name='装备')
    count = models.PositiveIntegerField(default=1, verbose_name='数量')
    rental_days = models.IntegerField(default=1, verbose_name='租赁天数')
    add_time = models.DateTimeField(auto_now_add=True, verbose_name='添加时间')

    class Meta:
        verbose_name = '购物车商品'
        verbose_name_plural = '购物车商品'
        unique_together = ('cart', 'equipment')