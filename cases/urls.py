# cases/urls.py (updated with new endpoint)

from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('cases/', views.case_list, name='case_list'),
    path('cases/register/', views.register_case, name='register_case'),
    path('cases/<str:case_id>/', views.case_detail, name='case_detail'),
    path('cases/<str:case_id>/move/', views.move_case, name='move_case'),
    path('users/register/', views.register_user, name='register_user'),
    path('import/bulk/', views.bulk_import_cases, name='bulk_import_cases'),

    # API endpoints
    path('api/ppo/', views.get_ppo_data, name='get_ppo_data'),
    path('api/sub_categories/', views.get_sub_categories, name='get_sub_categories'),
    path('api/retiring_employee/', views.get_retiring_employee_data, name='get_retiring_employee_data'),
    path('api/retiring_employees_by_month_year/', views.get_retiring_employees_by_month_year, name='get_retiring_employees_by_month_year'),
    path('api/available_holders/', views.get_available_holders, name='get_available_holders'),  # New endpoint

    # Legacy endpoints (for backward compatibility)
    path('get-ppo-data/', views.get_ppo_data, name='get_ppo_data_legacy'),
    path('get-retiring-employee-data/', views.get_retiring_employee_data, name='get_retiring_employee_data_legacy'),
    path('export/<str:format>/', views.export_cases, name='export_cases'),

]
