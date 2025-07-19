from django.contrib import admin
from import_export.admin import ImportExportMixin
from .models import UserProfile, PPOMaster, CaseType, Case, CaseMovement, StageAssignment

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'is_active_holder')
    list_filter = ('role', 'is_active_holder')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

@admin.register(PPOMaster)
class PPOMasterAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ('ppo_number', 'name', 'department', 'retirement_date')
    search_fields = ('ppo_number', 'name')

@admin.register(CaseType)
class CaseTypeAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ('name', 'workflow_type', 'priority', 'expected_days', 'is_active')
    list_filter = ('workflow_type', 'priority', 'is_active')

@admin.register(Case)
class CaseAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ('case_id', 'case_type', 'current_status', 'priority', 'is_completed', 'current_holder')
    list_filter = ('priority', 'is_completed', 'case_type', 'current_holder__role')
    search_fields = ('case_id', 'applicant_name', 'case_title')

@admin.register(CaseMovement)
class CaseMovementAdmin(admin.ModelAdmin):
    list_display = ('case', 'movement_date', 'from_stage', 'to_stage', 'action')
    list_filter = ('from_stage', 'to_stage')
    search_fields = ('case__case_id',)

@admin.register(StageAssignment)
class StageAssignmentAdmin(admin.ModelAdmin):
    list_display = ('stage', 'last_index')