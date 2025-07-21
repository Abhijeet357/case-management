# cases/admin.py (fixed version with proper PPOMaster import handling)

from django.contrib import admin
from import_export.admin import ImportExportMixin
from import_export import resources, fields, widgets
from import_export.results import RowResult
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

# Custom resource for PPOMaster to handle imports
# Updated PPOMasterResource class for admin.py

# Updated PPOMasterResource class for admin.py (without dummy defaults)

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
        """
        Override to handle instance loading with proper ppo_number
        """
        ppo_number = row.get('ppo_number')
        if ppo_number:
            try:
                return PPOMaster.objects.get(ppo_number=ppo_number)
            except PPOMaster.DoesNotExist:
                return None
        return None

    def import_row(self, row, instance_loader, **kwargs):
        """
        Override import_row to add better error handling
        """
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
            # Create a failed result
            row_result = RowResult()
            row_result.errors.append(f"Import error: {str(e)}")
            return row_result

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'is_active_holder')
    list_filter = ('role', 'is_active_holder')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

@admin.register(PPOMaster)
class PPOMasterAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = PPOMasterResource
    list_display = ('ppo_number', 'employee_name', 'department', 'date_of_retirement')
    search_fields = ('ppo_number', 'employee_name', 'employee_number')
    list_filter = ('pension_type', 'department')
    readonly_fields = ('created_at', 'updated_at')

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
    readonly_fields = ('ppo_master',)
    actions = ['generate_ppo_masters']

    def get_resource_kwargs(self, request, *args, **kwargs):
        rk = super().get_resource_kwargs(request, *args, **kwargs)
        rk['user'] = request.user
        return rk

    def generate_ppo_masters(self, request, queryset):
        for employee in queryset:
            employee.generate_ppo_master()
        self.message_user(request, f"PPO masters generated for {queryset.count()} employees.")
    generate_ppo_masters.short_description = "Generate PPO masters for selected employees"

@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'relationship', 'ppo_master', 'is_eligible')
    list_filter = ('relationship', 'is_eligible')
    search_fields = ('name', 'ppo_master__ppo_number')