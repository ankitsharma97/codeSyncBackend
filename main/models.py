from django.db import models

# Create your models here.

class GroupUser(models.Model):
    group_id = models.CharField(max_length=50)
    user_id = models.CharField(max_length=50)

    def __str__(self):
        return self.group_id