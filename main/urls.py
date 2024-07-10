from django.urls import path
from . import views

urlpatterns = [
    path('get/<str:group>', views.getUsers, name='getUsers'),
    path('', views.addUser, name='addUser'),
    path('delete/<str:group>/<str:user>', views.deleteUser, name='deleteUser'),
]