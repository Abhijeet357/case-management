# cases/urls.py (Complete and Corrected)

from django.urls import path
from . import views  # <-- THIS LINE WAS MISSING

urlpatterns = [
    # Existing URLs from your original file
    path('', views.dashboard, name='dashboard'),
    path('cases/', views.case_list, name='case_list'),
    path('cases/<str:case_id>/', views.case_detail, name='case_detail'),
    path('cases/<str:case_id>/move/', views.move_case, name='move_case'),
    path('register/', views.register_case, name='register_case'),
    path('bulk-import/', views.bulk_import_cases, name='bulk_import_cases'),
    path('export/<str:format>/', views.export_cases, name='export_cases'),
    
    # Enhanced Dashboard and Case Management
    path('enhanced-dashboard/', views.enhanced_dashboard, name='enhanced_dashboard'),
    path('register/enhanced/', views.register_case_enhanced, name='enhanced_register_case'),
    path('cases/<str:case_id>/enhanced/', views.case_detail_enhanced, name='enhanced_case_detail'),
    
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
    path('get-ppo-data/', views.get_ppo_data, name='get_ppo_data'),
    path('get-sub-categories/', views.get_sub_categories, name='get_sub_categories'),
    path('get-retiring-employee-data/', views.get_retiring_employee_data, name='get_retiring_employee_data'),
    path('get-retiring-employees-by-month-year/', views.get_retiring_employees_by_month_year, name='get_retiring_employees_by_month_year'),
    path('get-available-holders/', views.get_available_holders, name='get_available_holders'),

    # == URLs for Record Management Workflow ==

    # Phase 2: DH initiates a requisition
    path('cases/<str:case_id>/request-record/', views.request_record, name='request_record'),

    # Phase 3 & 6: AAO approval dashboard and action (for new requisitions and returns)
    path('records/approval-dashboard/', views.requisition_approval_dashboard, name='requisition_approval_dashboard'),
    path('records/requisition/<int:requisition_id>/action/', views.requisition_action, name='requisition_action'),

    # Phase 4 & 7: Record Keeper dashboard, handover, and return acknowledgment
    path('records/keeper-dashboard/', views.record_keeper_dashboard, name='record_keeper_dashboard'),
    path('records/requisition/<int:requisition_id>/handover/', views.handover_record, name='handover_record'),
    path('records/requisition/<int:requisition_id>/acknowledge-return/', views.acknowledge_return, name='acknowledge_return'),

    # Phase 5: DH initiates a return
    path('cases/<str:case_id>/return-record/', views.return_record, name='return_record'),
]
