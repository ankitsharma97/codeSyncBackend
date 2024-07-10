from rest_framework import serializers
from .models import GroupUser

class GroupUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupUser
        fields = '__all__'
        