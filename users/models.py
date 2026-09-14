from django.db import models

# Create your models here.
from django.contrib.auth.models import User,AbstractUser
class UserInfo(AbstractUser):
    phone = models.CharField(max_length=20, blank=True, default='',verbose_name='电话号码')
    is_frozen = models.BooleanField(default=False, verbose_name='账户是否冻结')
    frozen_reason = models.CharField(max_length=255, blank=True, default='', verbose_name='冻结原因')
    frozen_time = models.DateTimeField(null=True, blank=True, verbose_name='冻结时间')

