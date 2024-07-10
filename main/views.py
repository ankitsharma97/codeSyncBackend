from django.shortcuts import render
from django.http import JsonResponse
from .models import GroupUser
from .serializers import GroupUserSerializer
from rest_framework.decorators import api_view
# Create your views here.

@api_view(['GET'])
def getUsers(request, group):
    groupUsers = GroupUser.objects.filter(group_id=group)
    serializer = GroupUserSerializer(groupUsers, many=True)
    return JsonResponse(serializer.data, safe=False)

@api_view(['POST'])
def addUser(request):
    serializer = GroupUserSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
    return JsonResponse(serializer.data, safe=False)


@api_view(['DELETE'])
def deleteUser(request, user, group):
    groupUser = GroupUser.objects.filter(user_id=user, group_id=group)
    groupUser.delete()
    return JsonResponse('User deleted', safe=False)
