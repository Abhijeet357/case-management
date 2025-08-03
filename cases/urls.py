# cases/urls.py (Consolidated with all new Grievance URLs)

from django.urls import path
from . import views

urlpatterns = [
    # Core URLs
    path('', views.dashboard, name='dashboard'),
    path('cases/', views.case_list, name='case_list'),
    path('cases/<str:case_id>/', views.case_detail, name='case_detail'),
    path('cases/<str:case_id>/move/', views.move_case, name='move_case'),
    path('register/', views.register_case, name='register_case'),
    
    # Record Management URLs
    path('cases/<str:case_id>/request-record/', views.request_record, name='request_record'),
    path('cases/<str:case_id>/return-record/', views.return_record, name='return_record'),
    path('records/approval-dashboard/', views.requisition_approval_dashboard, name='requisition_approval_dashboard'),
    path('records/keeper-dashboard/', views.record_keeper_dashboard, name='record_keeper_dashboard'),
    path('records/history-report/', views.record_history_report, name='record_history_report'),
    path('records/requisition/<int:requisition_id>/action/', views.requisition_action, name='requisition_action'),
    path('records/requisition/<int:requisition_id>/handover/', views.handover_record, name='handover_record'),
    path('records/requisition/<int:requisition_id>/acknowledge-return/', views.acknowledge_return, name='acknowledge_return'),

    # Grievance Management URLs
    path('grievances/register/', views.register_grievance, name='register_grievance'),
    path('grievances/<str:grievance_id>/action/', views.take_grievance_action, name='take_grievance_action'),
    
    # NEW: URLs from your friend's code
    path('grievances/list/', views.grievance_list, name='grievance_list'),
    path('grievances/my-grievances/', views.my_grievances, name='my_grievances'),
    path('grievances/pending-actions/', views.pending_grievance_actions, name='pending_grievance_actions'),
    path('grievances/dashboard/', views.grievance_dashboard, name='grievance_dashboard'),
    path('grievances/escalated/', views.escalated_grievances, name='escalated_grievances'),
    path('grievances/overdue/', views.overdue_grievances, name='overdue_grievances'),
    path('grievances/reports/', views.grievance_reports, name='grievance_reports'),
    path('grievances/search/', views.search_grievances, name='search_grievances'),
    path('grievances/export/', views.export_grievances, name='export_grievances'),

    # Other URLs (bulk import, etc.)
    path('bulk-import/', views.bulk_import_cases, name='bulk_import_cases'),
    # ... any other URLs you have ...
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
]
