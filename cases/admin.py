# cases/admin.py

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import (
    UserProfile, PPOMaster, CaseType, Case, CaseMovement, RetiringEmployee,
    GrievanceMode, Grievance, Location, Record, RecordRequisition,
    RecordMovement, CaseTypeTrigger, IndexRegister, DocumentCategory
)

# ==============================================================================
# == RESOURCE CLASSES (for Import/Export)
# ==============================================================================

class PPOMasterResource(resources.ModelResource):
    class Meta:
        model = PPOMaster
        import_id_fields = ('ppo_number',)
        fields = ('ppo_number', 'employee_name', 'pension_type', 'date_of_retirement', 'mobile_number')

# ==============================================================================
# == INLINE ADMIN CLASSES
# ==============================================================================

class CaseTypeTriggerInline(admin.TabularInline):
    model = CaseTypeTrigger
    extra = 1

# ==============================================================================
# == MODEL ADMIN CLASSES (Consolidated and Corrected)
# ==============================================================================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'is_record_keeper', 'is_active_holder')
    list_filter = ('role', 'is_record_keeper', 'is_active_holder')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

@admin.register(PPOMaster)
class PPOMasterAdmin(ImportExportModelAdmin):
    resource_class = PPOMasterResource
    list_display = ('ppo_number', 'employee_name', 'department', 'date_of_retirement')
    # This search_fields is required by RecordAdmin's autocomplete
    search_fields = ('ppo_number', 'employee_name', 'employee_number')
    list_filter = ('pension_type', 'department')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(CaseType)
class CaseTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'workflow_type', 'priority', 'is_active')
    list_filter = ('workflow_type', 'priority', 'is_active')
    # This search_fields is required by IndexRegisterAdmin's autocomplete
    search_fields = ('name',) 
    inlines = [CaseTypeTriggerInline]

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('case_id', 'case_type', 'current_status', 'priority', 'is_completed', 'current_holder')
    list_filter = ('priority', 'is_completed', 'case_type', 'current_holder__role')
    search_fields = ('case_id', 'applicant_name', 'case_title', 'ppo_number')
    date_hierarchy = 'registration_date'
    readonly_fields = ('case_id', 'created_by', 'last_updated_by')

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_type', 'custodian')
    list_filter = ('location_type',)
    # This search_fields is required by RecordAdmin's autocomplete
    search_fields = ('name', 'custodian__user__username')

@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = ('file_number', 'record_type', 'pensioner', 'current_location', 'status')
    list_filter = ('record_type', 'status', 'current_location')
    search_fields = ('file_number', 'pensioner__employee_name', 'pensioner__ppo_number')
    # This line requires PPOMasterAdmin and LocationAdmin to have search_fields
    autocomplete_fields = ('pensioner', 'current_location')

@admin.register(IndexRegister)
class IndexRegisterAdmin(ImportExportModelAdmin):
    list_display = ('file_number', 'subject', 'workflow_type', 'dh_responsible', 'status')
    list_filter = ('workflow_type', 'status', 'dh_responsible')
    search_fields = ('file_number', 'subject')
    # This line requires CaseTypeAdmin and UserProfileAdmin to have search_fields
    autocomplete_fields = ('dh_responsible', 'current_location', 'related_case_types')

# Register other models with their default admin interface
admin.site.register(GrievanceMode)
admin.site.register(Grievance)
admin.site.register(CaseMovement)
admin.site.register(RetiringEmployee)
admin.site.register(RecordRequisition)
admin.site.register(RecordMovement)
admin.site.register(DocumentCategory)

# ===== ADMIN SITE CUSTOMIZATION =====
admin.site.site_header = "Pension Case Management System"
admin.site.site_title = "Pension CMS Admin"
admin.site.index_title = "Welcome to the Admin Portal"