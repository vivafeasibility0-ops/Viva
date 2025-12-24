from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload-master/', views.upload_dashboard_master, name='upload_master'),  # <- corrected
    path('check-feasibility/', views.check_feasibility, name='check_feasibility'),
    path('l2/', views.l2_search_page, name='l2_search'),
    path('l2-upload/', views.upload_l2_master, name='upload_l2_master'),
    path('l2-api/', views.l2_search_api, name='l2_search_api'),
]

