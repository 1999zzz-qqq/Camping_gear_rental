from django.db import models
from django.db.models import UniqueConstraint

# Create your models here.
class Comment(models.Model):
    user = models.ForeignKey('users.UserInfo', on_delete=models.CASCADE, related_name='comments')
    equipment = models.ForeignKey('equipment.Equipment', on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    rating = models.IntegerField(choices=[(i,f'{i}星') for i in range(1,6)])
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'equipment'],
                name='unique_user_equipment_comment'
            )
        ]
