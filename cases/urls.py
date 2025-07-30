# cases/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Existing URLs
    path('', views.dashboard, name='dashboard'),
    path('cases/', views.case_list, name='case_list'),
    path('cases/<str:case_id>/', views.case_detail, name='case_detail'),
    path('cases/<str:case_id>/move/', views.move_case, name='move_case'),
    path('register/', views.register_case, name='register_case'),
    path('bulk-import/', views.bulk_import_cases, name='bulk_import_cases'),
    path('export/<str:format>/', views.export_cases, name='export_cases'),
    
    # Enhanced Dashboard and Case Management - FIXED PATHS
    path('enhanced-dashboard/', views.enhanced_dashboard, name='enhanced_dashboard'),
    path('register/enhanced/', views.register_case_enhanced, name='enhanced_register_case'),
    path('cases/<str:case_id>/enhanced/', views.case_detail_enhanced, name='enhanced_case_detail'),  # Changed from 'case/' to 'cases/'
    
    # API endpoints for enhanced functionality
    path('api/case-type/<int:case_type_id>/fields/', views.get_case_type_fields, name='get_case_type_fields'),
    path('cases/<str:case_id>/milestone/<int:milestone_id>/update/', views.update_milestone, name='update_milestone'),
    path('milestone-report/', views.milestone_report, name='milestone_report'),
    
    # API endpoints
    path('api/ppo-data/', views.get_ppo_data, name='get_ppo_data'),
    path('api/sub-categories/', views.get_sub_categories, name='get_sub_categories'),
    path('api/retiring-employee/', views.get_retiring_employee_data, name='get_retiring_employee_data'),
    path('api/retiring-employees/', views.get_retiring_employees_by_month_year, name='get_retiring_employees_by_month_year'),
    path('api/available-holders/', views.get_available_holders, name='get_available_holders'),
    # Removed duplicate line
    path('get-ppo-data/', views.get_ppo_data, name='get_ppo_data'),
    path('get-sub-categories/', views.get_sub_categories, name='get_sub_categories'),
    path('get-retiring-employee-data/', views.get_retiring_employee_data, name='get_retiring_employee_data'),
    path('get-retiring-employees-by-month-year/', views.get_retiring_employees_by_month_year, name='get_retiring_employees_by_month_year'),
    path('get-available-holders/', views.get_available_holders, name='get_available_holders'),
]
 
    