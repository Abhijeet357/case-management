# cases/urls.py (Complete with all Reports Integration)

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
    path('grievances/list/', views.grievance_list, name='grievance_list'),
    path('grievances/my-grievances/', views.my_grievances, name='my_grievances'),
    path('grievances/pending-actions/', views.pending_grievance_actions, name='pending_grievance_actions'),
    path('grievances/dashboard/', views.grievance_dashboard, name='grievance_dashboard'),
    path('grievances/escalated/', views.escalated_grievances, name='escalated_grievances'),
    path('grievances/overdue/', views.overdue_grievances, name='overdue_grievances'),
    path('grievances/reports/', views.grievance_reports, name='grievance_reports'),
    path('grievances/search/', views.search_grievances, name='search_grievances'),
    path('grievances/export/', views.export_grievances, name='export_grievances'),

    # Other Core URLs
    path('bulk-import/', views.bulk_import_cases, name='bulk_import_cases'),
    
    # API endpoints for AJAX functionality
    path('api/ppo-data/', views.get_ppo_data, name='get_ppo_data'),
    path('api/sub-categories/', views.get_sub_categories, name='get_sub_categories'),
    path('api/retiring-employee/', views.get_retiring_employee_data, name='get_retiring_employee_data'),
    path('api/retiring-employees/', views.get_retiring_employees_by_month_year, name='get_retiring_employees_by_month_year'),
    path('api/available-holders/', views.get_available_holders, name='get_available_holders'),
    
    # Legacy API endpoints (for backward compatibility)
    path('get-ppo-data/', views.get_ppo_data, name='get_ppo_data_legacy'),
    path('get-sub-categories/', views.get_sub_categories, name='get_sub_categories_legacy'),
    path('get-retiring-employee-data/', views.get_retiring_employee_data, name='get_retiring_employee_data_legacy'),
    path('get-retiring-employees-by-month-year/', views.get_retiring_employees_by_month_year, name='get_retiring_employees_by_month_year_legacy'),
    path('get-available-holders/', views.get_available_holders, name='get_available_holders_legacy'),
    
    # ========================================================================
    # COMPREHENSIVE REPORTS SECTION - The heart of our reporting system
    # ========================================================================
    
    # Main Reports Dashboard - This serves as the central hub
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    
    # Core Case Analysis Reports
    path('reports/case-aging/', views.case_aging_report, name='case_aging_report'),
    path('reports/workload-analysis/', views.workload_analysis_report, name='workload_analysis_report'),
    path('reports/performance-trends/', views.performance_trends_report, name='performance_trends_report'),
    path('reports/executive-summary/', views.executive_summary_report, name='executive_summary_report'),
    
    # Specialized Report Types
    path('reports/grievance-analytics/', views.grievance_reports, name='grievance_reports'),  # Enhanced grievance reporting
    path('reports/milestone-progress/', views.milestone_report, name='milestone_report'),  # Progress tracking
    path('reports/record-history/', views.record_history_report, name='record_history_report'),  # Record movement tracking
    
    # Data Export Endpoints - Essential for external analysis
    path('reports/export/cases/', views.export_cases_report, name='export_cases_report'),
    path('reports/export/workload/', views.export_workload_report, name='export_workload_report'),
    path('reports/export/performance/', views.export_performance_report, name='export_performance_report'),
    path('reports/export/grievances/', views.export_grievances, name='export_grievances'),
    
    # Advanced Analytics and Specialized Reports
    path('reports/case-type-analysis/', views.case_type_analysis_report, name='case_type_analysis_report'),
    path('reports/bottleneck-analysis/', views.bottleneck_analysis_report, name='bottleneck_analysis_report'),
    path('reports/sla-compliance/', views.sla_compliance_report, name='sla_compliance_report'),
    path('reports/user-productivity/', views.user_productivity_report, name='user_productivity_report'),
    
    # Enhanced Export Options with Filtering
    path('reports/export/cases/filtered/', views.export_filtered_cases, name='export_filtered_cases'),
    path('reports/export/custom-report/', views.export_custom_report, name='export_custom_report'),
    
    # Interactive Dashboard APIs for Charts and Graphs
    path('api/reports/dashboard-data/', views.get_dashboard_data, name='get_dashboard_data'),
    path('api/reports/trend-data/', views.get_trend_data, name='get_trend_data'),
    path('api/reports/workload-data/', views.get_workload_data, name='get_workload_data'),
    
    # Report Scheduling and Automation (for future implementation)
    path('reports/schedule/', views.schedule_report, name='schedule_report'),
    path('reports/automated/', views.automated_report_list, name='automated_report_list'),
]