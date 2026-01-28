from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='permissions_index'),
   
    # 🔽 STAFF ACTIONS
    path('view/<int:id>/', views.view_request, name='view_request'),
    path('approve/<int:id>/', views.approve_request, name='approve_request'),
    path('reject/<int:id>/', views.reject_request, name='reject_request'),
    path('forward/<int:id>/', views.forward_request, name='forward_request'),
    
    path("requests/<int:pk>/forward-ui/", views.forward_ui, name="forward_ui"),
    path("requests/<int:pk>/forward-do/", views.forward_do, name="forward_do"),
]


