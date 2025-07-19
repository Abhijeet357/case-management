# cases/admin.py (updated before_import_row to set created_by if missing)

from django.contrib import admin
from import_export.admin import ImportExportMixin
from import_export import resources, fields, widgets
from .models import UserProfile, PPOMaster, CaseType, Case, CaseMovement, RetiringEmployee, FamilyMember
from django.contrib.auth.models import User

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

@admin.register(RetiringEmployee)
class RetiringEmployeeAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = RetiringEmployeeResource
    list_display = ('employee_id', 'name', 'designation', 'department', 'retirement_date', 'is_processed', 'ppo_generated')
    list_filter = ('department', 'is_processed', 'ppo_generated')
    search_fields = ('employee_id', 'name')
    date_hierarchy = 'retirement_date'
    readonly_fields = ('ppo_master',)  # Make PPO master view-only if generated
    actions = ['generate_ppo_masters']  # Custom action to generate PPO in bulk

    def get_resource_kwargs(self, request, *args, **kwargs):
        rk = super().get_resource_kwargs(request, *args, **kwargs)
        rk['user'] = request.user
        return rk

    def generate_ppo_masters(self, request, queryset):
        for employee in queryset:
            employee.generate_ppo_master()
        self.message_user(request, f"PPO masters generated for {queryset.count()} employees.")
    generate_ppo_masters.short_description = "Generate PPO masters for selected employees"

# Optionally register FamilyMember if needed for admin management
@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'relationship', 'ppo_master', 'is_eligible')
    list_filter = ('relationship', 'is_eligible')
    search_fields = ('name', 'ppo_master__ppo_number')