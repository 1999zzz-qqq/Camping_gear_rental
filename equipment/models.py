from django.db import models


# Create your models here.
# 分类表
class Category(models.Model):
    # 分类名称
    name = models.CharField(max_length=32, verbose_name='分类名称')
    # 父分类（自关联）
    parent = models.ForeignKey(
        to='self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父分类'
    )
    # 分类排序（数字越小越靠前）
    sort = models.PositiveIntegerField(default=99, verbose_name='排序')
    # 分类状态（启用/禁用）
    is_show = models.BooleanField(default=True, verbose_name='是否显示')
    # 创建时间
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '露营装备分类'
        verbose_name_plural = '露营装备分类'

    def __str__(self):
        return self.name


# 装备表
class Equipment(models.Model):
    category = models.ForeignKey(
        to='Category',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipments_category",
        verbose_name="所属分类"
    )
    name = models.CharField(max_length=10, verbose_name='装备名称')
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='单价')
    daily_rental = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name='日租金')
    deposit = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name='押金')    
    stock = models.PositiveIntegerField(
        default=0,
        verbose_name="库存数量"
    )
    # 展示信息
    cover_img = models.ImageField(upload_to="equipment_img/", null=True, blank=True, verbose_name="装备图片")
    desc = models.TextField(null=True, blank=True, verbose_name="装备简介")
    # 状态
    is_shelf = models.BooleanField(default=True, verbose_name="是否上架")
    is_show = models.BooleanField(default=True, verbose_name="是否显示")
    # 是否已售出
    is_sold_out = models.BooleanField(default=False, verbose_name="是否售出")
    # 时间
    created_time = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "露营装备"
        verbose_name_plural = "露营装备"
        unique_together = ('category', 'name')

    def __str__(self):
        return self.name
    
