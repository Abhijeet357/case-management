# cases/models.py (updated created_by to allow null=True, blank=True for flexibility)

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import RegexValidator
import uuid
from simple_history.models import HistoricalRecords
from dateutil.relativedelta import relativedelta

WORKFLOW_STAGES = {
    'Type_A': ['DH', 'AAO', 'AO'],
    'Type_B': ['DH', 'AAO', 'AO', 'Jt.CCA'],
    'Type_C': ['DH', 'AAO', 'AO', 'Jt.CCA', 'CCA'],
    'Type_Extended': ['DH', 'AAO', 'AO', 'Dy.CCA', 'Jt.CCA', 'CCA', 'Pr.CCA']
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
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=15, blank=True)
    department = models.CharField(max_length=100, blank=True)
    is_active_holder = models.BooleanField(default=True)
    
    def __str__(self):
        return self.user.username

class PPOMaster(models.Model):
    ppo_number = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    pension_type = models.CharField(max_length=50)
    retirement_date = models.DateField()
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    branch_code = models.CharField(max_length=20)
    address = models.TextField()
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.ppo_number} - {self.name}"

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
                retirement_date__year=year
            ).count() + 1
            
            ppo_number = f"PPO/{year}/{count:04d}"
            
            ppo_master = PPOMaster.objects.create(
                ppo_number=ppo_number,
                name=self.name,
                designation=self.designation,
                department=self.department,
                pension_type='Superannuation',  # Default, can be customized
                retirement_date=self.retirement_date,
                bank_name=self.bank_name,
                account_number=self.account_number,
                branch_code=self.ifsc_code,
                address=self.address,
                phone=self.phone,
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
    relationship = models.CharField(max_length=50, choices=[('spouse', 'Spouse'), ('child', 'Child'), ('parent', 'Parent')])  # Add more as needed
    birth_date = models.DateField(null=True, blank=True)  # For age eligibility
    is_eligible = models.BooleanField(default=False, help_text="Eligible for family pension")
    eligibility_reason = models.TextField(blank=True)
    
    history = HistoricalRecords()  # Track changes
    
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
    
    # Existing fields
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
    
    # Add the new fields that are referenced in the form
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
    date_of_retirement = models.DateField(null=True, blank=True)  # For Superannuation, fetched but stored
    
    class Meta:
        ordering = ['-registration_date']
    
    def __str__(self):
        return f"{self.case_id} - {self.case_title}"
    
    def save(self, *args, **kwargs):
        if not self.case_id:
            self.case_id = self.generate_case_id()
        if not self.expected_completion:
            self.expected_completion = self.calculate_expected_completion()
        super().save(*args, **kwargs)
    
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
    
    history = HistoricalRecords()  # Track changes
    
    def __str__(self):
        return f"Claim for {self.case.case_id}"
    
    def check_claim_received(self):
        if self.claim_received:
            self.claim_status = 'received'
        self.save()