# cases/admin.py (Complete version with all enhancements integrated)

from django.contrib import admin
from import_export.admin import ImportExportMixin
from import_export import resources, fields, widgets
from import_export.results import RowResult
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Q, Count
from django.contrib import messages


# Import all models (existing + new)
from .models import (
    UserProfile, PPOMaster, CaseType, Case, CaseMovement, RetiringEmployee, FamilyMember,
    # New enhanced models
    DynamicFormField, GrievanceMode, Grievance, CaseMilestone, CaseMilestoneProgress, CaseFieldData,Location, Record, RecordRequisition, RecordMovement, CaseTypeTrigger
)
from django.contrib.auth.models import User

# ===== EXISTING RESOURCE CLASSES =====

class RetiringEmployeeResource(resources.ModelResource):
    retirement_date = fields.Field(
        attribute='retirement_date',
        widget=widgets.DateWidget(format='%d-%m-%Y')
    )
    last_working_day = fields.Field(
        attribute='last_working_day',
        widget=widgets.DateWidget(format='%d-%m-%Y')
    )

    class Meta:
        model = RetiringEmployee
        fields = (
            'employee_id', 'name', 'designation', 'department', 'retirement_date',
            'last_working_day', 'basic_pay', 'pension_amount', 'bank_name',
            'account_number', 'ifsc_code', 'address', 'phone', 'email',
            'is_processed', 'ppo_generated'
        )
        import_id_fields = ('employee_id',)

    def before_import_row(self, row, **kwargs):
        user = kwargs.get('user')
        if user:
            row['created_by'] = user.id
        else:
            # Fallback to first user
            first_user = User.objects.first()
            if first_user:
                row['created_by'] = first_user.id

class PPOMasterResource(resources.ModelResource):

    class Meta:
        model = PPOMaster
        import_id_fields = ('ppo_number',)
        skip_unchanged = True
        report_skipped = True
        use_transactions = False
        fields = (
            'pension_case_number', 'ppo_number', 'pension_type', 'employee_number', 
            'employee_name', 'date_of_retirement', 'date_of_birth', 
            'date_of_death_pensioner', 'date_of_death_family_pensioner', 'nominee_name',
            'relationship_with_pensioner', 'bank_sort_code', 'account_number', 'it_pan',
            'mobile_number', 'aadhaar_number', 'ifsc_code', 'designation', 'department',
            'bank_name', 'branch_code', 'address', 'email'
        )

    def before_import_row(self, row, row_number=None, **kwargs):
        print(f"\n=== PROCESSING ROW {row_number} ===")
        print(f"Original row keys: {list(row.keys())}")

        # Create a new row dict with cleaned keys
        cleaned_row = {}

        # Map headers with leading spaces to clean headers
        field_mappings = {
            'pension_case_number': ['pension_case_number', ' pension_case_number'],
            'ppo_number': ['ppo_number', ' ppo_number'],
            'pension_type': ['pension_type', ' pension_type'],
            'employee_number': ['employee_number', ' employee_number'],
            'employee_name': ['employee_name', ' employee_name'],
            'date_of_retirement': ['date_of_retirement', ' date_of_retirement'],
            'date_of_birth': ['date_of_birth', ' date_of_birth'],
            'date_of_death_pensioner': ['date_of_death_pensioner', ' date_of_death_pensioner'],
            'date_of_death_family_pensioner': ['date_of_death_family_pensioner', ' date_of_death_family_pensioner'],
            'nominee_name': ['nominee_name', ' nominee_name'],
            'relationship_with_pensioner': ['relationship_with_pensioner', ' relationship_with_pensioner'],
            'bank_sort_code': ['bank_sort_code', ' bank_sort_code'],
            'account_number': ['account_number', ' account_number'],
            'it_pan': ['it_pan', ' it_pan'],
            'mobile_number': ['mobile_number', ' mobile_number'],
            'aadhaar_number': ['aadhaar_number', ' aadhaar_number'],
            'ifsc_code': ['ifsc_code', ' ifsc_code'],
            'designation': ['designation', ' designation'],
            'department': ['department', ' department'],
            'bank_name': ['bank_name', ' bank_name'],
            'branch_code': ['branch_code', ' branch_code'],
            'address': ['address', ' address'],
            'email': ['email', ' email'],
            'created_at': ['created_at', ' created_at'],
            'updated_at': ['updated_at', ' updated_at'],
        }

        # Map each field from possible variations
        for clean_field, possible_keys in field_mappings.items():
            value = None
            for key in possible_keys:
                if key in row:
                    value = row[key]
                    break
            cleaned_row[clean_field] = value

        # Update the original row with cleaned values
        row.clear()
        row.update(cleaned_row)

        print(f"After cleaning - ppo_number: {repr(row.get('ppo_number'))}")
        print(f"After cleaning - employee_name: {repr(row.get('employee_name'))}")
        print(f"After cleaning - pension_type: {repr(row.get('pension_type'))}")

        # Clean up empty strings and None values
        for key, value in list(row.items()):
            if value in ['', 'None', 'NULL', None, 'nan', 'NaN']:
                row[key] = None
            elif isinstance(value, str):
                cleaned_value = value.strip()
                row[key] = cleaned_value if cleaned_value else None

        # Handle date fields - convert to None if empty or invalid
        date_fields = ['date_of_retirement', 'date_of_birth', 'date_of_death_pensioner', 'date_of_death_family_pensioner']
        for field in date_fields:
            if not row.get(field) or row.get(field) in ['01-01-1900', '1900-01-01', '00-00-0000']:
                row[field] = None

        # Validate only the absolutely required fields
        if not row.get('ppo_number'):
            raise ValueError(f"Row {row_number}: ppo_number is required but got: {repr(row.get('ppo_number'))}")

        if not row.get('employee_name'):
            raise ValueError(f"Row {row_number}: employee_name is required but got: {repr(row.get('employee_name'))}")

        if not row.get('pension_type'):
            raise ValueError(f"Row {row_number}: pension_type is required but got: {repr(row.get('pension_type'))}")

        print(f"Final row validation passed for row {row_number}")
        return row

    def get_instance(self, instance_loader, row):
        ppo_number = row.get('ppo_number')
        if ppo_number:
            try:
                return PPOMaster.objects.get(ppo_number=ppo_number)
            except PPOMaster.DoesNotExist:
                return None
        return None

    def import_row(self, row, instance_loader, **kwargs):
        try:
            result = super().import_row(row, instance_loader, **kwargs)
            if result.errors:
                print(f"Import errors for row: {result.errors}")
            else:
                print(f"Successfully processed row: {result.import_type}")
            return result
        except Exception as e:
            print(f"Exception during import_row: {str(e)}")
            print(f"Row data: {dict(row)}")
            row_result = RowResult()
            row_result.errors.append(f"Import error: {str(e)}")
            return row_result

# ===== NEW ENHANCED ADMIN CLASSES =====

@admin.register(DynamicFormField)
class DynamicFormFieldAdmin(admin.ModelAdmin):
    list_display = ['case_type', 'field_label', 'field_type', 'is_required', 'field_order', 'is_active']
    list_filter = ['case_type', 'field_type', 'is_required', 'is_active', 'data_source']
    search_fields = ['field_name', 'field_label', 'case_type__name']
    ordering = ['case_type', 'field_order', 'field_name']

    fieldsets = (
        ('Basic Information', {
            'fields': ('case_type', 'field_name', 'field_label', 'field_type', 'is_required', 'help_text')
        }),
        ('Field Configuration', {
            'fields': ('choices', 'field_order', 'field_group')
        }),
        ('Data Source', {
            'fields': ('data_source', 'source_field'),
            'classes': ('collapse',)
        }),
        ('Validation', {
            'fields': ('min_length', 'max_length', 'regex_pattern'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('case_type')


@admin.register(CaseMilestone)
class CaseMilestoneAdmin(admin.ModelAdmin):
    list_display = ['case_type', 'milestone_name', 'responsible_role', 'expected_days', 'is_mandatory', 'milestone_order', 'is_active']
    list_filter = ['case_type', 'responsible_role', 'is_mandatory', 'is_active']
    search_fields = ['milestone_name', 'case_type__name']
    ordering = ['case_type', 'milestone_order']

    fieldsets = (
        ('Basic Information', {
            'fields': ('case_type', 'milestone_name', 'milestone_description')
        }),
        ('Configuration', {
            'fields': ('responsible_role', 'expected_days', 'is_mandatory', 'milestone_order')
        }),
        ('Status', {
            'fields': ('is_active',)
        })
    )


@admin.register(CaseMilestoneProgress)
class CaseMilestoneProgressAdmin(admin.ModelAdmin):
    list_display = ['case', 'milestone', 'status', 'assigned_to', 'started_date', 'completed_date', 'get_days_taken']
    list_filter = ['status', 'milestone__case_type', 'assigned_to__role']
    search_fields = ['case__case_id', 'milestone__milestone_name']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Case Information', {
            'fields': ('case', 'milestone')
        }),
        ('Progress', {
            'fields': ('status', 'assigned_to', 'completed_by')
        }),
        ('Dates', {
            'fields': ('started_date', 'completed_date', 'expected_completion_date')
        }),
        ('Additional Information', {
            'fields': ('notes', 'attachments')
        })
    )

    readonly_fields = ['created_at', 'updated_at']

    def get_days_taken(self, obj):
        days = obj.calculate_days_taken()
        if days is not None:
            color = 'green' if days <= obj.milestone.expected_days else 'red'
            return format_html('<span style="color: {};">{} days</span>', color, days)
        return "Not completed"
    get_days_taken.short_description = 'Days Taken'


@admin.register(CaseFieldData)
class CaseFieldDataAdmin(admin.ModelAdmin):
    list_display = ['case', 'field', 'get_field_type', 'get_value_preview', 'updated_at']
    list_filter = ['field__field_type', 'field__case_type']
    search_fields = ['case__case_id', 'field__field_name']

    def get_field_type(self, obj):
        return obj.field.field_type
    get_field_type.short_description = 'Field Type'

    def get_value_preview(self, obj):
        value = obj.get_value()
        if value is None:
            return "No value"

        if obj.field.field_type == 'file' and value:
            return format_html('<a href="{}" target="_blank">View File</a>', value.url)

        str_value = str(value)
        return str_value[:50] + "..." if len(str_value) > 50 else str_value
    get_value_preview.short_description = 'Value'


# ===== INLINE CLASSES FOR ENHANCED FUNCTIONALITY =====

class CaseMilestoneProgressInline(admin.TabularInline):
    model = CaseMilestoneProgress
    extra = 0
    readonly_fields = ['milestone', 'created_at', 'updated_at']
    fields = ['milestone', 'status', 'assigned_to', 'started_date', 'completed_date', 'notes']


class CaseFieldDataInline(admin.TabularInline):
    model = CaseFieldData
    extra = 0
    readonly_fields = ['field', 'created_at', 'updated_at']
    fields = ['field', 'text_value', 'number_value', 'date_value', 'boolean_value']


# ===== ENHANCED EXISTING ADMIN CLASSES =====

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'is_active_holder', 'get_assigned_cases_count')
    list_filter = ('role', 'is_active_holder')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def get_assigned_cases_count(self, obj):
        count = obj.current_cases.filter(is_completed=False).count()
        return format_html('<span style="font-weight: bold;">{}</span>', count)
    get_assigned_cases_count.short_description = 'Active Cases'


@admin.register(PPOMaster)
class PPOMasterAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = PPOMasterResource
    list_display = ('ppo_number', 'employee_name', 'department', 'date_of_retirement', 'get_related_cases_count')
    search_fields = ('ppo_number', 'employee_name', 'employee_number')
    list_filter = ('pension_type', 'department')
    readonly_fields = ('created_at', 'updated_at')

    def get_related_cases_count(self, obj):
        count = obj.case_set.count()
        if count > 0:
            return format_html('<a href="{}?ppo_master__id__exact={}">{} cases</a>', 
                             reverse('admin:cases_case_changelist'), obj.id, count)
        return "No cases"
    get_related_cases_count.short_description = 'Related Cases'


@admin.register(CaseType)
class CaseTypeAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ('name', 'workflow_type', 'priority', 'expected_days', 'is_active', 
                   'get_dynamic_fields_count', 'get_milestones_count', 'get_cases_count')
    list_filter = ('workflow_type', 'priority', 'is_active')

    def get_dynamic_fields_count(self, obj):
        count = obj.dynamic_fields.count()
        if count > 0:
            return format_html('<a href="{}?case_type__id__exact={}">{} fields</a>', 
                             reverse('admin:cases_dynamicformfield_changelist'), obj.id, count)
        return "No fields"
    get_dynamic_fields_count.short_description = 'Dynamic Fields'

    def get_milestones_count(self, obj):
        count = obj.milestones.count()
        if count > 0:
            return format_html('<a href="{}?case_type__id__exact={}">{} milestones</a>', 
                             reverse('admin:cases_casemilestone_changelist'), obj.id, count)
        return "No milestones"
    get_milestones_count.short_description = 'Milestones'

    def get_cases_count(self, obj):
        count = obj.case_set.count()
        if count > 0:
            return format_html('<a href="{}?case_type__id__exact={}">{} cases</a>', 
                             reverse('admin:cases_case_changelist'), obj.id, count)
        return "No cases"
    get_cases_count.short_description = 'Cases'


# Action to initialize milestones for existing cases
def initialize_milestones_for_cases(modeladmin, request, queryset):
    count = 0
    for case in queryset:
        milestones_created = case.initialize_milestones()
        if milestones_created > 0:
            count += 1

    modeladmin.message_user(request, f"Initialized milestones for {count} cases.")
initialize_milestones_for_cases.short_description = "Initialize milestones for selected cases"


@admin.register(Case)
class CaseAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ('case_id', 'case_type', 'current_status', 'priority', 'is_completed', 
                   'current_holder', 'get_milestone_status', 'get_dynamic_fields_count')
    list_filter = ('priority', 'is_completed', 'case_type', 'current_holder__role', 'status_color')
    search_fields = ('case_id', 'applicant_name', 'case_title', 'ppo_number')
    date_hierarchy = 'registration_date'

    # Add the enhanced inlines
    inlines = [CaseMilestoneProgressInline, CaseFieldDataInline]

    # Add the action
    actions = [initialize_milestones_for_cases]

    fieldsets = (
        ('Basic Information', {
            'fields': ('case_type', 'sub_category', 'case_title', 'case_description', 'applicant_name')
        }),
        ('PPO Integration', {
            'fields': ('ppo_master', 'ppo_number', 'name_pensioner'),
            'classes': ('collapse',)
        }),
        ('Case Management', {
            'fields': ('priority', 'current_status', 'current_holder', 'is_completed')
        }),
        ('Dates', {
            'fields': ('registration_date', 'expected_completion', 'actual_completion'),
            'classes': ('collapse',)
        }),
        ('Additional Fields', {
            'fields': ('mobile_number', 'mode_of_receipt', 'fresh_or_compliance'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ('case_id', 'registration_date', 'created_by', 'last_updated_by', 'last_update_date')

    def get_milestone_status(self, obj):
        total = obj.milestone_progress.count()
        completed = obj.milestone_progress.filter(status='completed').count()
        if total == 0:
            return "No milestones"

        percentage = (completed / total) * 100
        color = 'green' if percentage == 100 else 'orange' if percentage > 50 else 'red'

        return format_html(
            '<span style="color: {};">{}/{} ({}%)</span>',
            color, completed, total, int(percentage)
        )
    get_milestone_status.short_description = 'Milestones'

    def get_dynamic_fields_count(self, obj):
        total_fields = obj.case_type.dynamic_fields.count()
        filled_fields = obj.field_data.count()

        if total_fields == 0:
            return "No dynamic fields"

        color = 'green' if filled_fields == total_fields else 'orange' if filled_fields > 0 else 'red'
        return format_html(
            '<span style="color: {};">{}/{}</span>',
            color, filled_fields, total_fields
        )
    get_dynamic_fields_count.short_description = 'Dynamic Fields'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.last_updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CaseMovement)
class CaseMovementAdmin(admin.ModelAdmin):
    list_display = ('case', 'movement_date', 'from_stage', 'to_stage', 'action', 'days_in_previous_stage')
    list_filter = ('from_stage', 'to_stage', 'action')
    search_fields = ('case__case_id',)
    date_hierarchy = 'movement_date'
    readonly_fields = ('movement_date',)


@admin.register(RetiringEmployee)
class RetiringEmployeeAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = RetiringEmployeeResource
    list_display = ('employee_id', 'name', 'designation', 'department', 'retirement_date', 
                   'is_processed', 'ppo_generated', 'get_days_until_retirement')
    list_filter = ('department', 'is_processed', 'ppo_generated')
    search_fields = ('employee_id', 'name')
    date_hierarchy = 'retirement_date'
    readonly_fields = ('ppo_master',)
    actions = ['generate_ppo_masters']

    def get_resource_kwargs(self, request, *args, **kwargs):
        rk = super().get_resource_kwargs(request, *args, **kwargs)
        rk['user'] = request.user
        return rk

    def generate_ppo_masters(self, request, queryset):
        count = 0
        for employee in queryset:
            if employee.generate_ppo_master():
                count += 1
        self.message_user(request, f"PPO masters generated for {count} employees.")
    generate_ppo_masters.short_description = "Generate PPO masters for selected employees"

    def get_days_until_retirement(self, obj):
        days = obj.days_until_retirement()
        if days is not None:
            if days < 0:
                return format_html('<span style="color: red;">Retired {} days ago</span>', abs(days))
            elif days <= 30:
                return format_html('<span style="color: orange;">{} days</span>', days)
            else:
                return format_html('<span style="color: green;">{} days</span>', days)
        return "Unknown"
    get_days_until_retirement.short_description = 'Days Until Retirement'


@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'relationship', 'ppo_master', 'is_eligible', 'get_age')
    list_filter = ('relationship', 'is_eligible')
    search_fields = ('name', 'ppo_master__ppo_number')
    actions = ['check_eligibility_for_selected']

    def check_eligibility_for_selected(self, request, queryset):
        for member in queryset:
            member.check_eligibility()
        self.message_user(request, f"Eligibility checked for {queryset.count()} family members.")
    check_eligibility_for_selected.short_description = "Check eligibility for selected members"

    def get_age(self, obj):
        if obj.birth_date:
            from django.utils import timezone
            age = (timezone.now().date() - obj.birth_date).days // 365
            return f"{age} years"
        return "Unknown"
    get_age.short_description = 'Age'


# ===== ADMIN SITE CUSTOMIZATION =====

admin.site.site_header = "Case Management System - Enhanced"
admin.site.site_title = "Case Management Admin"
admin.site.index_title = "Welcome to Case Management System"

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    """
    Admin interface for managing physical record locations.
    """
    list_display = ('name', 'location_type', 'custodian')
    list_filter = ('location_type',)
    search_fields = ('name', 'custodian__user__username')
    ordering = ('name',)

@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    """
    Admin interface for managing individual physical records.
    Allows for easy viewing and updating of record status and location.
    """
    list_display = ('pensioner', 'record_type', 'status', 'current_location')
    list_filter = ('record_type', 'status', 'current_location__name')
    search_fields = ('pensioner__employee_name', 'pensioner__ppo_number')
    autocomplete_fields = ('pensioner', 'current_location') # Makes selecting pensioner/location easier
    ordering = ('pensioner__employee_name',)

    fieldsets = (
        (None, {
            'fields': ('pensioner', 'record_type', 'status')
        }),
        ('Location Information', {
            'fields': ('current_location',)
        }),
    )

@admin.register(RecordRequisition)
class RecordRequisitionAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing and managing record requisitions.
    Primarily for tracking and auditing purposes.
    """
    list_display = ('case', 'requester_dh', 'approving_aao', 'status', 'created_at')
    list_filter = ('status', 'is_return_request')
    search_fields = ('case__case_id', 'requester_dh__user__username')
    autocomplete_fields = ('case', 'records_requested', 'requester_dh', 'approving_aao')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

@admin.register(RecordMovement)
class RecordMovementAdmin(admin.ModelAdmin):
    """
    Admin interface for the audit log of all record movements.
    This view is read-only as movements should only be created by the application logic.
    """
    list_display = ('record', 'from_location', 'to_location', 'acknowledged_by', 'timestamp')
    list_filter = ('from_location', 'to_location')
    search_fields = ('record__pensioner__employee_name',)
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)

    # Make the admin view read-only
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    
    
if admin.site.is_registered(CaseType):
    admin.site.unregister(CaseType)

class CaseTypeTriggerInline(admin.TabularInline):
    """
    This allows an admin to manage triggers directly from the CaseType page.
    It's a more intuitive user experience.
    """
    model = CaseTypeTrigger
    extra = 1 # Show one empty form for adding a new trigger.
    verbose_name = "Automated Record Trigger"
    verbose_name_plural = "Automated Record Triggers"

    # ==============================================================================
# == ENHANCEMENTS TO EXISTING ADMIN MODELS
# ==============================================================================

# Unregister the existing UserProfile admin if it exists, to re-register it with enhancements
# This avoids errors if you run this script multiple times.
# Note: You might need to import the original admin class if it's in a different file.
# For now, we assume it's simple and can be re-registered directly.

# Clear existing registrations to avoid conflicts if you re-run this
# This is a robust way to handle updates in a development environment
if admin.site.is_registered(UserProfile):
    admin.site.unregister(UserProfile)
if admin.site.is_registered(Case):
    admin.site.unregister(Case)
if admin.site.is_registered(CaseType):
    admin.site.unregister(CaseType)


class RecordRequisitionInline(admin.TabularInline):
    """
    Inline view to show record requisitions directly on the Case admin page.
    """
    model = RecordRequisition
    extra = 0 # Don't show empty forms for new requisitions
    readonly_fields = ('requester_dh', 'approving_aao', 'status', 'created_at')
    fields = ('requester_dh', 'approving_aao', 'status', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False # Requisitions should be created from the app, not admin

@admin.register(Case)
class CaseAdmin(ImportExportMixin, admin.ModelAdmin):
    """
    Enhanced Case admin to show related record requisitions.
    """
    # Assuming your existing CaseAdmin configuration is similar to this
    list_display = ('case_id', 'case_type', 'current_status', 'priority', 'is_completed', 'current_holder')
    list_filter = ('priority', 'is_completed', 'case_type', 'current_holder__role')
    search_fields = ('case_id', 'applicant_name', 'case_title')
    inlines = [RecordRequisitionInline] # Add the inline here

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin for User Profiles.
    """
    list_display = ('user', 'role', 'is_active_holder')
    list_filter = ('role', 'is_active_holder')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

class CaseTypeTriggerInline(admin.TabularInline):
    """
    Allows managing triggers directly from the CaseType admin page.
    """
    model = CaseTypeTrigger
    extra = 1

@admin.register(CaseType)
class CaseTypeAdmin(ImportExportMixin, admin.ModelAdmin):
    """
    Enhanced CaseType admin to manage triggers inline.
    """
    list_display = ('name', 'workflow_type', 'priority', 'is_active')
    list_filter = ('workflow_type', 'priority', 'is_active')
    
    # Add the inline here. Now, when you edit a CaseType, you'll see a section
    # at the bottom to manage its triggers.
    inlines = [CaseTypeTriggerInline]

# Re-register other models if they were unregistered
# This ensures all your original admin views are still present
if not admin.site.is_registered(PPOMaster):
    admin.site.register(PPOMaster)
if not admin.site.is_registered(CaseMovement):
    admin.site.register(CaseMovement)
    # ==============================================================================
# == NEW ADMIN REGISTRATIONS FOR GRIEVANCE MANAGEMENT
# ==============================================================================

@admin.register(GrievanceMode)
class GrievanceModeAdmin(admin.ModelAdmin):
    """
    Admin interface for managing the configurable Grievance Modes.
    """
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    actions = ['activate_modes', 'deactivate_modes']

    def activate_modes(self, request, queryset):
        queryset.update(is_active=True)
    activate_modes.short_description = "Mark selected modes as active"

    def deactivate_modes(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_modes.short_description = "Mark selected modes as inactive"


@admin.register(Grievance)
class GrievanceAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing and managing Grievances.
    """
    list_display = ('grievance_id', 'pensioner', 'status', 'disposal_type', 'date_received', 'generated_case')
    list_filter = ('status', 'disposal_type', 'mode_of_receipt', 'date_received')
    search_fields = ('grievance_id', 'pensioner__ppo_number', 'pensioner__employee_name', 'complainant_name')
    autocomplete_fields = ('pensioner', 'generated_case')
    date_hierarchy = 'date_received'
    ordering = ('-date_received',)

    fieldsets = (
        ('Grievance Details', {
            'fields': ('grievance_id', 'pensioner', 'complainant_name', 'complainant_contact', 'mode_of_receipt', 'date_received', 'grievance_text')
        }),
        ('Resolution & Case Link', {
            'fields': ('status', 'disposal_type', 'reply_details', 'date_disposed', 'generated_case')
        }),
    )
    # Make grievance_id read-only after creation
    readonly_fields = ('grievance_id',)