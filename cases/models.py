# cases/models.py (updated with dashboard filtering and PPO improvements)

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, datetime
from django.core.validators import RegexValidator
import uuid
from simple_history.models import HistoricalRecords
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.core.validators import RegexValidator
from django.db.models import Q


WORKFLOW_STAGES = {
    'Type_A': ['DH', 'AAO', 'AO'],
    'Type_B': ['DH', 'AAO', 'AO', 'Jt.CCA'],
    'Type_C': ['DH', 'AAO', 'AO', 'Jt.CCA', 'CCA'],
    'Type_Extended': ['DH', 'AAO', 'AO', 'Dy.CCA', 'Jt.CCA', 'CCA', 'Pr.CCA']
}

# Role hierarchy for dashboard filtering
ROLE_HIERARCHY = {
    'Pr.CCA': ['CCA', 'Jt.CCA', 'Dy.CCA', 'AO', 'AAO', 'DH'],
    'CCA': ['Jt.CCA', 'Dy.CCA', 'AO', 'AAO', 'DH'],
    'Jt.CCA': ['Dy.CCA', 'AO', 'AAO', 'DH'],
    'Dy.CCA': ['AO', 'AAO', 'DH'],
    'AO': ['AAO', 'DH'],
    'AAO': ['DH'],
    'DH': [],
    'ADMIN': ['Pr.CCA', 'CCA', 'Jt.CCA', 'Dy.CCA', 'AO', 'AAO', 'DH'],
}

def get_workflow_for_case(case):
    return WORKFLOW_STAGES[case.case_type.workflow_type]

def get_current_stage_index(case, workflow):
    return workflow.index(case.current_holder.role)

def get_status_color(stage, priority):
    if stage in ['Jt.CCA', 'CCA', 'Pr.CCA']:
        return 'Blue'
    elif priority == 'High':
        return 'Red'
    elif priority == 'Medium':
        return 'Orange'
    else:
        return 'Green'

def get_subordinate_roles(user_role):
    """Get list of subordinate roles for a given user role"""
    return ROLE_HIERARCHY.get(user_role, [])

def get_dashboard_cases_query(user_profile):
    """
    Get queryset for dashboard cases based on user role hierarchy
    """
    user_role = user_profile.role
    subordinate_roles = get_subordinate_roles(user_role)
    
    # Include cases assigned to user and all subordinate roles
    roles_to_include = [user_role] + subordinate_roles
    
    return Case.objects.filter(
        current_holder__role__in=roles_to_include,
        is_completed=False
    )

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('DH', 'Dealing Hand'),
        ('AAO', 'Assistant Accounts Officer'),
        ('AO', 'Accounts Officer'),
        ('Dy.CCA', 'Deputy Chief Controller of Accounts'),
        ('Jt.CCA', 'Joint Chief Controller of Accounts'),
        ('CCA', 'Chief Controller of Accounts'),
        ('Pr.CCA', 'Principal Chief Controller of Accounts'),
        ('ADMIN', 'Administrator'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=15, blank=True)
    department = models.CharField(max_length=100, blank=True)
    is_active_holder = models.BooleanField(default=True)

    # NEW: Added a boolean field to grant Record Keeper permissions.
    is_record_keeper = models.BooleanField(
        default=False,
        help_text="Designates this user as responsible for handing over and receiving physical records."
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"
    
      
    def get_dashboard_cases(self):
        """Get cases for dashboard based on role hierarchy"""
        return get_dashboard_cases_query(self)
    
    def get_subordinate_roles(self):
        """Get list of subordinate roles"""
        return get_subordinate_roles(self.role)
    
    def can_view_case(self, case):
        """Check if user can view a specific case based on hierarchy"""
        user_role = self.role
        case_holder_role = case.current_holder.role
        subordinate_roles = get_subordinate_roles(user_role)
        
        return (
            case_holder_role == user_role or 
            case_holder_role in subordinate_roles or
            user_role == 'ADMIN'
        )

class PPOMaster(models.Model):
    pension_case_number = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)  # PNSN_CASE_NO
    ppo_number = models.CharField(max_length=20, unique=True, db_index=True)  # PPO_NO
    pension_type = models.CharField(max_length=50)  # PNSN_TYP
    employee_number = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    employee_name = models.CharField(max_length=200)  # EMP_NM
    date_of_retirement = models.DateField(null=True, blank=True)   # Date_of_retirement
    date_of_birth = models.DateField(null=True, blank=True)  # date_of_birth
    date_of_death_pensioner = models.DateField(null=True, blank=True)  # date_of_death_Pensioner
    date_of_death_family_pensioner = models.DateField(null=True, blank=True)  # date_of_death_FP
    nominee_name = models.CharField(max_length=200, blank=True, null=True)  # NOMINE_NM
    relationship_with_pensioner = models.CharField(max_length=50, blank=True, null=True)  # Relationship_with_the_pensioner
    bank_sort_code = models.CharField(max_length=20, blank=True, null=True)  # BANK_SORT_CD
    account_number = models.CharField(max_length=20, blank=True, null=True)  # ACCT_NO
    
    # Fields with validators removed - now simple CharField with blank=True, null=True
    designation = models.CharField(max_length=100, blank=True, null=True)
    aadhaar_number = models.CharField(max_length=12, blank=True, null=True)  # AADHAAR_NO
    mobile_number = models.CharField(max_length=15, blank=True, null=True)  # MOB_NO
    it_pan = models.CharField(max_length=10, blank=True, null=True)  # IT_PAN
    ifsc_code = models.CharField(max_length=11, blank=True, null=True)  # IFSC_CODE
    
    # Existing fields (kept for compatibility)
    department = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    branch_code = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Audit/history
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.ppo_number} - {self.employee_name}"
    
    @classmethod
    def get_by_ppo_number(cls, ppo_number):
        """Get PPO Master by PPO number with error handling"""
        try:
            return cls.objects.get(ppo_number=ppo_number)
        except cls.DoesNotExist:
            return None
        except cls.MultipleObjectsReturned:
            # Return the first one if multiple exist (shouldn't happen with unique constraint)
            return cls.objects.filter(ppo_number=ppo_number).first()
    
    @classmethod
    def search_ppo(cls, query):
        """Search PPO by number, employee name, or employee number"""
        if not query:
            return cls.objects.none()
        
        return cls.objects.filter(
            Q(ppo_number__icontains=query) |
            Q(employee_name__icontains=query) |
            Q(employee_number__icontains=query) |
            Q(pension_case_number__icontains=query)
        ).distinct()
    
    def get_full_details(self):
        """Get complete PPO details for case registration"""
        return {
            'ppo_number': self.ppo_number,
            'employee_name': self.employee_name,
            'employee_number': self.employee_number,
            'pension_type': self.pension_type,
            'date_of_retirement': self.date_of_retirement,
            'date_of_birth': self.date_of_birth,
            'mobile_number': self.mobile_number,
            'designation': self.designation,
            'department': self.department,
            'bank_name': self.bank_name,
            'account_number': self.account_number,
            'ifsc_code': self.ifsc_code,
            'address': self.address,
            'email': self.email,
            'nominee_name': self.nominee_name,
            'relationship_with_pensioner': self.relationship_with_pensioner,
        }

    class Meta:
        ordering = ['-date_of_retirement']
        verbose_name = 'PPO Master'
        verbose_name_plural = 'PPO Masters'
        indexes = [
            models.Index(fields=['ppo_number']),
            models.Index(fields=['employee_number']),
            models.Index(fields=['employee_name']),
            models.Index(fields=['pension_case_number']),
        ]

class RetiringEmployee(models.Model):
    employee_id = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    retirement_date = models.DateField()
    last_working_day = models.DateField(null=True, blank=True)
    
    # Pension details
    basic_pay = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pension_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Banking details
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    ifsc_code = models.CharField(max_length=11, blank=True)
    
    # Contact information
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    
    # Status tracking
    is_processed = models.BooleanField(default=False)
    ppo_generated = models.BooleanField(default=False)
    ppo_master = models.OneToOneField(
        PPOMaster, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='retiring_employee'
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_retiring_employees')
    
    class Meta:
        ordering = ['retirement_date', 'name']
        verbose_name = 'Retiring Employee'
        verbose_name_plural = 'Retiring Employees'
    
    def __str__(self):
        return f"{self.employee_id} - {self.name} (Retiring: {self.retirement_date})"
    
    def days_until_retirement(self):
        """Calculate days until retirement"""
        if self.retirement_date:
            delta = self.retirement_date - timezone.now().date()
            return delta.days
        return None
    
    def is_retired(self):
        """Check if employee has already retired"""
        return self.retirement_date <= timezone.now().date()
    
    def generate_ppo_master(self):
        """Generate PPOMaster record for this retiring employee"""
        if not self.ppo_master and not self.ppo_generated:
            # Generate unique PPO number
            year = self.retirement_date.year
            count = PPOMaster.objects.filter(
                date_of_retirement__year=year
            ).count() + 1
            
            ppo_number = f"PPO/{year}/{count:04d}"
            
            ppo_master = PPOMaster.objects.create(
                ppo_number=ppo_number,
                employee_name=self.name,  # Fixed field name
                designation=self.designation,
                department=self.department,
                pension_type='Superannuation',
                date_of_retirement=self.retirement_date,
                bank_name=self.bank_name,
                account_number=self.account_number,
                branch_code=self.ifsc_code,
                address=self.address,
                mobile_number=self.phone,  # Fixed field name
                email=self.email
            )
            
            self.ppo_master = ppo_master
            self.ppo_generated = True
            self.save()
            
            return ppo_master
        return self.ppo_master

class FamilyMember(models.Model):
    ppo_master = models.ForeignKey(PPOMaster, on_delete=models.CASCADE, related_name='family_members')
    name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=50, choices=[('spouse', 'Spouse'), ('child', 'Child'), ('parent', 'Parent')])
    birth_date = models.DateField(null=True, blank=True)
    is_eligible = models.BooleanField(default=False, help_text="Eligible for family pension")
    eligibility_reason = models.TextField(blank=True)
    
    history = HistoricalRecords()
    
    def __str__(self):
        return f"{self.name} ({self.relationship}) for {self.ppo_master.ppo_number}"
    
    def check_eligibility(self):
        # Example rule: Spouse always eligible; Child if under 25
        if self.relationship == 'spouse':
            self.is_eligible = True
            self.eligibility_reason = "Spouse is always eligible."
        elif self.relationship == 'child' and self.birth_date:
            age = (timezone.now().date() - self.birth_date).days / 365
            self.is_eligible = age < 25
            self.eligibility_reason = f"Child {'eligible' if self.is_eligible else 'not eligible'} (age {age:.0f})."
        else:
            self.is_eligible = False
            self.eligibility_reason = "No eligibility rule matched."
        self.save()

class CaseType(models.Model):
    WORKFLOW_TYPES = [
        ('Type_A', 'Type A: DH → AAO → AO'),
        ('Type_B', 'Type B: DH → AAO → AO → Jt.CCA'),
        ('Type_C', 'Type C: DH → AAO → AO → Jt.CCA → CCA'),
        ('Type_Extended', 'Type Extended: DH → AAO → AO → Dy.CCA → Jt.CCA → CCA → Pr.CCA'),
    ]
    
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    sub_categories = models.TextField(help_text="Comma-separated sub-categories")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    expected_days = models.IntegerField(default=30)
    workflow_type = models.CharField(max_length=20, choices=WORKFLOW_TYPES, default='Type_A')
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name
    
    def get_sub_categories_list(self):
        return [cat.strip() for cat in self.sub_categories.split(',') if cat.strip()]

class CaseQuerySet(models.QuerySet):
    def for_user_dashboard(self, user_profile):
        """Filter cases for user dashboard based on role hierarchy"""
        return get_dashboard_cases_query(user_profile)
    
    def pending_cases(self):
        """Get all pending (non-completed) cases"""
        return self.filter(is_completed=False)
    
    def by_priority(self, priority):
        """Filter cases by priority"""
        return self.filter(priority=priority)
    
    def by_status_color(self, color):
        """Filter cases by status color"""
        return self.filter(status_color=color)

class CaseManager(models.Manager):
    def get_queryset(self):
        return CaseQuerySet(self.model, using=self._db)
    
    def for_user_dashboard(self, user_profile):
        return self.get_queryset().for_user_dashboard(user_profile)
    
    def pending_cases(self):
        return self.get_queryset().pending_cases()

class Case(models.Model):
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]
    
    STATUS_COLORS = [
        ('Green', 'Green'),
        ('Orange', 'Orange'),
        ('Red', 'Red'),
        ('Blue', 'Blue'),
    ]
    
    MODE_OF_RECEIPT_CHOICES = [
        ('by_post', 'By Post'),
        ('by_hand', 'By Hand'),
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('email', 'Email'),
        ('in_person', 'In Person'),
    ]
    
    TYPE_OF_CORRECTION_CHOICES = [
        ('change_of_address', 'Change Of Address'),
        ('change_dob_family', 'Change / Correction of DOB of Family Pensioner'),
        ('change_name', 'Change / Correction of Name of the Pensioner / Family Pensioner'),
        ('other', 'Other'),
    ]
    
    FRESH_COMPLIANCE_CHOICES = [
        ('fresh', 'Fresh Case'),
        ('compliance', 'Compliance'),
    ]
    
    TYPE_OF_EMPLOYEE_CHOICES = [
        ('MTNL_IDA', 'MTNL IDA'),
        ('MTNL_CDA', 'MTNL CDA'),
        ('DOT_CDA', 'DOT CDA'),
    ]
    
    TYPE_OF_PENSION_CHOICES = [
        ('MTNL-IDA', 'MTNL-IDA'),
        ('DOT-CDA', 'DOT-CDA'),
    ]
    
    TYPE_OF_PENSIONER_CHOICES = [
        ('Superannuation/VR', 'Superannuation / VR'),
        ('Family Pensioner', 'Family Pensioner'),
    ]
    
    # Core fields
    case_id = models.CharField(max_length=50, unique=True, db_index=True)
    registration_date = models.DateTimeField(default=timezone.now)
    case_type = models.ForeignKey(CaseType, on_delete=models.CASCADE)
    sub_category = models.CharField(max_length=100)
    case_title = models.CharField(max_length=500)
    case_description = models.TextField()
    applicant_name = models.CharField(max_length=200)
    ppo_master = models.ForeignKey(PPOMaster, on_delete=models.SET_NULL, null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    current_status = models.CharField(max_length=200)
    current_holder = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='current_cases')
    days_in_current_stage = models.IntegerField(default=0)
    total_days_pending = models.IntegerField(default=0)
    expected_completion = models.DateTimeField()
    actual_completion = models.DateTimeField(null=True, blank=True)
    status_color = models.CharField(max_length=10, choices=STATUS_COLORS, default='Green')
    is_completed = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_cases')
    last_updated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='updated_cases')
    last_update_date = models.DateTimeField(auto_now=True)
    
    # Additional fields
    ppo_number = models.CharField(max_length=20, blank=True)
    name_pensioner = models.CharField(max_length=200, blank=True)
    mobile_number = models.CharField(max_length=15, blank=True)
    last_lc_done_date = models.DateField(null=True, blank=True)
    kyp_flag = models.BooleanField(default=False)
    mode_of_receipt = models.CharField(max_length=20, choices=MODE_OF_RECEIPT_CHOICES, blank=True)
    date_of_death = models.DateField(null=True, blank=True)
    name_claimant = models.CharField(max_length=200, blank=True)
    relationship = models.CharField(max_length=50, blank=True)
    service_book_enclosed = models.BooleanField(default=False)
    type_of_correction = models.CharField(max_length=30, choices=TYPE_OF_CORRECTION_CHOICES, blank=True)
    original_ppo_submitted = models.BooleanField(default=False)
    fresh_or_compliance = models.CharField(max_length=20, choices=FRESH_COMPLIANCE_CHOICES, blank=True)
    type_of_employee = models.CharField(max_length=20, choices=TYPE_OF_EMPLOYEE_CHOICES, blank=True)
    retiring_employee = models.ForeignKey('RetiringEmployee', on_delete=models.SET_NULL, null=True, blank=True)
    type_of_pension = models.CharField(max_length=20, choices=TYPE_OF_PENSION_CHOICES, blank=True)
    type_of_pensioner = models.CharField(max_length=30, choices=TYPE_OF_PENSIONER_CHOICES, blank=True)
    date_of_retirement = models.DateField(null=True, blank=True)
    
    # Custom manager
    objects = CaseManager()
    
    class Meta:
        ordering = ['-registration_date']
        indexes = [
            models.Index(fields=['case_id']),
            models.Index(fields=['ppo_number']),
            models.Index(fields=['current_holder', 'is_completed']),
            models.Index(fields=['priority', 'status_color']),
            models.Index(fields=['registration_date']),
        ]
    
    def __str__(self):
        return f"{self.case_id} - {self.case_title}"
    
    def save(self, *args, **kwargs):
        if not self.case_id:
            self.case_id = self.generate_case_id()
        if not self.expected_completion:
            self.expected_completion = self.calculate_expected_completion()
        
        # Auto-populate fields from PPO Master if available
        if self.ppo_master and not self.ppo_number:
            self.populate_from_ppo_master()
        
        super().save(*args, **kwargs)
    
    def populate_from_ppo_master(self):
        """Populate case fields from associated PPO Master"""
        if self.ppo_master:
            self.ppo_number = self.ppo_master.ppo_number
            self.name_pensioner = self.ppo_master.employee_name
            self.mobile_number = self.ppo_master.mobile_number or ''
            self.date_of_retirement = self.ppo_master.date_of_retirement
    
    def generate_case_id(self):
        from datetime import datetime
        today = datetime.now()
        year = today.year
        month = f"{today.month:02d}"
        
        # Get last case number for current month
        last_case = Case.objects.filter(
            case_id__startswith=f"CASE-{year}-{month}-"
        ).order_by('-case_id').first()
        
        if last_case:
            last_number = int(last_case.case_id.split('-')[-1])
            new_number = last_number + 1
        else:
            new_number = 1
        
        return f"CASE-{year}-{month}-{new_number:04d}"
    
    def calculate_expected_completion(self):
        from datetime import timedelta
        days_map = {'High': 15, 'Medium': 30, 'Low': 45}
        days = days_map.get(self.priority, 30)
        return self.registration_date + timedelta(days=days)
    
    def update_days_in_current_stage(self):
        if self.last_update_date:
            delta = timezone.now() - self.last_update_date
            self.days_in_current_stage = delta.days
            self.save(update_fields=['days_in_current_stage'])
    
    def can_be_viewed_by(self, user_profile):
        """Check if case can be viewed by given user profile"""
        return user_profile.can_view_case(self)

class CaseMovement(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='movements')
    movement_date = models.DateTimeField(default=timezone.now)
    from_stage = models.CharField(max_length=100)
    to_stage = models.CharField(max_length=100)
    from_holder = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='movements_from', null=True, blank=True)
    to_holder = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='movements_to')
    action = models.CharField(max_length=200)
    comments = models.TextField(blank=True)
    days_in_previous_stage = models.IntegerField(default=0)
    updated_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        ordering = ['-movement_date']
    
    def __str__(self):
        return f"{self.case.case_id} - {self.from_stage} to {self.to_stage}"

class FamilyPensionClaim(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('rejected', 'Rejected'),
    ]
    
    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name='family_pension_claim')
    claim_received = models.DateField(null=True, blank=True)
    claim_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    eligible_claimant = models.ForeignKey(FamilyMember, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    
    # Fixed the conflicting related_name and ppo_master field
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_family_pension_claims', null=True, blank=True)
    ppo_master = models.ForeignKey(PPOMaster, on_delete=models.SET_NULL, null=True, blank=True, related_name='family_pension_claims')
    
    history = HistoricalRecords()
    
    def __str__(self):
        return f"Claim for {self.case.case_id}"
    
    def check_claim_received(self):
        if self.claim_received:
            self.claim_status = 'received'
        self.save()

class DynamicFormField(models.Model):
    """Define dynamic fields for different case types"""
    FIELD_TYPES = [
        ('text', 'Text Input'),
        ('textarea', 'Text Area'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('select', 'Select Dropdown'),
        ('checkbox', 'Checkbox'),
        ('radio', 'Radio Button'),
        ('file', 'File Upload'),
    ]

    DATA_SOURCES = [
        ('manual', 'Manual Entry'),
        ('ppo_master', 'PPO Master'),
        ('retiring_employee', 'Retiring Employee'),
        ('database_query', 'Database Query'),
    ]

    case_type = models.ForeignKey(CaseType, on_delete=models.CASCADE, related_name='dynamic_fields')
    field_name = models.CharField(max_length=100)
    field_label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    help_text = models.TextField(blank=True)

    # For select/radio options
    choices = models.TextField(blank=True, help_text="One option per line for select/radio fields")

    # Data source configuration
    data_source = models.CharField(max_length=20, choices=DATA_SOURCES, default='manual')
    source_field = models.CharField(max_length=100, blank=True, help_text="Field name from data source")

    # Field ordering and grouping
    field_order = models.IntegerField(default=0)
    field_group = models.CharField(max_length=100, blank=True, help_text="Group related fields together")

    # Validation
    min_length = models.IntegerField(null=True, blank=True)
    max_length = models.IntegerField(null=True, blank=True)
    regex_pattern = models.CharField(max_length=500, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['field_order', 'field_name']
        unique_together = ['case_type', 'field_name']

    def __str__(self):
        return f"{self.case_type.name} - {self.field_label}"

    def get_choices_list(self):
        """Convert choices text to list"""
        if self.choices:
            return [choice.strip() for choice in self.choices.split('\n') if choice.strip()]
        return []


class CaseMilestone(models.Model):
    """Define milestones for different case types"""
    case_type = models.ForeignKey(CaseType, on_delete=models.CASCADE, related_name='milestones')
    milestone_name = models.CharField(max_length=200)
    milestone_description = models.TextField(blank=True)
    expected_days = models.IntegerField(default=1, help_text="Expected days to complete this milestone")
    is_mandatory = models.BooleanField(default=True)
    milestone_order = models.IntegerField(default=0)

    # Role that should complete this milestone
    # FIX: Increased max_length from 10 to 20 to accommodate 'RECORD_KEEPER'
    responsible_role = models.CharField(max_length=20, choices=UserProfile.ROLE_CHOICES)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['milestone_order', 'milestone_name']
        unique_together = ['case_type', 'milestone_name']

    def __str__(self):
        return f"{self.case_type.name} - {self.milestone_name}"

class CaseMilestoneProgress(models.Model):
    """Track progress of milestones for each case"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('blocked', 'Blocked'),
    ]

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='milestone_progress')
    milestone = models.ForeignKey(CaseMilestone, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    started_date = models.DateTimeField(null=True, blank=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    expected_completion_date = models.DateTimeField(null=True, blank=True)

    assigned_to = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='assigned_milestones')
    completed_by = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_milestones')

    notes = models.TextField(blank=True)
    attachments = models.FileField(upload_to='milestone_attachments/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['milestone__milestone_order']
        unique_together = ['case', 'milestone']

    def __str__(self):
        return f"{self.case.case_id} - {self.milestone.milestone_name} ({self.status})"

    def mark_completed(self, completed_by, notes=""):
        """Mark milestone as completed"""
        self.status = 'completed'
        self.completed_date = timezone.now()
        self.completed_by = completed_by
        if notes:
            self.notes = notes
        self.save()

    def calculate_days_taken(self):
        """Calculate days taken to complete milestone"""
        if self.started_date and self.completed_date:
            return (self.completed_date - self.started_date).days
        return None


class CaseFieldData(models.Model):
    """Store dynamic field data for cases"""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='field_data')
    field = models.ForeignKey(DynamicFormField, on_delete=models.CASCADE)

    # Store different types of data
    text_value = models.TextField(blank=True, null=True)
    number_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    date_value = models.DateField(null=True, blank=True)
    boolean_value = models.BooleanField(null=True, blank=True)
    file_value = models.FileField(upload_to='case_files/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['case', 'field']

    def __str__(self):
        return f"{self.case.case_id} - {self.field.field_name}"

    def get_value(self):
        """Get the appropriate value based on field type"""
        field_type = self.field.field_type
        if field_type in ['text', 'textarea', 'select', 'radio']:
            return self.text_value
        elif field_type == 'number':
            return self.number_value
        elif field_type == 'date':
            return self.date_value
        elif field_type == 'checkbox':
            return self.boolean_value
        elif field_type == 'file':
            return self.file_value
        return None

    def set_value(self, value):
        """Set the appropriate value based on field type"""
        field_type = self.field.field_type
        if field_type in ['text', 'textarea', 'select', 'radio']:
            self.text_value = str(value) if value is not None else None
        elif field_type == 'number':
            self.number_value = value
        elif field_type == 'date':
            self.date_value = value
        elif field_type == 'checkbox':
            self.boolean_value = bool(value)
        elif field_type == 'file':
            self.file_value = value


# Add these methods to your existing Case model (don't replace the model, just add these methods)
# You can add these methods inside your existing Case class

def get_dynamic_field_data(self):
    """Get all dynamic field data for this case"""
    field_data = {}
    for data in self.field_data.all():
        field_data[data.field.field_name] = data.get_value()
    return field_data

def set_dynamic_field_data(self, field_name, value):
    """Set dynamic field data for this case"""
    try:
        field = DynamicFormField.objects.get(case_type=self.case_type, field_name=field_name)
        field_data, created = CaseFieldData.objects.get_or_create(
            case=self, 
            field=field,
            defaults={'text_value': ''}
        )
        field_data.set_value(value)
        field_data.save()
        return True
    except DynamicFormField.DoesNotExist:
        return False

def get_milestone_progress(self):
    """Get milestone progress for this case"""
    return self.milestone_progress.all().order_by('milestone__milestone_order')

def initialize_milestones(self):
    """Initialize milestones for this case based on case type"""
    milestones = self.case_type.milestones.filter(is_active=True)
    for milestone in milestones:
        progress, created = CaseMilestoneProgress.objects.get_or_create(
            case=self,
            milestone=milestone,
            defaults={
                'assigned_to': self.current_holder,
                'expected_completion_date': timezone.now() + timezone.timedelta(days=milestone.expected_days)
            }
        )
    return self.milestone_progress.count()

# Add this to Case model's save method (modify your existing save method)
def enhanced_save(self, *args, **kwargs):
    # Your existing save logic here...
    if not self.case_id:
        self.case_id = self.generate_case_id()
    if not self.expected_completion:
        self.expected_completion = self.calculate_expected_completion()

    # Auto-populate fields from PPO Master if available
    if self.ppo_master and not self.ppo_number:
        self.populate_from_ppo_master()

    # Call the original save
    super().save(*args, **kwargs)

    # Initialize milestones for new cases
    if not hasattr(self, '_milestones_initialized'):
        self.initialize_milestones()
        self._milestones_initialized = True
class Location(models.Model):
    """
    Represents a physical location where a record can be stored.
    This can be a record room, an external office, or a user's desk.
    """
    LOCATION_TYPE_CHOICES = [
        ('RECORD_ROOM', 'Record Room'),
        ('EXTERNAL_OFFICE', 'External Office'),
        ('USER_DESK', 'User Desk'),
    ]

    name = models.CharField(max_length=200, unique=True, help_text="A unique name for the location (e.g., 'CTO Record Room', 'AAO John Doe's Desk').")
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPE_CHOICES, help_text="The category of the location.")
    custodian = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, help_text="The user responsible for this location (e.g., the record keeper for a room).")
    address = models.TextField(blank=True, help_text="Physical address or description of the location.")

    class Meta:
        ordering = ['name']
        verbose_name = "Record Location"
        verbose_name_plural = "Record Locations"

    def __str__(self):
        return self.name

class Record(models.Model):
    """
    Represents a single physical record, such as a Service Book or Pension File.
    """
    RECORD_TYPE_CHOICES = [
        ('SERVICE_BOOK', 'Service Book'),
        ('PENSION_FILE', 'Pension File'),
    ]

    RECORD_STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('IN_USE', 'In Use'),
        ('REQUISITIONED', 'Requisitioned'),
        ('MISSING', 'Missing'),
        ('NOT_APPLICABLE', 'Not Applicable'), # For cases where a record does not exist
    ]

    record_type = models.CharField(max_length=20, choices=RECORD_TYPE_CHOICES, help_text="The type of the record.")
    pensioner = models.ForeignKey(PPOMaster, on_delete=models.CASCADE, related_name='records', help_text="The pensioner this record belongs to.")
    status = models.CharField(max_length=20, choices=RECORD_STATUS_CHOICES, default='AVAILABLE', help_text="The current status of the record.")
    current_location = models.ForeignKey(Location, on_delete=models.PROTECT, help_text="The current physical location of the record.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        # Ensures a pensioner can only have one of each type of record
        unique_together = ('record_type', 'pensioner')
        ordering = ['pensioner__employee_name', 'record_type']
        verbose_name = "Physical Record"
        verbose_name_plural = "Physical Records"

    def __str__(self):
        return f"{self.get_record_type_display()} for {self.pensioner.employee_name}"

class RecordRequisition(models.Model):
    """
    Tracks the entire lifecycle of a request for one or more records.
    """
    REQUISITION_STATUS_CHOICES = [
        ('PENDING_APPROVAL', 'Pending AAO Approval'),
        ('REJECTED', 'Rejected'),
        ('APPROVED', 'Approved (Pending Handover)'),
        ('IN_TRANSIT', 'In Transit'),
        ('IN_USE', 'In Use (Handed Over)'),
        ('RETURN_REQUESTED', 'Return Requested'),
        ('RETURN_APPROVED', 'Return Approved'),
        ('RETURNED', 'Returned (Closed)'),
        ('RETURN_REJECTED', 'Return Rejected'),
    ]

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='requisitions', help_text="The case that this requisition is for.")
    records_requested = models.ManyToManyField(Record, help_text="The specific records being requested.")
    status = models.CharField(max_length=20, choices=REQUISITION_STATUS_CHOICES, default='PENDING_APPROVAL')
    is_return_request = models.BooleanField(default=False, help_text="Check this if this is a request to return records.")

    # Workflow Roles
    requester_dh = models.ForeignKey(UserProfile, related_name='made_requisitions', on_delete=models.PROTECT, help_text="The Dealing Hand who initiated the request.")
    approving_aao = models.ForeignKey(UserProfile, related_name='approved_requisitions', on_delete=models.PROTECT, help_text="The AAO responsible for approving this request.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Record Requisition"
        verbose_name_plural = "Record Requisitions"

    def __str__(self):
        return f"Requisition for Case {self.case.case_id} ({self.get_status_display()})"


class RecordMovement(models.Model):
    """
    Serves as a permanent audit log for every completed handover of a record.
    """
    requisition = models.ForeignKey(RecordRequisition, on_delete=models.CASCADE, related_name='movements', help_text="The requisition that authorized this movement.", null=True, blank=True)
    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name='movements', help_text="The specific record that was moved.")
    from_location = models.ForeignKey(Location, related_name='moves_from', on_delete=models.PROTECT, help_text="The location the record came from.")
    to_location = models.ForeignKey(Location, related_name='moves_to', on_delete=models.PROTECT, help_text="The location the record went to.")
    timestamp = models.DateTimeField(default=timezone.now, help_text="The exact date and time of the handover.")
    acknowledged_by = models.ForeignKey(UserProfile, on_delete=models.PROTECT, help_text="The user who received the record and acknowledged the handover.")
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Record Movement Log"
        verbose_name_plural = "Record Movement Logs"

    def __str__(self):
        return f"Moved {self.record} to {self.to_location} on {self.timestamp.strftime('%Y-%m-%d')}"

class CaseTypeTrigger(models.Model):
    """
    Allows an administrator to configure automatic record requisitions
    based on case events.
    """
    TRIGGER_EVENT_CHOICES = [
        ('ON_CASE_CREATION', 'On Case Creation'),
        ('ON_CASE_COMPLETION', 'On Case Completion'),
    ]

    RECORD_CHOICES = [
        ('SERVICE_BOOK', 'Service Book'),
        ('PENSION_FILE', 'Pension File'),
    ]

    case_type = models.ForeignKey(CaseType, on_delete=models.CASCADE, related_name='record_triggers')
    trigger_event = models.CharField(max_length=25, choices=TRIGGER_EVENT_CHOICES, help_text="The event that will fire this trigger.")
    records_to_request = models.CharField(max_length=20, choices=RECORD_CHOICES)

    class Meta:
        unique_together = ('case_type', 'trigger_event', 'records_to_request')
        verbose_name = "Case Type Record Trigger"
        verbose_name_plural = "Case Type Record Triggers"

    def __str__(self):
        return f"Trigger for {self.case_type.name}: {self.get_trigger_event_display()}"
    
# ==============================================================================
# == NEW MODELS FOR GRIEVANCE MANAGEMENT (As per new plan)
# ==============================================================================

class GrievanceMode(models.Model):
    """
    A model to allow administrators to configure the different modes by which
    a grievance can be received (e.g., By Post, Email, CPGRAMS Portal).
    This makes the grievance modes configurable from the admin panel.
    """
    name = models.CharField(max_length=100, unique=True, help_text="The name of the grievance mode.")
    is_active = models.BooleanField(default=True, help_text="Deactivate to hide this mode from forms.")

    class Meta:
        ordering = ['name']
        verbose_name = "Grievance Mode"
        verbose_name_plural = "Grievance Modes"

    def __str__(self):
        return self.name


class Grievance(models.Model):
    """
    Represents a single grievance filed by a pensioner or claimant.
    This grievance can then trigger the creation of a formal Case.
    """
    GRIEVANCE_STATUS_CHOICES = [
        ('NEW', 'New'),
        ('ACTION_INITIATED', 'Action Initiated (Case Created)'),
        ('DISPOSED', 'Disposed'),
    ]
    DISPOSAL_TYPE_CHOICES = [
        ('INTERIM_REPLY', 'Interim Reply'),
        ('FINAL_REPLY', 'Final Reply'),
    ]

    grievance_id = models.CharField(max_length=50, unique=True, db_index=True, help_text="A unique ID for the grievance.")
    pensioner = models.ForeignKey(PPOMaster, on_delete=models.PROTECT, related_name='grievances', help_text="The pensioner this grievance relates to.")
    
    complainant_name = models.CharField(max_length=200)
    complainant_contact = models.CharField(max_length=100, blank=True, help_text="Phone number or email address.")
    
    mode_of_receipt = models.ForeignKey('GrievanceMode', on_delete=models.PROTECT, help_text="How the grievance was received.")
    
    grievance_text = models.TextField(help_text="The full text of the complaint.")
    date_received = models.DateField(default=timezone.now)
    
    status = models.CharField(max_length=20, choices=GRIEVANCE_STATUS_CHOICES, default='NEW')
    disposal_type = models.CharField(max_length=20, choices=DISPOSAL_TYPE_CHOICES, null=True, blank=True)
    reply_details = models.TextField(blank=True, help_text="Details of the interim or final reply provided.")
    date_disposed = models.DateField(null=True, blank=True)

    generated_case = models.OneToOneField('Case', on_delete=models.SET_NULL, null=True, blank=True, related_name='source_grievance')

    history = HistoricalRecords()

    class Meta:
        ordering = ['-date_received']
        verbose_name = "Grievance"
        verbose_name_plural = "Grievances"

    def __str__(self):
        return f"Grievance {self.grievance_id} for {self.pensioner.employee_name}"

    def save(self, *args, **kwargs):
        # Auto-generate a unique ID if one isn't provided
        if not self.grievance_id:
            today = date.today() # This line now works because of the import
            count = Grievance.objects.filter(date_received__year=today.year, date_received__month=today.month).count() + 1
            self.grievance_id = f"GRV-{today.year}-{today.month:02d}-{count:04d}"
        super().save(*args, **kwargs)